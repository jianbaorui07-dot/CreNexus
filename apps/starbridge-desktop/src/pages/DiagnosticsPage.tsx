import { useState } from "react";

import { SoftwareUpdatePanel } from "../components/SoftwareUpdatePanel/SoftwareUpdatePanel";
import type {
  RuntimeStatus,
  SoftwareUpdateProgress,
  SoftwareUpdateStatus,
  VersionInfo,
} from "../types/api";

interface DiagnosticsPageProps {
  status: RuntimeStatus;
  version: VersionInfo | null;
  onRestart: () => Promise<void>;
  onOpenLogs: () => Promise<string>;
  updateStatus: SoftwareUpdateStatus;
  automaticUpdateChecks: boolean;
  checkingForUpdate: boolean;
  installingUpdate: boolean;
  updateProgress: SoftwareUpdateProgress | null;
  updateMessage: string;
  updateError: string;
  onAutomaticUpdateChecksChange: (enabled: boolean) => void;
  onCheckForUpdate: () => Promise<void>;
  onInstallUpdate: () => Promise<void>;
}

export function DiagnosticsPage({
  status,
  version,
  onRestart,
  onOpenLogs,
  updateStatus,
  automaticUpdateChecks,
  checkingForUpdate,
  installingUpdate,
  updateProgress,
  updateMessage,
  updateError,
  onAutomaticUpdateChecksChange,
  onCheckForUpdate,
  onInstallUpdate,
}: DiagnosticsPageProps) {
  const [message, setMessage] = useState("");
  return (
    <div className="standard-page diagnostics-page">
      <header className="page-intro"><div><span className="page-kicker">设置与诊断</span><h2>检查本机运行状态</h2><p>普通创作页面只显示必要信息；端口、自动恢复和构建说明集中在这里。</p></div></header>
      <div className="diagnostic-grid">
        <section className="diagnostic-card"><div className="diagnostic-heading"><span className={`diagnostic-dot state-${status.state}`} /><div><h3>{status.state === "connected" ? "运行正常" : "本地服务需要处理"}</h3><p>{status.message}</p></div></div><div className="actions"><button type="button" className="primary" onClick={() => void onRestart().then(() => setMessage("已请求重新启动本地服务。"))}>重新启动本地服务</button><button type="button" className="secondary" onClick={() => void onOpenLogs().then((path) => setMessage(`已打开日志目录：${path}`)).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "无法打开日志目录。"))}>打开日志目录</button></div></section>
        <SoftwareUpdatePanel
          status={updateStatus}
          automaticChecksEnabled={automaticUpdateChecks}
          checking={checkingForUpdate}
          installing={installingUpdate}
          progress={updateProgress}
          message={updateMessage}
          error={updateError}
          onAutomaticChecksChange={onAutomaticUpdateChecksChange}
          onCheck={onCheckForUpdate}
          onInstall={onInstallUpdate}
        />
      </div>
      {message ? <p className="page-message" role="status">{message}</p> : null}
      <details className="technical-panel" open>
        <summary>技术详情</summary>
        <dl><div><dt>桌面版本</dt><dd>{version?.desktop ?? "读取中"}</dd></div><div><dt>后端版本</dt><dd>{version?.backend ?? "读取中"}</dd></div><div><dt>本地端口</dt><dd>{status.port ?? "未连接"}</dd></div><div><dt>后端进程</dt><dd>{status.backendPid ?? "未运行"}</dd></div><div><dt>自动恢复</dt><dd>{status.recoveryAttempts}/1 次</dd></div><div><dt>网络范围</dt><dd>127.0.0.1 随机端口</dd></div></dl>
        <p>会话凭据只保存在 Rust 进程内，不提供给 WebView。写入、导出和运行继续要求明确确认；safe roots 未扩大。</p>
        {status.technicalDetails ? <pre>{status.technicalDetails}</pre> : null}
      </details>
      <section className="privacy-boundaries"><h3>本机安全边界</h3><ul><li>不上传图片、设计文件或授权文件</li><li>不收集遥测，不运行后台公网服务</li><li>不扫描未授权目录，不记录原始 MachineGuid</li><li>Community 构建不包含生产私钥或私有 Pro 源码</li></ul></section>
    </div>
  );
}
