import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import {
  StarBridgeApiClient,
  UserFacingError,
  type StarBridgeClient,
} from "../services/client";
import type {
  LicenseStatus,
  RuntimeState,
  RuntimeStatus,
  VersionInfo,
} from "../types/api";

const STATE_COPY: Record<
  RuntimeState,
  { eyebrow: string; title: string; description: string }
> = {
  starting: {
    eyebrow: "STARTING",
    title: "正在启动 StarBridge",
    description: "正在准备本地安全服务，通常只需要几秒钟。",
  },
  connected: {
    eyebrow: "CONNECTED",
    title: "本地服务已连接",
    description: "你可以继续进行安全检查、计划生成和结果验证。",
  },
  offline: {
    eyebrow: "OFFLINE",
    title: "本地服务尚未连接",
    description: "请重新启动本地服务；如果仍未恢复，再查看诊断信息。",
  },
  recovering: {
    eyebrow: "RECOVERING",
    title: "正在恢复本地服务",
    description: "StarBridge 只会自动恢复一次，不会无限重启。",
  },
  failed: {
    eyebrow: "NEEDS ATTENTION",
    title: "本地服务启动失败",
    description: "你的文件没有被修改。请查看诊断信息或手动重试。",
  },
};

const INITIAL_STATUS: RuntimeStatus = {
  state: "starting",
  message: "正在等待本地服务报告就绪状态。",
  recoveryAttempts: 0,
};

const INITIAL_LICENSE: LicenseStatus = {
  state: "community",
  edition: "community",
  message: "正在读取本机授权状态。",
  deviceLimit: 0,
  features: [],
  commercialVerifierConfigured: false,
};

const EDITION_COPY = {
  community: "Community 免费版",
  pro: "Pro 专业版",
  enterprise: "Enterprise 企业版",
} as const;

const FEATURE_COPY: Record<string, string> = {
  "vectorization.advanced": "高级矢量化",
  "batch.processing": "批量处理",
  "integration.adobe": "Adobe 联动",
  "integration.comfyui": "ComfyUI 联动",
  "integration.blender": "Blender 联动",
  "updates.offline_signed_packages": "离线签名更新包",
  "support.enterprise_customization": "企业定制支持",
};

interface AppProps {
  client?: StarBridgeClient;
}

function statusFromError(error: unknown): RuntimeStatus {
  if (error instanceof UserFacingError) {
    return {
      state: error.code === "backend_offline" ? "offline" : "failed",
      message: error.message,
      recoveryAttempts: 0,
      technicalDetails: error.technicalDetails,
    };
  }
  return {
    state: "failed",
    message: "本地服务状态暂时无法确认。",
    recoveryAttempts: 0,
    technicalDetails: error instanceof Error ? error.message : String(error),
  };
}

export function App({ client: providedClient }: AppProps) {
  const client = useMemo(() => providedClient ?? new StarBridgeApiClient(), [providedClient]);
  const [status, setStatus] = useState<RuntimeStatus>(INITIAL_STATUS);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [license, setLicense] = useState<LicenseStatus>(INITIAL_LICENSE);
  const [actionMessage, setActionMessage] = useState<string>("");
  const [licenseMessage, setLicenseMessage] = useState<string>("");
  const mounted = useRef(true);

  const refreshStatus = useCallback(async () => {
    try {
      const nextStatus = await client.getRuntimeStatus();
      if (mounted.current) {
        setStatus(nextStatus);
      }
    } catch (error) {
      if (mounted.current) {
        setStatus(statusFromError(error));
      }
    }
  }, [client]);

  useEffect(() => {
    mounted.current = true;
    void refreshStatus();
    void client
      .getVersion()
      .then((nextVersion) => mounted.current && setVersion(nextVersion))
      .catch(() => undefined);
    void client
      .getLicenseStatus()
      .then((nextLicense) => mounted.current && setLicense(nextLicense))
      .catch((error: unknown) => {
        if (mounted.current) {
          setLicenseMessage(error instanceof Error ? error.message : "无法读取本机授权状态。");
        }
      });
    return () => {
      mounted.current = false;
    };
  }, [client, refreshStatus]);

  useEffect(() => {
    if (status.state !== "starting" && status.state !== "recovering") {
      return undefined;
    }
    const timer = window.setTimeout(() => void refreshStatus(), 600);
    return () => window.clearTimeout(timer);
  }, [refreshStatus, status.state]);

  const restart = async () => {
    setActionMessage("");
    setStatus({
      state: "recovering",
      message: "正在重新启动本地服务。",
      recoveryAttempts: status.recoveryAttempts,
    });
    try {
      setStatus(await client.restartBackend());
    } catch (error) {
      setStatus(statusFromError(error));
    }
  };

  const openLogs = async () => {
    setActionMessage("");
    try {
      const openedPath = await client.openLogsDirectory();
      setActionMessage(`已打开日志目录：${openedPath}`);
    } catch (error) {
      const result = statusFromError(error);
      setActionMessage(result.message);
      setStatus((current) => ({
        ...current,
        technicalDetails: result.technicalDetails,
      }));
    }
  };

  const copy = STATE_COPY[status.state];

  const exportLicenseRequest = async () => {
    setLicenseMessage("");
    try {
      const receipt = await client.createLicenseRequest();
      setLicenseMessage(
        `${receipt.fileName} 已保存到本机授权申请目录${
          receipt.folderOpened ? "，文件夹已打开。" : "。"
        }`,
      );
    } catch (error) {
      setLicenseMessage(error instanceof Error ? error.message : "设备授权申请未创建。");
    }
  };

  const importLicense = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }
    if (file.size > 64 * 1024) {
      setLicenseMessage("授权文件超过 64 KB，已拒绝读取。");
      return;
    }
    setLicenseMessage("");
    try {
      const nextLicense = await client.importLicenseFile(await file.text());
      setLicense(nextLicense);
      setLicenseMessage("授权文件已在本机完成签名和设备绑定验证。");
    } catch (error) {
      setLicenseMessage(error instanceof Error ? error.message : "授权文件未能导入。");
    }
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand" aria-label="StarBridge Desktop">
          <span className="brand-mark" aria-hidden="true">
            S
          </span>
          <span>
            <strong>StarBridge</strong>
            <small>DESKTOP FOUNDATION</small>
          </span>
        </div>
        <span className="version" aria-label="版本信息">
          {version ? `Desktop ${version.desktop}` : "正在读取版本"}
        </span>
      </header>

      <section className="workspace" aria-labelledby="runtime-title">
        <div className="intro">
          <p className="section-label">本地运行状态</p>
          <h1 id="runtime-title">安全桌面运行基座</h1>
          <p>
            本阶段只负责安全启动、连接和诊断。工作流中心与完整任务界面将在后续阶段逐步加入。
          </p>
        </div>

        <article className={`status-card status-${status.state}`} aria-live="polite">
          <div className="status-indicator" aria-hidden="true" />
          <div className="status-content">
            <span className="status-eyebrow">{copy.eyebrow}</span>
            <h2>{copy.title}</h2>
            <p>{status.message || copy.description}</p>

            <dl className="status-facts">
              <div>
                <dt>本地服务</dt>
                <dd>{status.state === "connected" ? "已连接" : "等待处理"}</dd>
              </div>
              <div>
                <dt>自动恢复</dt>
                <dd>{status.recoveryAttempts}/1 次</dd>
              </div>
              <div>
                <dt>网络范围</dt>
                <dd>仅本机</dd>
              </div>
            </dl>

            <div className="actions">
              <button type="button" className="primary" onClick={() => void restart()}>
                重新启动本地服务
              </button>
              <button type="button" className="secondary" onClick={() => void openLogs()}>
                打开日志目录
              </button>
            </div>
            {actionMessage ? <p className="action-message">{actionMessage}</p> : null}

            {status.technicalDetails ? (
              <details className="technical-details">
                <summary>查看技术详情</summary>
                <pre>{status.technicalDetails}</pre>
              </details>
            ) : null}
          </div>
        </article>

        <section className={`license-card license-${license.state}`} aria-labelledby="license-title">
          <div className="license-heading">
            <div>
              <p className="section-label">本机授权</p>
              <h2 id="license-title">{EDITION_COPY[license.edition]}</h2>
            </div>
            <span className="license-badge">
              {license.state === "active" ? "授权有效" : "本地模式"}
            </span>
          </div>
          <p>{license.message}</p>

          <dl className="license-facts">
            <div>
              <dt>激活方式</dt>
              <dd>离线签名文件</dd>
            </div>
            <div>
              <dt>网络服务器</dt>
              <dd>不需要</dd>
            </div>
            <div>
              <dt>设备范围</dt>
              <dd>{license.deviceLimit > 0 ? `${license.deviceLimit} 台` : "申请时选择 1–2 台"}</dd>
            </div>
          </dl>

          {license.features.length > 0 ? (
            <ul className="license-features" aria-label="已授权功能">
              {license.features.map((feature) => (
                <li key={feature}>{FEATURE_COPY[feature] ?? "商业扩展功能"}</li>
              ))}
            </ul>
          ) : null}

          <div className="actions">
            <button type="button" className="secondary" onClick={() => void exportLicenseRequest()}>
              导出设备授权申请
            </button>
            <label className="file-button">
              导入授权文件
              <input
                type="file"
                accept=".starbridge-license,application/json"
                onChange={(event) => void importLicense(event)}
              />
            </label>
          </div>
          {!license.commercialVerifierConfigured ? (
            <p className="license-build-note">
              当前公开开发构建没有商业验签公钥，也不包含 Pro 功能代码。
            </p>
          ) : null}
          {licenseMessage ? <p className="action-message">{licenseMessage}</p> : null}
        </section>

        <aside className="safety-note">
          <div aria-hidden="true">✓</div>
          <div>
            <h2>当前仍处于安全计划与验证阶段</h2>
            <p>
              文件默认留在本机。真实写入仍需明确确认，并继续受 safe roots、dry-run 和路径脱敏规则约束。
            </p>
          </div>
        </aside>
      </section>
    </main>
  );
}
