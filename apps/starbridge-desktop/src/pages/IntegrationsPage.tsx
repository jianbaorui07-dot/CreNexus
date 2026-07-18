import { useState } from "react";

import type { StarBridgeClient } from "../services/client";
import type {
  ConnectionOverview,
  CreativeApplicationConnection,
  CreativeApplicationPairingState,
  CreativeApplicationState,
} from "../types/api";

interface IntegrationsPageProps {
  client: StarBridgeClient;
  connections: ConnectionOverview | null;
  loading: boolean;
  error: string;
  onRefresh: () => Promise<void>;
  onRestartBridge: () => Promise<void>;
}

const APPLICATION_STATE: Record<CreativeApplicationState, string> = {
  not_installed: "未找到",
  installed: "已安装",
  running: "运行中",
  bridge_ready: "桥接可用",
  unavailable: "待重试",
};

const APPLICATION_PAIRING_STATE: Record<CreativeApplicationPairingState, string> = {
  not_available: "不可配对",
  open_required: "需要打开软件",
  ready_to_pair: "等待配对",
  paired: "桥接已连接",
  paired_limited: "已配对 · 仅检测",
  reconnect_required: "需要重连",
  unavailable: "检测失败",
};

function actionError(error: unknown) {
  return error instanceof Error ? error.message : "连接操作未完成，请重新检测。";
}

export function IntegrationsPage({
  client,
  connections,
  loading,
  error,
  onRefresh,
  onRestartBridge,
}: IntegrationsPageProps) {
  const [busy, setBusy] = useState(false);
  const [busyApplication, setBusyApplication] = useState("");
  const [message, setMessage] = useState("");

  const pairingCode = connections?.codex.pairing_code ?? "--------";
  const pairingPrompt = `请调用 StarBridge MCP 工具 starbridge.desktop_pair，参数 pairing_code="${pairingCode}"、dry_run=false、confirm_pairing=true、confirm_write=true。完成后告诉我关联结果；不要读取或输出任何 Codex 登录凭据。`;

  const installAndOpen = async () => {
    setBusy(true);
    setMessage("");
    try {
      if (!connections?.codex.connector_configured) {
        await client.installCodexConnector(true);
      }
      await client.openCodexPairing(pairingCode);
      setMessage("已打开新的 Codex 任务。请发送预填的关联指令，StarBridge 会自动等待结果。");
      await onRefresh();
    } catch (reason) {
      setMessage(actionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(pairingPrompt);
      setMessage("关联指令已复制。请粘贴到一个已加载 StarBridge MCP 的新 Codex 任务中并发送。");
    } catch {
      setMessage("无法写入剪贴板。请点击“打开 Codex 完成配对”。");
    }
  };

  const resetPairing = async () => {
    setBusy(true);
    setMessage("");
    try {
      await client.resetCodexConnection(true);
      await onRefresh();
      setMessage("已轮换配对码，旧 Codex 任务不能再关联本次桌面会话。");
    } catch (reason) {
      setMessage(actionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const restartBridge = async () => {
    setBusy(true);
    setMessage("");
    try {
      await onRestartBridge();
      setMessage("正在重启 StarBridge 本地桥接。重启后需要重新关联 Codex。外部创意软件不会被关闭。");
    } catch (reason) {
      setMessage(actionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const updateApplicationPairing = async (
    application: CreativeApplicationConnection,
    action: "pair" | "reconnect" | "disconnect",
  ) => {
    setBusyApplication(application.id);
    setMessage("");
    try {
      const result = action === "pair"
        ? await client.pairCreativeApplication(application.id)
        : action === "reconnect"
          ? await client.reconnectCreativeApplication(application.id)
          : await client.disconnectCreativeApplication(application.id);
      await onRefresh();
      if (action === "disconnect") {
        setMessage(`${application.name} 已解除配对；软件仍保持原样运行。`);
      } else if (result.pairing_state === "paired") {
        setMessage(`${application.name} 配对成功，只读桥接握手已通过。`);
      } else {
        setMessage(`${application.name} 已配对；当前仅提供存在性检测和任务路由。`);
      }
    } catch (reason) {
      setMessage(actionError(reason));
    } finally {
      setBusyApplication("");
    }
  };

  const codexState = connections?.codex.state ?? "error";
  return (
    <div className="standard-page connection-center">
      <header className="page-intro">
        <div>
          <span className="page-kicker">连接中心</span>
          <h2>先关联 Codex，再连接本机创意软件</h2>
          <p>
            每次打开 StarBridge 都会创建新的本地配对会话。只有当前 Codex 完成关联后，制图入口才会开放；软件检测不会读取账号、素材或项目内容。
          </p>
        </div>
        <span className={connections?.drawing_enabled ? "local-badge" : "connection-required-badge"}>
          {connections?.drawing_enabled ? "Codex 已关联" : "制图等待关联"}
        </span>
      </header>

      <section className={`codex-connection-card codex-state-${codexState}`}>
        <div className="codex-connection-heading">
          <span className="integration-mark codex-mark">Cx</span>
          <div>
            <span className="connection-eyebrow">必需连接 · 当前桌面会话</span>
            <h3>Codex</h3>
            <p>{connections?.codex.message ?? "正在读取 Codex 连接状态。"}</p>
          </div>
          <span className={`state-label connection-${codexState}`}>
            {connections?.codex.session_paired
              ? "已关联"
              : connections?.codex.connector_configured
                ? "等待配对"
                : connections?.codex.app_available
                  ? "需要连接器"
                  : "未找到"}
          </span>
        </div>

        <div className="connection-steps" aria-label="Codex 连接步骤">
          <div className={connections?.codex.app_available ? "is-complete" : ""}>
            <span>1</span><strong>找到 Codex</strong><small>{connections?.codex.app_available ? "可打开" : "等待安装"}</small>
          </div>
          <div className={connections?.codex.connector_configured ? "is-complete" : ""}>
            <span>2</span><strong>本地 MCP</strong><small>{connections?.codex.connector_configured ? "已配置" : "需要确认安装"}</small>
          </div>
          <div className={connections?.codex.session_paired ? "is-complete" : ""}>
            <span>3</span><strong>本次会话</strong><small>{connections?.codex.session_paired ? "关联成功" : "等待 Codex 确认"}</small>
          </div>
        </div>

        {!connections?.codex.session_paired ? (
          <div className="pairing-panel">
            <div>
              <span>当前配对码</span>
              <code>{pairingCode}</code>
              <small>15 分钟内有效；重启桥接或重新生成后旧码失效。</small>
            </div>
            <div className="actions">
              <button
                type="button"
                className="primary"
                disabled={busy || !connections?.codex.app_available}
                onClick={() => void installAndOpen()}
              >
                {connections?.codex.connector_configured ? "打开 Codex 完成配对" : "安装连接器并打开 Codex"}
              </button>
              <button type="button" className="secondary" disabled={busy} onClick={() => void copyPrompt()}>
                复制关联指令
              </button>
            </div>
          </div>
        ) : (
          <div className="paired-summary">
            <span aria-hidden="true">✓</span>
            <div><strong>当前 Codex 会话已验证</strong><p>制图功能已开放；每项写入和导出操作仍保留独立确认。</p></div>
          </div>
        )}

        <div className="connection-card-actions">
          <button type="button" className="quiet-button" disabled={busy} onClick={() => void onRefresh()}>
            {loading ? "正在检测" : "重新检测"}
          </button>
          <button type="button" className="quiet-button" disabled={busy} onClick={() => void resetPairing()}>
            重新生成配对码
          </button>
          <button type="button" className="quiet-button danger-action" disabled={busy} onClick={() => void restartBridge()}>
            重启本地桥接
          </button>
        </div>
      </section>

      {error ? <p className="connection-error" role="alert">{error}</p> : null}
      {message ? <p className="page-message" role="status">{message}</p> : null}

      <div className="connection-section-heading">
        <div><span>本机软件</span><h3>独立配对、重连与桥接状态</h3></div>
        <button type="button" className="secondary" disabled={loading || busy} onClick={() => void onRefresh()}>
          {loading ? "检测中…" : "重新检测全部"}
        </button>
      </div>
      <div className="integration-list">
        {(connections?.applications ?? []).map((application) => (
          <article key={application.id} className={application.paired ? "application-is-paired" : ""}>
            <span className="integration-mark">{application.mark}</span>
            <div className="application-connection-copy">
              <div className="application-title-line">
                <h3>{application.name}</h3>
                <span className={`state-label application-${application.state}`}>
                  {APPLICATION_STATE[application.state]}
                </span>
              </div>
              <p>{application.message}</p>
              <div className="application-capabilities" aria-label={`${application.name} 可用能力`}>
                {application.capabilities.map((capability) => <span key={capability}>{capability}</span>)}
              </div>
            </div>
            <div className="application-pairing-control">
              <span className={`pairing-state pairing-${application.pairing_state}`}>
                {APPLICATION_PAIRING_STATE[application.pairing_state]}
              </span>
              <div className="application-actions">
                {application.paired || application.pairing_state === "reconnect_required" ? (
                  <>
                    <button
                      type="button"
                      className="quiet-button"
                      disabled={!application.running || Boolean(busyApplication)}
                      onClick={() => void updateApplicationPairing(application, "reconnect")}
                    >
                      {busyApplication === application.id ? "连接中…" : "重新连接"}
                    </button>
                    <button
                      type="button"
                      className="quiet-button danger-action"
                      disabled={Boolean(busyApplication)}
                      onClick={() => void updateApplicationPairing(application, "disconnect")}
                    >
                      解除配对
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="secondary application-pair-button"
                    disabled={
                      !connections?.codex.session_paired
                      || !application.running
                      || Boolean(busyApplication)
                    }
                    onClick={() => void updateApplicationPairing(application, "pair")}
                  >
                    {busyApplication === application.id
                      ? "配对中…"
                      : !connections?.codex.session_paired
                        ? "先配对 Codex"
                        : application.running
                          ? "开始配对"
                          : application.installed
                            ? "请先打开软件"
                            : "未安装"}
                  </button>
                )}
              </div>
            </div>
          </article>
        ))}
        {!connections?.applications.length ? (
          <article className="connection-placeholder">
            <span className="integration-mark">…</span><div><h3>正在检测本机软件</h3><p>只读取固定的安装和进程线索。</p></div><span className="state-label">检测中</span>
          </article>
        ) : null}
      </div>
      <p className="truth-note">
        “桥接已连接”表示只读 COM 或回环 HTTP 握手已响应；“已配对 · 仅检测”只表示当前运行会话已确认，不代表能够自动编辑。重新连接不会关闭、启动或重启客户正在编辑的外部软件。
      </p>
    </div>
  );
}
