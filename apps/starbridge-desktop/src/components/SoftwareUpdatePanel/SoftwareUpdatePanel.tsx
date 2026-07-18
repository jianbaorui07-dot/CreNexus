import { useEffect, useMemo, useState } from "react";

import type {
  SoftwareUpdateProgress,
  SoftwareUpdateStatus,
} from "../../types/api";

interface SoftwareUpdatePanelProps {
  status: SoftwareUpdateStatus;
  automaticChecksEnabled: boolean;
  checking: boolean;
  installing: boolean;
  progress: SoftwareUpdateProgress | null;
  message: string;
  error: string;
  onAutomaticChecksChange: (enabled: boolean) => void;
  onCheck: () => Promise<void>;
  onInstall: () => Promise<void>;
}

function progressLabel(progress: SoftwareUpdateProgress | null): string {
  if (!progress || progress.event === "started") return "正在下载签名更新包…";
  if (progress.event === "verified") return "签名验证通过，正在安全关闭本地任务…";
  if (progress.event === "installing") return "正在启动安装程序，StarBridge 将自动关闭。";
  const { contentLength, downloadedBytes } = progress.data;
  if (!contentLength) return `已下载 ${Math.round(downloadedBytes / 1024 / 1024)} MB`;
  return `已下载 ${Math.min(100, Math.round((downloadedBytes / contentLength) * 100))}%`;
}

export function SoftwareUpdatePanel({
  status,
  automaticChecksEnabled,
  checking,
  installing,
  progress,
  message,
  error,
  onAutomaticChecksChange,
  onCheck,
  onInstall,
}: SoftwareUpdatePanelProps) {
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => setConfirmed(false), [status.version]);

  const progressValue = useMemo(() => {
    if (progress?.event !== "progress" || !progress.data.contentLength) return undefined;
    return Math.min(100, (progress.data.downloadedBytes / progress.data.contentLength) * 100);
  }, [progress]);

  return (
    <section className="diagnostic-card software-update-card">
      <div className="update-card-heading">
        <div>
          <h3>软件更新</h3>
          <p>
            正式版本发布到 GitHub 后，StarBridge 会检查签名更新。只请求版本信息，
            不上传图片、设计文件、授权文件或使用数据。
          </p>
        </div>
        <span className={status.configured ? "state-label" : "inactive-action"}>
          {status.configured ? "签名通道已配置" : "发布通道未启用"}
        </span>
      </div>

      {status.configured ? (
        <>
          <label className="confirmation update-toggle">
            <input
              type="checkbox"
              checked={automaticChecksEnabled}
              onChange={(event) => onAutomaticChecksChange(event.currentTarget.checked)}
              disabled={!status.automaticChecksSupported || installing}
            />
            <span>
              启动后并在运行期间定时检查 GitHub 正式版本；不会自动下载或静默安装。
            </span>
          </label>
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={() => void onCheck()}
              disabled={checking || installing}
            >
              {checking ? "正在检查…" : "立即检查更新"}
            </button>
          </div>
        </>
      ) : (
        <p className="update-readiness-note">
          当前开发构建没有正式更新验签公钥。取得受信任的 Windows 代码签名并安全配置更新私钥后，
          才能开放公开下载和软件内更新。
        </p>
      )}

      {status.available && status.version ? (
        <div className="update-available" role="status">
          <div className="update-version-row">
            <div>
              <span>发现新版本</span>
              <strong>StarBridge v{status.version}</strong>
            </div>
            <small>当前 v{status.currentVersion}</small>
          </div>
          {status.notes ? <p className="update-notes">{status.notes}</p> : null}
          {status.publishedAt ? <p className="update-date">发布于 {status.publishedAt}</p> : null}
          <label className="confirmation">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.currentTarget.checked)}
              disabled={installing}
            />
            <span>我已保存正在进行的工作，同意下载、验签并安装 v{status.version}。</span>
          </label>
          <button
            type="button"
            className="primary"
            disabled={!confirmed || installing}
            onClick={() => void onInstall()}
          >
            {installing ? "正在准备安装…" : `更新到 v${status.version}`}
          </button>
        </div>
      ) : null}

      {installing ? (
        <div className="update-progress" role="status">
          <progress max={100} value={progressValue} />
          <span>{progressLabel(progress)}</span>
        </div>
      ) : null}
      {message ? <p className="update-message" role="status">{message}</p> : null}
      {error ? <p className="update-error" role="alert">{error}</p> : null}
      <p className="update-source">更新来源：{status.source} · 更新包必须通过签名验证</p>
    </section>
  );
}
