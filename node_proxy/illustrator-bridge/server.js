import http from "node:http";
import { URL } from "node:url";
import { WebSocketServer } from "ws";
import { createLiveSessionStore, rpcLiveSession } from "../live-session.js";

const PORT = Number(process.env.STARBRIDGE_ILLUSTRATOR_PROXY_PORT || 8972);
const MAX_FRAME_BYTES = 4 * 1024 * 1024;
const MAX_SESSION_BYTES = 32 * 1024;
const DEFAULT_STATE_MAX_AGE_MS = 2000;
const WRITE_METHODS = new Set([
  "illustrator.select_object",
  "illustrator.set_fill",
  "illustrator.move_object",
  "illustrator.create_path",
  "illustrator.apply_artisan_map",
  "illustrator.rollback_artisan_map",
]);
const METHODS = new Set([
  "illustrator.get_state",
  "illustrator.document_info",
  "illustrator.zoom_to_selection",
  "illustrator.readback_artisan_map",
  "illustrator.commit_artisan_map",
  ...WRITE_METHODS,
]);

let adapter = null;
const liveSession = createLiveSessionStore("illustrator", update => {
  if (adapter?.readyState === 1) adapter.send(JSON.stringify(update));
});
let latestStateRecord = null;
let latestFrame = null;
let stateRevision = 0;
const pending = new Map();
const status = {
  adapter_connected: false,
  capture_connected: false,
  last_state_at: null,
  last_frame_at: null,
  pending_jobs: 0,
  rejected_states: 0,
  last_error: null,
};

function json(res, code, value) {
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(value));
}

function error(id, code, message) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

function safeString(value) {
  return typeof value === "string" && !/[\\/]:?|file:|users\\|home\//i.test(value);
}

function safeToken(value, maximum = 64) {
  return (
    typeof value === "string" &&
    value.length <= maximum &&
    /^[\p{L}\p{N} _.+()-]*$/u.test(value) &&
    safeString(value)
  );
}

function boundedInteger(value, maximum) {
  return Number.isInteger(value) && value >= 0 && value <= maximum ? value : null;
}

function finiteNumber(value, minimum, maximum) {
  return typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum;
}

function validNameRows(value, idPattern, maximum) {
  if (!Array.isArray(value) || value.length > maximum) return false;
  const ids = new Set();
  for (const row of value) {
    if (!Array.isArray(row) || row.length !== 2 || !idPattern.test(String(row[0])) || !safeToken(row[1], 64) || ids.has(row[0])) return false;
    ids.add(row[0]);
  }
  return true;
}

function validate(message) {
  if (!message || message.jsonrpc !== "2.0" || !("id" in message) || !METHODS.has(message.method)) {
    return error(message?.id, -32600, "invalid_or_unlisted_method");
  }
  if (!message.params || typeof message.params !== "object" || Array.isArray(message.params)) {
    return error(message.id, -32602, "params_must_be_object");
  }
  if (WRITE_METHODS.has(message.method) && message.params.confirm_write !== true) {
    return error(message.id, -32010, "confirm_write=true_required");
  }
  if (message.params.object_id !== undefined && !/^item:[1-9][0-9]*$/.test(String(message.params.object_id))) {
    return error(message.id, -32602, "object_id_must_be_session_local");
  }
  if (["illustrator.apply_artisan_map", "illustrator.readback_artisan_map", "illustrator.commit_artisan_map", "illustrator.rollback_artisan_map"].includes(message.method)) {
    if (!/^apply:[0-9a-f]{12}$/.test(String(message.params.transaction_ref || "")) || !/^imap:[0-9a-f]{12}$/.test(String(message.params.map_ref || ""))) {
      return error(message.id, -32602, "artisan_refs_invalid");
    }
  }
  if (message.method === "illustrator.apply_artisan_map") {
    if (!validNameRows(message.params.layers, /^layer-[a-z][a-z-]{0,31}$/, 4) || !validNameRows(message.params.objects, /^shape-[0-9]{4,}$/, 128)) {
      return error(message.id, -32602, "artisan_name_map_invalid");
    }
    if (!Number.isInteger(message.params.expected_state_revision) || message.params.expected_state_revision !== stateRevision) {
      return error(message.id, -32011, "stale_state_revision");
    }
  }
  return null;
}

function normalizeItem(item) {
  if (!item || typeof item !== "object" || !/^item:[1-9][0-9]*$/.test(String(item.object_id))) return null;
  if (!safeToken(item.type)) return null;
  return {
    object_id: String(item.object_id),
    type: item.type,
    selected: Boolean(item.selected),
    locked: Boolean(item.locked),
    hidden: Boolean(item.hidden),
  };
}

function normalizeLayer(layer) {
  if (!layer || typeof layer !== "object" || !/^layer:[1-9][0-9]*$/.test(String(layer.layer_id))) return null;
  return { layer_id: String(layer.layer_id), visible: Boolean(layer.visible), locked: Boolean(layer.locked) };
}

function normalizeArtboard(artboard) {
  if (!artboard || typeof artboard !== "object" || !/^artboard:[1-9][0-9]*$/.test(String(artboard.artboard_id))) return null;
  if (!Array.isArray(artboard.rect) || artboard.rect.length !== 4 || !artboard.rect.every(value => finiteNumber(value, -10000000, 10000000))) return null;
  return { artboard_id: String(artboard.artboard_id), rect: [...artboard.rect] };
}

function normalizeState(message) {
  if (!message || message.type !== "state" || message.protocol_version !== 2) return null;
  if (!Number.isInteger(message.sequence) || message.sequence < 1) return null;
  if (message.host?.app !== "Adobe Illustrator" || message.host?.adapter !== "custom_uxp_v2") return null;
  if (!safeToken(message.host.version, 32)) return null;
  if (!Array.isArray(message.selection) || message.selection.length > 256) return null;
  if (!Array.isArray(message.layers) || message.layers.length > 512) return null;
  if (!Array.isArray(message.artboards) || message.artboards.length > 128) return null;

  const selection = message.selection.map(normalizeItem);
  const layers = message.layers.map(normalizeLayer);
  const artboards = message.artboards.map(normalizeArtboard);
  if (selection.includes(null) || layers.includes(null) || artboards.includes(null)) return null;

  let document = null;
  if (message.document !== null) {
    if (!message.document || typeof message.document !== "object") return null;
    const pageItems = boundedInteger(message.document.page_items, 1000000);
    const layerCount = boundedInteger(message.document.layer_count, 512);
    const artboardCount = boundedInteger(message.document.artboard_count, 128);
    if (pageItems === null || layerCount === null || artboardCount === null || !safeToken(message.document.color_space, 32)) return null;
    document = {
      page_items: pageItems,
      layer_count: layerCount,
      artboard_count: artboardCount,
      color_space: message.document.color_space,
    };
  }

  if (message.zoom !== null && !finiteNumber(message.zoom, 0.01, 640)) return null;
  if (message.tool !== null && !safeToken(message.tool, 64)) return null;
  const capturedAt = new Date(message.captured_at);
  if (!message.captured_at || Number.isNaN(capturedAt.getTime())) return null;

  return {
    type: "state",
    protocol_version: 2,
    sequence: message.sequence,
    host: { app: "Adobe Illustrator", version: message.host.version, adapter: "custom_uxp_v2" },
    document,
    selection,
    layers,
    artboards,
    zoom: message.zoom,
    tool: message.tool,
    captured_at: capturedAt.toISOString(),
  };
}

async function body(req, limit = MAX_FRAME_BYTES) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw new Error("payload_too_large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function stateAgeMs() {
  return latestStateRecord ? Math.max(0, Date.now() - latestStateRecord.received_at_ms) : null;
}

function maxStateAge(value) {
  if (value === null || value === "") return DEFAULT_STATE_MAX_AGE_MS;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_STATE_MAX_AGE_MS;
  return Math.min(60000, Math.max(100, Math.round(parsed)));
}

function stateEnvelope(maxAgeMs = DEFAULT_STATE_MAX_AGE_MS) {
  if (!latestStateRecord) {
    return { ok: false, state: null, revision: 0, received_at: null, age_ms: null, stale: true, max_age_ms: maxAgeMs };
  }
  const ageMs = stateAgeMs();
  return {
    ok: true,
    state: latestStateRecord.state,
    revision: latestStateRecord.revision,
    received_at: latestStateRecord.received_at,
    age_ms: ageMs,
    stale: ageMs > maxAgeMs,
    max_age_ms: maxAgeMs,
  };
}

function health() {
  const ageMs = stateAgeMs();
  return {
    ok: true,
    node_proxy_running: true,
    websocket_enabled: true,
    ...status,
    has_state: Boolean(latestStateRecord),
    state_revision: latestStateRecord?.revision || 0,
    state_age_ms: ageMs,
    state_stale: ageMs === null || ageMs > DEFAULT_STATE_MAX_AGE_MS,
    has_frame: Boolean(latestFrame),
    live_session: liveSession.summary(),
  };
}

function forward(message) {
  return new Promise(resolve => {
    if (!adapter || adapter.readyState !== 1) return resolve(error(message.id, -32001, "illustrator_adapter_not_connected"));
    pending.set(message.id, resolve);
    status.pending_jobs = pending.size;
    adapter.send(JSON.stringify(message));
    setTimeout(() => {
      if (pending.delete(message.id)) {
        status.pending_jobs = pending.size;
        resolve(error(message.id, -32002, "adapter_timeout"));
      }
    }, 8000);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);
  try {
    if (req.method === "GET" && url.pathname === "/health") return json(res, 200, health());
    if (req.method === "GET" && url.pathname === "/preview") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
      return res.end(`<!doctype html><meta charset="utf-8"><title>StarBridge Illustrator Preview</title><style>html,body{margin:0;background:#111;color:#ddd;font:14px system-ui;height:100%}body{display:grid;grid-template-rows:auto 1fr}header{padding:8px 12px;background:#202020}img{width:100%;height:100%;object-fit:contain;min-height:0}</style><header>Illustrator 窗口实时预览 · <span id="status">连接中</span></header><img id="frame" alt="Illustrator window preview"><script>const image=document.querySelector('#frame'),status=document.querySelector('#status');let last='';async function tick(){try{const meta=await fetch('/frame/meta',{cache:'no-store'}).then(r=>r.json());if(meta.ok&&meta.frame.at!==last){last=meta.frame.at;image.src='/frame/latest?t='+encodeURIComponent(last);status.textContent=meta.frame.width+'×'+meta.frame.height+' · '+new Date(last).toLocaleTimeString();}}catch(e){status.textContent='等待代理';}}setInterval(tick,250);tick();</script>`);
    }
    if (req.method === "GET" && url.pathname === "/session") return json(res, 200, liveSession.snapshot());
    if (req.method === "POST" && url.pathname === "/session") {
      const update = liveSession.publish(JSON.parse((await body(req, MAX_SESSION_BYTES)).toString("utf8") || "{}"));
      return json(res, 202, { ok: true, update });
    }
    if (req.method === "GET" && url.pathname === "/state") return json(res, 200, stateEnvelope(maxStateAge(url.searchParams.get("max_age_ms"))));
    if (req.method === "GET" && url.pathname === "/frame/meta") return json(res, 200, { ok: Boolean(latestFrame), frame: latestFrame ? { ...latestFrame, data: undefined } : null });
    if (req.method === "GET" && url.pathname === "/frame/latest") {
      if (!latestFrame) return json(res, 404, { ok: false, message: "frame_unavailable" });
      res.writeHead(200, { "Content-Type": latestFrame.content_type, "Cache-Control": "no-store", "X-StarBridge-Capture": "illustrator-window" });
      return res.end(latestFrame.data);
    }
    if (req.method === "POST" && url.pathname === "/capture/frame") {
      if (req.headers["x-starbridge-capture-target"] !== "illustrator-window") return json(res, 400, { ok: false, message: "desktop_capture_rejected" });
      const data = await body(req);
      const contentType = String(req.headers["content-type"] || "");
      if (!["image/jpeg", "image/png"].includes(contentType)) return json(res, 415, { ok: false, message: "frame_must_be_jpeg_or_png" });
      latestFrame = { data, content_type: contentType, bytes: data.length, width: Number(req.headers["x-frame-width"] || 0), height: Number(req.headers["x-frame-height"] || 0), at: new Date().toISOString() };
      status.capture_connected = true;
      status.last_frame_at = latestFrame.at;
      return json(res, 202, { ok: true, bytes: data.length });
    }
    if (req.method === "POST" && url.pathname === "/rpc") {
      const message = JSON.parse((await body(req, 256 * 1024)).toString("utf8"));
      const invalid = validate(message);
      if (invalid) return json(res, 200, invalid);
      liveSession.publish(rpcLiveSession({ bridge: "illustrator", message, phase: "running" }));
      const reply = await forward(message);
      liveSession.publish(rpcLiveSession({ bridge: "illustrator", message, phase: reply.error ? "failed" : "completed", errorMessage: reply.error?.message }));
      return json(res, 200, reply);
    }
    return json(res, 404, { ok: false, message: "not_found" });
  } catch (caught) {
    status.last_error = String(caught?.message || caught);
    return json(res, 400, { ok: false, message: status.last_error });
  }
});

const wss = new WebSocketServer({ noServer: true });
server.on("upgrade", (req, socket, head) => {
  if (req.url !== "/illustrator") {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, ws => wss.emit("connection", ws));
});

wss.on("connection", ws => {
  adapter = ws;
  status.adapter_connected = true;
  if (liveSession.current()) ws.send(JSON.stringify(liveSession.current()));
  let lastSequence = 0;
  ws.on("message", raw => {
    let message;
    try {
      message = JSON.parse(String(raw));
    } catch {
      status.last_error = "invalid_adapter_json";
      return;
    }
    if (message.type === "state") {
      const state = normalizeState(message);
      if (!state || state.sequence <= lastSequence) {
        status.rejected_states += 1;
        status.last_error = state ? "non_monotonic_state_sequence" : "invalid_or_unsafe_state_v2";
        return;
      }
      lastSequence = state.sequence;
      const receivedAt = new Date();
      stateRevision += 1;
      latestStateRecord = { state, revision: stateRevision, received_at: receivedAt.toISOString(), received_at_ms: receivedAt.getTime() };
      status.last_state_at = latestStateRecord.received_at;
      status.last_error = null;
      return;
    }
    const done = pending.get(message.id);
    if (done) {
      pending.delete(message.id);
      status.pending_jobs = pending.size;
      done(message);
    }
  });
  ws.on("close", () => {
    if (adapter === ws) {
      adapter = null;
      status.adapter_connected = false;
    }
  });
});

server.listen(PORT, "127.0.0.1");
