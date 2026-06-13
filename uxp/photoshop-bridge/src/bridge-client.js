const DEFAULT_PROXY_URL = "ws://127.0.0.1:8971/uxp";

function nowIso() {
  return new Date().toISOString();
}

export class BridgeClient {
  constructor({ proxyUrl = DEFAULT_PROXY_URL, handlers = {} } = {}) {
    this.proxyUrl = proxyUrl;
    this.handlers = handlers;
    this.socket = null;
    this.connected = false;
    this.lastPingAt = null;
    this.reconnectTimer = null;
  }

  connect() {
    if (this.socket) {
      return;
    }
    try {
      this.socket = new WebSocket(this.proxyUrl);
      this.socket.addEventListener("open", () => {
        this.connected = true;
        this.send({
          type: "register",
          host: "photoshop",
          connectedAt: nowIso(),
          photoshop_host: this.hostInfo(),
        });
      });
      this.socket.addEventListener("close", () => {
        this.connected = false;
        this.socket = null;
        this.scheduleReconnect();
      });
      this.socket.addEventListener("message", async (event) => {
        const message = JSON.parse(String(event.data || "{}"));
        if (!message?.method) {
          return;
        }
        const handler = this.handlers[message.method];
        const replyBase = { jsonrpc: "2.0", id: message.id };
        if (!handler) {
          this.send({ ...replyBase, error: { code: -32601, message: `unknown method: ${message.method}` } });
          return;
        }
        try {
          const result = await handler(message.params || {});
          if (message.method === "starbridge.ping") {
            this.lastPingAt = nowIso();
          }
          this.send({ ...replyBase, result });
        } catch (error) {
          this.send({ ...replyBase, error: { code: -32000, message: String(error?.message || error) } });
        }
      });
    } catch (_error) {
      this.connected = false;
      this.socket = null;
      this.scheduleReconnect();
    }
  }

  hostInfo() {
    try {
      const photoshop = require("photoshop");
      return {
        app: "Photoshop",
        version: String(photoshop?.app?.version || "unknown"),
      };
    } catch (_error) {
      return { app: "Photoshop", version: "unknown" };
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) {
      return;
    }
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 2000);
  }

  send(payload) {
    if (this.socket && this.connected) {
      this.socket.send(JSON.stringify(payload));
    }
  }
}
