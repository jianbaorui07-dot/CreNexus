import http from "node:http";
import { URL } from "node:url";

let WebSocketServer = null;
try {
  ({ WebSocketServer } = await import("ws"));
} catch (_error) {
  WebSocketServer = null;
}

const PORT = Number(process.env.STARBRIDGE_PHOTOSHOP_PROXY_PORT || 8971);
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
  if (message.params !== undefined && (typeof message.params !== "object" || message.params === null || Array.isArray(message.params))) {
    return rpcError(message.id, -32602, "params_must_be_an_object");
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
    for await (const chunk of request) {
      chunks.push(chunk);
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
    if (!request.url?.startsWith("/uxp")) {
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
        state.photoshop_host = message.photoshop_host || state.photoshop_host || {};
        recordEvent("uxp_registered", { photoshop_host: state.photoshop_host });
        return;
      }
      if (message.result?.photoshop_host) {
        state.photoshop_host = message.result.photoshop_host;
        state.photoshop_host_seen = true;
      }
      if (message.error?.message) {
        state.last_error = message.error.message;
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
      }
      state.uxp_client_connected = false;
      recordEvent("uxp_disconnected");
    });
  });
}

server.listen(PORT, "127.0.0.1");
recordEvent("node_proxy_started", { port: PORT, websocket_enabled: Boolean(WebSocketServer) });
