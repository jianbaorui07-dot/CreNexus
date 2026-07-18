import { rpcError, rpcResult, validateRequest } from "./protocol.js";

export class BridgeClient {
  constructor({adapter, url = "ws://127.0.0.1:8972/illustrator", intervalMs = 500, onStatus = () => {}, onSession = () => {}}) {
    this.adapter = adapter; this.url = url; this.intervalMs = Math.max(200, intervalMs); this.onStatus = onStatus; this.onSession = onSession;
    this.socket = null; this.timer = null; this.reconnectTimer = null;
  }
  connect() {
    if (this.socket) return;
    try {
      const socket = new WebSocket(this.url); this.socket = socket; this.onStatus("connecting");
      socket.addEventListener("open", () => { this.onStatus("connected"); this.startStateLoop(); this.pushState(); });
      socket.addEventListener("message", async (event) => {
        let message; try { message = JSON.parse(String(event.data || "{}")); } catch (_error) { this.send(rpcError(null, -32700, "parse_error")); return; }
        if (message?.type === "codex_session") { this.onSession(message); return; }
        const invalid = validateRequest(message); if (invalid) { this.send(rpcError(message?.id, -32602, invalid)); return; }
        try { const result = await this.adapter.execute(message.method, message.params); this.send(rpcResult(message.id, result)); await this.pushState(); }
        catch (error) { this.send(rpcError(message.id, -32000, String(error?.message || error))); }
      });
      socket.addEventListener("close", () => { this.stopStateLoop(); this.socket = null; this.onStatus("disconnected"); this.scheduleReconnect(); });
      socket.addEventListener("error", () => this.onStatus("error"));
    } catch (_error) { this.socket = null; this.onStatus("error"); this.scheduleReconnect(); }
  }
  disconnect() { this.stopStateLoop(); if (this.socket) this.socket.close(); this.socket = null; }
  reconnect() { this.disconnect(); setTimeout(() => this.connect(), 100); }
  scheduleReconnect() { if (this.reconnectTimer) return; this.reconnectTimer = setTimeout(() => {this.reconnectTimer = null; this.connect();}, 2000); }
  startStateLoop() { this.stopStateLoop(); this.timer = setInterval(() => this.pushState(), this.intervalMs); }
  stopStateLoop() { if (this.timer) clearInterval(this.timer); this.timer = null; }
  send(payload) { if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload)); }
  async pushState() { if (this.socket?.readyState !== WebSocket.OPEN) return; try { const state = this.adapter.state(); this.send(state); this.onStatus("synced", state); } catch (error) { this.onStatus("state_error", {message: String(error?.message || error)}); } }
}
