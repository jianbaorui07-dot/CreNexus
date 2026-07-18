import { BridgeClient } from "./bridge-client.js";
import { IllustratorHostAdapter } from "./host-adapter.js";

const elements = {
  connection: document.querySelector("#connection"),
  host: document.querySelector("#host"),
  document: document.querySelector("#document"),
  selection: document.querySelector("#selection"),
  synced: document.querySelector("#synced"),
  message: document.querySelector("#message"),
  sessionCard: document.querySelector("#session-card"),
  sessionPhase: document.querySelector("#session-phase"),
  sessionStep: document.querySelector("#session-step"),
  sessionMessage: document.querySelector("#session-message"),
  sessionProgress: document.querySelector("#session-progress"),
  progressTrack: document.querySelector(".progress-track"),
  sessionMode: document.querySelector("#session-mode"),
  sessionTime: document.querySelector("#session-time"),
};

const adapter = new IllustratorHostAdapter();

function onStatus(status, detail = {}) {
  const labels = { connecting: "连接中", connected: "已连接", disconnected: "已断开", error: "连接异常", synced: "已连接" };
  elements.connection.textContent = labels[status] || status;
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

const phaseLabels = {
  queued: "已排队",
  running: "Codex 正在工作",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  needs_user: "等待确认",
};

function onSession(update) {
  const progress = Math.max(0, Math.min(100, Number(update?.progress || 0)));
  elements.sessionCard.dataset.phase = String(update?.phase || "idle");
  elements.sessionPhase.textContent = phaseLabels[update?.phase] || String(update?.phase || "等待任务");
  elements.sessionStep.textContent = `${update?.step?.index || 0}/${update?.step?.total || 0} · ${update?.step?.label || ""}`;
  elements.sessionMessage.textContent = String(update?.message || "");
  elements.sessionMode.textContent = update?.mode === "computer_use" ? "界面操作" : "结构化命令";
  elements.sessionTime.textContent = update?.at ? new Date(update.at).toLocaleTimeString() : "—";
  elements.sessionProgress.style.width = `${progress}%`;
  elements.progressTrack.setAttribute("aria-valuenow", String(progress));
}

const client = new BridgeClient({ adapter, onStatus, onSession });
document.querySelector("#reconnect").addEventListener("click", () => client.reconnect());
document.querySelector("#push-state").addEventListener("click", () => client.pushState());
client.connect();
