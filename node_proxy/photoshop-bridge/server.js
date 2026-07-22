import http from "node:http";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { URL } from "node:url";
import { fileURLToPath } from "node:url";
import { createLiveSessionStore, rpcLiveSession } from "../live-session.js";

let WebSocketServer = null;
try {
  ({ WebSocketServer } = await import("ws"));
} catch (_error) {
  WebSocketServer = null;
}

const PORT = Number(process.env.STARBRIDGE_PHOTOSHOP_PROXY_PORT || 8971);
const MAX_RPC_BYTES = 256 * 1024;
const MAX_SOURCE_ASSET_BYTES = 512 * 1024 * 1024;
const MAX_SESSION_BYTES = 32 * 1024;
const PROXY_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(PROXY_DIR, "../..");
const APP_DATA_CONFIGURED = process.env.STARBRIDGE_APP_DATA_DIR ||
  (process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "StarBridge") : null);
const APP_DATA_ROOT = APP_DATA_CONFIGURED ? path.resolve(APP_DATA_CONFIGURED) : null;
const APP_PROJECTS_ROOT = APP_DATA_ROOT ? path.join(APP_DATA_ROOT, "projects") : null;
const APP_ARTIFACTS_ROOT = APP_DATA_ROOT ? path.join(APP_DATA_ROOT, "artifacts") : null;
const OUTPUT_ROOTS = [
  path.resolve(REPO_ROOT, "sandbox"),
  path.resolve(REPO_ROOT, "output"),
  path.resolve(REPO_ROOT, "examples/output/photoshop"),
  ...(APP_ARTIFACTS_ROOT ? [APP_ARTIFACTS_ROOT] : []),
];
const ALLOWED_METHODS = new Set([
  "starbridge.ping",
  "ps.document.info",
  "ps.layers.list",
  "ps.preview.export",
  "ps.camera_raw.tune",
  "ps.batchplay.validate.local",
  "ps.batchplay.execute_confirmed",
  "ps.production.execute_confirmed",
]);
const PRODUCTION_OUTPUT_EXTENSIONS = new Map([
  ["png", ".png"],
  ["jpeg", ".jpg"],
  ["psd", ".psd"],
  ["subject", ".png"],
]);
const PRODUCTION_OUTPUT_BASENAMES = new Map([
  ["png", "photoshop-preview.png"],
  ["jpeg", "photoshop-preview.jpg"],
  ["psd", "photoshop-copy.psd"],
  ["subject", "photoshop-subject.png"],
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
const timedOutProductionStaging = new Map();
let currentClient = null;
const liveSession = createLiveSessionStore("photoshop", (update) => {
  if (currentClient?.readyState === 1) currentClient.send(JSON.stringify(update));
});

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
    live_session: liveSession.summary(),
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

function fileSha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function canonicalExistingPathInside(rawPath, root) {
  if (!root) return null;
  try {
    const canonicalRoot = fs.realpathSync(root);
    const canonicalPath = fs.realpathSync(path.resolve(rawPath));
    return pathInside(canonicalPath, canonicalRoot) ? canonicalPath : null;
  } catch (_error) {
    return null;
  }
}

function canonicalNewPathInside(rawPath, root) {
  if (!root) return null;
  try {
    const candidate = path.resolve(rawPath);
    if (fs.existsSync(candidate)) return null;
    const canonicalRoot = fs.realpathSync(root);
    const canonicalParent = fs.realpathSync(path.dirname(candidate));
    if (!pathInside(canonicalParent, canonicalRoot)) return null;
    const canonicalPath = path.join(canonicalParent, path.basename(candidate));
    return pathInside(canonicalPath, canonicalRoot) ? canonicalPath : null;
  } catch (_error) {
    return null;
  }
}

function normalizeManagedSource(rawPath, expectedHash) {
  if (!APP_PROJECTS_ROOT) return null;
  if (typeof rawPath !== "string" || !rawPath.trim() || !path.isAbsolute(rawPath)) return null;
  const candidate = canonicalExistingPathInside(rawPath, APP_PROJECTS_ROOT);
  if (!candidate || ![".png", ".jpg", ".jpeg"].includes(path.extname(candidate).toLowerCase())) return null;
  const sourceStat = fs.statSync(candidate);
  if (!sourceStat.isFile() || sourceStat.size > MAX_SOURCE_ASSET_BYTES) return null;
  if (!/^[0-9a-f]{64}$/.test(String(expectedHash || "")) || fileSha256(candidate) !== expectedHash) return null;
  return candidate;
}

function normalizeProductionOutputs(rawOutputs, jobId) {
  if (!APP_ARTIFACTS_ROOT) return null;
  if (!rawOutputs || typeof rawOutputs !== "object" || Array.isArray(rawOutputs)) return null;
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(String(jobId || ""))) return null;
  const keys = Object.keys(rawOutputs);
  if (keys.length < 1 || keys.length > PRODUCTION_OUTPUT_EXTENSIONS.size || keys.some((key) => !PRODUCTION_OUTPUT_EXTENSIONS.has(key))) return null;
  const finalOutputs = {};
  const stagingOutputs = {};
  for (const key of keys) {
    const rawCandidate = String(rawOutputs[key] || "");
    const expectedExtension = PRODUCTION_OUTPUT_EXTENSIONS.get(key);
    const expectedBasename = PRODUCTION_OUTPUT_BASENAMES.get(key);
    if (!path.isAbsolute(rawCandidate) || path.extname(rawCandidate).toLowerCase() !== expectedExtension || path.basename(rawCandidate) !== expectedBasename) return null;
    const candidate = canonicalNewPathInside(rawCandidate, APP_ARTIFACTS_ROOT);
    if (!candidate) return null;
    const canonicalArtifactsRoot = fs.realpathSync(APP_ARTIFACTS_ROOT);
    const relativeParts = path.relative(canonicalArtifactsRoot, candidate).split(path.sep);
    if (relativeParts.length !== 3 || relativeParts[1] !== jobId) return null;
    const staging = path.join(path.dirname(candidate), `.${path.basename(candidate, expectedExtension)}.${jobId}.part${expectedExtension}`);
    if (!canonicalNewPathInside(staging, APP_ARTIFACTS_ROOT) && !canonicalExistingPathInside(staging, APP_ARTIFACTS_ROOT)) return null;
    if (fs.existsSync(staging)) fs.rmSync(staging, { force: true });
    finalOutputs[key] = candidate;
    stagingOutputs[key] = staging;
  }
  return { finalOutputs, stagingOutputs };
}

function cleanupProductionStaging(stagingOutputs) {
  if (!APP_ARTIFACTS_ROOT) return;
  for (const candidate of Object.values(stagingOutputs || {})) {
    const canonical = typeof candidate === "string"
      ? canonicalExistingPathInside(candidate, APP_ARTIFACTS_ROOT)
      : null;
    if (canonical) {
      fs.rmSync(canonical, { force: true });
    }
  }
}

function finalizeProductionReply(reply, params) {
  const stagingOutputs = params.staging_outputs || {};
  const finalOutputs = params.outputs || {};
  if (!reply?.result?.executed || reply.result.success === false) {
    cleanupProductionStaging(stagingOutputs);
    return reply;
  }
  const promoted = [];
  try {
    const outputBasenames = {};
    const outputHashes = {};
    for (const key of Object.keys(finalOutputs)) {
      const staging = canonicalExistingPathInside(stagingOutputs[key], APP_ARTIFACTS_ROOT);
      const finalPath = canonicalNewPathInside(finalOutputs[key], APP_ARTIFACTS_ROOT);
      if (!staging || !finalPath || !fs.statSync(staging).isFile()) {
        throw new Error("production_output_promotion_failed");
      }
    }
    for (const key of Object.keys(finalOutputs)) {
      const staging = canonicalExistingPathInside(stagingOutputs[key], APP_ARTIFACTS_ROOT);
      const finalPath = canonicalNewPathInside(finalOutputs[key], APP_ARTIFACTS_ROOT);
      if (!staging || !finalPath) throw new Error("production_output_promotion_failed");
      fs.renameSync(staging, finalPath);
      promoted.push({ staging, finalPath });
      outputBasenames[key] = path.basename(finalPath);
      outputHashes[key] = fileSha256(finalPath);
    }
    reply.result.output_basenames = outputBasenames;
    reply.result.output_hashes = outputHashes;
    reply.result.output_count = Object.keys(finalOutputs).length;
    delete reply.result.output_paths;
    return reply;
  } catch (_error) {
    for (const item of promoted.reverse()) {
      try {
        if (fs.existsSync(item.finalPath) && !fs.existsSync(item.staging)) fs.renameSync(item.finalPath, item.staging);
      } catch (_rollbackError) {
        const exactPromotedFile = canonicalExistingPathInside(item.finalPath, APP_ARTIFACTS_ROOT);
        if (exactPromotedFile) fs.rmSync(exactPromotedFile, { force: true });
      }
    }
    cleanupProductionStaging(stagingOutputs);
    return rpcError(reply?.id, -32020, "production_output_promotion_failed");
  }
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
  if (pending.has(message.id) || timedOutProductionStaging.has(message.id)) {
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
  if (message.method === "ps.production.execute_confirmed") {
    if (params.confirm_write !== true) {
      return rpcError(message.id, -32010, "confirm_write=true_required");
    }
    const sourcePath = normalizeManagedSource(params.source_path, String(params.source_sha256 || ""));
    const outputs = normalizeProductionOutputs(params.outputs, params.job_id);
    if (!sourcePath) return rpcError(message.id, -32602, "source_path_outside_managed_projects_or_hash_mismatch");
    if (!outputs) return rpcError(message.id, -32602, "outputs_outside_managed_artifacts_or_already_exist");
    if (Boolean(params.export_subject) !== Object.hasOwn(outputs.finalOutputs, "subject")) {
      cleanupProductionStaging(outputs.stagingOutputs);
      return rpcError(message.id, -32602, "subject_output_must_match_export_subject");
    }
    const canvas = params.canvas || {};
    const adjustment = params.adjustment || {};
    const boundedInteger = (value, minimum, maximum) => Number.isInteger(value) && value >= minimum && value <= maximum;
    if (canvas.resize === true && (!boundedInteger(canvas.width, 64, 8192) || !boundedInteger(canvas.height, 64, 8192))) {
      cleanupProductionStaging(outputs.stagingOutputs);
      return rpcError(message.id, -32602, "canvas_dimensions_out_of_range");
    }
    if (!boundedInteger(adjustment.brightness ?? 0, -150, 150) || !boundedInteger(adjustment.contrast ?? 0, -100, 100) || !boundedInteger(adjustment.saturation ?? 0, -100, 100)) {
      cleanupProductionStaging(outputs.stagingOutputs);
      return rpcError(message.id, -32602, "adjustment_out_of_range");
    }
    params.source_path = sourcePath;
    params.outputs = outputs.finalOutputs;
    params.staging_outputs = outputs.stagingOutputs;
    params.managed_source_verified = true;
    params.safe_roots_verified = true;
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
    const timeoutMs = message.method === "ps.production.execute_confirmed" ? 55_000 : 8_000;
    setTimeout(() => {
      if (pending.has(message.id)) {
        pending.delete(message.id);
        state.pending_jobs = pending.size;
        state.last_error = "uxp_timeout";
        recordEvent("rpc_timeout", { id: message.id, method: message.method });
        if (message.method === "ps.production.execute_confirmed") {
          timedOutProductionStaging.set(message.id, message.params?.staging_outputs || {});
          setTimeout(() => {
            cleanupProductionStaging(timedOutProductionStaging.get(message.id));
            timedOutProductionStaging.delete(message.id);
          }, 5 * 60_000);
        }
        resolve(rpcError(message.id, -32002, "uxp_timeout"));
      }
    }, timeoutMs);
  });
}

async function readBody(request, limit) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > limit) throw new Error("payload_too_large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
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
  if (request.method === "GET" && url.pathname === "/session") {
    sendJson(response, 200, liveSession.snapshot());
    return;
  }
  if (request.method === "POST" && url.pathname === "/session") {
    try {
      const update = liveSession.publish(JSON.parse((await readBody(request, MAX_SESSION_BYTES)).toString("utf-8") || "{}"));
      recordEvent("session_published", { session_id: update.session_id, phase: update.phase });
      sendJson(response, 202, { ok: true, update });
    } catch (error) {
      recordEvent("session_rejected", { reason: String(error?.message || error) });
      sendJson(response, 400, { ok: false, message: String(error?.message || error) });
    }
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
    liveSession.publish(rpcLiveSession({ bridge: "photoshop", message, phase: "running" }));
    let reply = await rpcToUxp(message);
    if (message.method === "ps.production.execute_confirmed") {
      reply = finalizeProductionReply(reply, message.params || {});
    }
    liveSession.publish(
      rpcLiveSession({
        bridge: "photoshop",
        message,
        phase: reply.error ? "failed" : "completed",
        errorMessage: reply.error?.message,
      }),
    );
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
    if (liveSession.current()) ws.send(JSON.stringify(liveSession.current()));
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
      } else if (timedOutProductionStaging.has(message.id)) {
        cleanupProductionStaging(timedOutProductionStaging.get(message.id));
        timedOutProductionStaging.delete(message.id);
        recordEvent("late_production_reply_cleaned", { id: message.id });
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
