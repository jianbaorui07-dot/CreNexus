import http from "node:http";
import path from "node:path";
import { URL } from "node:url";
import { fileURLToPath } from "node:url";

let WebSocketServer = null;
try {
  ({ WebSocketServer } = await import("ws"));
} catch (_error) {
  WebSocketServer = null;
}

const PORT = Number(process.env.STARBRIDGE_PHOTOSHOP_PROXY_PORT || 8971);
const MAX_RPC_BYTES = 256 * 1024;
const PROXY_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(PROXY_DIR, "../..");
const OUTPUT_ROOTS = [
  path.resolve(REPO_ROOT, "sandbox"),
  path.resolve(REPO_ROOT, "output"),
  path.resolve(REPO_ROOT, "examples/output/photoshop"),
];
const ALLOWED_METHODS = new Set([
  "starbridge.ping",
  "ps.document.info",
  "ps.layers.list",
  "ps.preview.export",
  "ps.camera_raw.tune",
  "ps.batchplay.validate.local",
  "ps.batchplay.execute_confirmed",
]);
const state = {
  node_proxy_running: true,
  uxp_client_connected: false,
  photoshop_host_seen: false,
  last_ping_at: null,
  pending_jobs: 0,
  photoshop_host: {},
  last_client_registered_at: null,
  last_error: null,
  event_log: [],
};

const pending = new Map();
let currentClient = null;

function recordEvent(type, details = {}) {
  const event = {
    type,
    at: new Date().toISOString(),
    ...details,
  };
  state.event_log.push(event);
  if (state.event_log.length > 50) {
    state.event_log.shift();
  }
  return event;
}

function sendJson(response, status, payload) {
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(payload));
}

function rpcError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) {
    error.data = data;
  }
  return { jsonrpc: "2.0", id: id ?? null, error };
}

function healthPayload() {
  return {
    ok: true,
    node_proxy_running: true,
    uxp_client_connected: state.uxp_client_connected,
    photoshop_host_seen: state.photoshop_host_seen,
    last_ping_at: state.last_ping_at,
    pending_jobs: state.pending_jobs,
    last_client_registered_at: state.last_client_registered_at,
    last_error: state.last_error,
    websocket_enabled: Boolean(WebSocketServer),
  };
}

function bridgeStatusPayload() {
  return {
    ...healthPayload(),
    photoshop_host: state.photoshop_host,
  };
}

function pathInside(candidate, root) {
  const relative = path.relative(root, candidate);
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

function normalizeSandboxOutput(rawPath) {
  if (typeof rawPath !== "string" || !rawPath.trim() || !path.isAbsolute(rawPath)) {
    return null;
  }
  const candidate = path.resolve(rawPath);
  if (path.extname(candidate).toLowerCase() !== ".png") {
    return null;
  }
  return OUTPUT_ROOTS.some((root) => pathInside(candidate, root)) ? candidate : null;
}

function safeHostInfo(value) {
  const version = String(value?.version || "unknown");
  return {
    app: "Photoshop",
    version: /^[0-9A-Za-z._ -]{1,32}$/.test(version) ? version : "unknown",
  };
}

function validateRpcMessage(message) {
  if (!message || typeof message !== "object" || Array.isArray(message)) {
    return rpcError(null, -32600, "invalid_request_object");
  }
  if (message.jsonrpc !== "2.0") {
    return rpcError(message.id, -32600, "jsonrpc_must_be_2_0");
  }
  if (typeof message.method !== "string" || !message.method.trim()) {
    return rpcError(message.id, -32600, "method_must_be_a_string");
  }
  if (!ALLOWED_METHODS.has(message.method)) {
    return rpcError(message.id, -32601, "method_not_allowed");
  }
  if (message.params !== undefined && (typeof message.params !== "object" || message.params === null || Array.isArray(message.params))) {
    return rpcError(message.id, -32602, "params_must_be_an_object");
  }
  const params = message.params || {};
  const descriptors = params.descriptors || (params.descriptor ? [params.descriptor] : []);
  if (Array.isArray(descriptors) && descriptors.length > 32) {
    return rpcError(message.id, -32602, "descriptor_count_out_of_range");
  }
  if (pending.has(message.id)) {
    return rpcError(message.id, -32600, "duplicate_request_id");
  }
  if (message.method === "ps.preview.export" && params.dry_run !== true) {
    if (params.confirm_write !== true) {
      return rpcError(message.id, -32010, "confirm_write=true_required");
    }
    const outputPath = normalizeSandboxOutput(params.output_path);
    if (!outputPath) {
      return rpcError(message.id, -32602, "output_path_outside_sandbox");
    }
    params.output_path = outputPath;
    params.sandbox_verified = true;
  }
  if (message.method === "ps.batchplay.execute_confirmed") {
    if (params.confirm_write !== true) {
      return rpcError(message.id, -32010, "confirm_write=true_required");
    }
    if (!Array.isArray(descriptors) || descriptors.length < 1) {
      return rpcError(message.id, -32602, "descriptors_required");
    }
    if (params.output_path) {
      const outputPath = normalizeSandboxOutput(params.output_path);
      if (!outputPath) {
        return rpcError(message.id, -32602, "output_path_outside_sandbox");
      }
      params.output_path = outputPath;
    }
    params.sandbox_verified = true;
  }
  if (message.method === "ps.camera_raw.tune" && params.dry_run === false) {
    if (params.confirm_apply !== true) {
      return rpcError(message.id, -32011, "confirm_apply=true_required");
    }
    if (params.output?.export_after_apply === true && params.confirm_export !== true) {
      return rpcError(message.id, -32012, "confirm_export=true_required");
    }
  }
  return null;
}

function rpcToUxp(message) {
  return new Promise((resolve) => {
    if (!currentClient || currentClient.readyState !== 1) {
      resolve(rpcError(message.id, -32001, "uxp_client_not_connected"));
      return;
    }
    pending.set(message.id, resolve);
    state.pending_jobs = pending.size;
    recordEvent("rpc_forwarded", { id: message.id, method: message.method });
    currentClient.send(JSON.stringify(message));
    setTimeout(() => {
      if (pending.has(message.id)) {
        pending.delete(message.id);
        state.pending_jobs = pending.size;
        state.last_error = "uxp_timeout";
        recordEvent("rpc_timeout", { id: message.id, method: message.method });
        resolve(rpcError(message.id, -32002, "uxp_timeout"));
      }
    }, 8000);
  });
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://127.0.0.1:${PORT}`);
  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, healthPayload());
    return;
  }
  if (request.method === "GET" && url.pathname === "/bridge/status") {
    sendJson(response, 200, bridgeStatusPayload());
    return;
  }
  if (request.method === "GET" && url.pathname === "/events") {
    sendJson(response, 200, { ok: true, events: state.event_log });
    return;
  }
  if (request.method === "POST" && url.pathname === "/rpc") {
    const chunks = [];
    let bodyBytes = 0;
    let bodyTooLarge = false;
    for await (const chunk of request) {
      bodyBytes += chunk.length;
      if (bodyBytes > MAX_RPC_BYTES) {
        bodyTooLarge = true;
        break;
      }
      chunks.push(chunk);
    }
    if (bodyTooLarge) {
      state.last_error = "rpc_payload_too_large";
      recordEvent("rpc_payload_rejected", { reason: "payload_too_large" });
      sendJson(response, 200, rpcError(null, -32013, "payload_too_large"));
      return;
    }
    let message;
    try {
      message = JSON.parse(Buffer.concat(chunks).toString("utf-8") || "{}");
    } catch (error) {
      state.last_error = "invalid_json";
      recordEvent("rpc_invalid_json");
      sendJson(response, 200, rpcError(null, -32700, "parse_error", String(error?.message || error)));
      return;
    }
    const validationError = validateRpcMessage(message);
    if (validationError) {
      state.last_error = validationError.error.message;
      recordEvent("rpc_invalid_request", { id: message?.id, reason: validationError.error.message });
      sendJson(response, 200, validationError);
      return;
    }
    const reply = await rpcToUxp(message);
    if (message.method === "starbridge.ping" && reply.result) {
      state.last_ping_at = new Date().toISOString();
      state.photoshop_host_seen = Boolean(reply.result.photoshop_host);
      state.photoshop_host = reply.result.photoshop_host || {};
    }
    sendJson(response, 200, reply);
    return;
  }
  sendJson(response, 404, { ok: false, message: "not_found" });
});

if (WebSocketServer) {
  const wss = new WebSocketServer({ noServer: true });
  server.on("upgrade", (request, socket, head) => {
    if (request.url !== "/uxp") {
      socket.destroy();
      return;
    }
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit("connection", ws, request);
    });
  });
  wss.on("connection", (ws) => {
    currentClient = ws;
    state.uxp_client_connected = true;
    ws.on("message", (data) => {
      let message;
      try {
        message = JSON.parse(String(data || "{}"));
      } catch (_error) {
        state.last_error = "invalid_uxp_json";
        recordEvent("uxp_invalid_json");
        return;
      }
      if (message.type === "register") {
        state.photoshop_host_seen = true;
        state.last_client_registered_at = new Date().toISOString();
        state.last_ping_at = new Date().toISOString();
        state.photoshop_host = safeHostInfo(message.photoshop_host);
        recordEvent("uxp_registered", { photoshop_host: state.photoshop_host });
        return;
      }
      if (message.result?.photoshop_host) {
        state.photoshop_host = safeHostInfo(message.result.photoshop_host);
        state.photoshop_host_seen = true;
      }
      if (message.error?.message) {
        state.last_error = "uxp_rpc_error";
      }
      const resolver = pending.get(message.id);
      if (resolver) {
        pending.delete(message.id);
        state.pending_jobs = pending.size;
        recordEvent("rpc_resolved", { id: message.id, ok: !message.error });
        resolver(message);
      }
    });
    ws.on("close", () => {
      if (currentClient === ws) {
        currentClient = null;
        state.uxp_client_connected = false;
      }
      recordEvent("uxp_disconnected");
    });
  });
}

server.listen(PORT, "127.0.0.1");
recordEvent("node_proxy_started", { port: PORT, websocket_enabled: Boolean(WebSocketServer) });
