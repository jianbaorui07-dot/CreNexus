import { BridgeClient } from "./bridge-client.js";
import { IllustratorHostAdapter } from "./host-adapter.js";

const elements = {
  connection: document.querySelector("#connection"),
  host: document.querySelector("#host"),
  document: document.querySelector("#document"),
  selection: document.querySelector("#selection"),
  synced: document.querySelector("#synced"),
  message: document.querySelector("#message"),
};

const adapter = new IllustratorHostAdapter();

function onStatus(status, detail = {}) {
  elements.connection.textContent = status;
  if (status === "synced") {
    elements.host.textContent = `${detail.host?.version || "unknown"} / ${detail.host?.adapter || "custom"}`;
    elements.document.textContent = detail.document ? "有活动文档（名称已脱敏）" : "无活动文档";
    elements.selection.textContent = String(detail.selection?.length || 0);
    elements.synced.textContent = new Date(detail.captured_at).toLocaleTimeString();
    elements.message.textContent = `对象 ${detail.document?.page_items || 0} · 图层 ${detail.layers?.length || 0} · 画板 ${detail.artboards?.length || 0}`;
  } else if (status.endsWith("error")) {
    elements.message.textContent = detail.message || status;
  }
}

const client = new BridgeClient({ adapter, onStatus });
document.querySelector("#reconnect").addEventListener("click", () => client.reconnect());
document.querySelector("#push-state").addEventListener("click", () => client.pushState());
client.connect();
