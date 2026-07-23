import { useCallback, useEffect, useState } from "react";

import type { KORYAOClient } from "../services/client";
import type { ModelRuntimeStatus } from "../types/api";

interface ModelRuntimePageProps {
  client: KORYAOClient;
  runtimeReady: boolean;
}

function statusLabel(status: ModelRuntimeStatus["status"]) {
  if (status === "healthy") return "运行正常";
  if (status === "degraded") return "部分可用";
  return "不可用";
}

export function ModelRuntimePage({ client, runtimeReady }: ModelRuntimePageProps) {
  const [status, setStatus] = useState<ModelRuntimeStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!runtimeReady) {
      setStatus(null);
      setError("请先启动 KORYAO 本地服务。");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setStatus(await client.getModelRuntimeStatus());
    } catch (reason) {
      setStatus(null);
      setError(
        reason instanceof Error
          ? reason.message
          : "无法连接本地模型运行端。",
      );
    } finally {
      setLoading(false);
    }
  }, [client, runtimeReady]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="standard-page model-runtime-page">
      <header className="page-intro">
        <div>
          <span className="page-kicker">闭源模型 / 本机连接</span>
          <h2>KORYAO-C1 模型运行端</h2>
          <p>
            KORYAO 只向本机运行端发送经过 schema 校验的任务元数据、素材 ID
            和 Adapter 白名单。模型不会读取磁盘，也不能直接执行软件或绕过确认门。
          </p>
        </div>
        <button type="button" className="secondary" disabled={loading} onClick={() => void refresh()}>
          {loading ? "检测中…" : "重新检测"}
        </button>
      </header>

      {error ? (
        <section className="model-runtime-offline" role="alert">
          <strong>本地模型运行端未连接</strong>
          <p>{error}</p>
          <small>请启动 KORYAO-Model-Private，并保持默认 loopback 配置。</small>
        </section>
      ) : null}

      {status ? (
        <>
          <section className="model-runtime-summary">
            <div>
              <span>服务状态</span>
              <strong>{statusLabel(status.status)}</strong>
            </div>
            <div>
              <span>协议</span>
              <strong>{status.schema}</strong>
            </div>
            <div>
              <span>网络</span>
              <strong>{status.network.bindAddress} / LOOPBACK</strong>
            </div>
            <div>
              <span>原始素材</span>
              <strong>{status.privacy.acceptsRawAssets ? "允许" : "不接收"}</strong>
            </div>
          </section>

          <section className="model-runtime-models">
            <header>
              <div>
                <span>已注册模型</span>
                <h3>{status.models.length} 个 Provider</h3>
              </div>
              <small>服务版本 {status.serviceVersion}</small>
            </header>
            {status.models.map((model) => (
              <article key={`${model.modelId}-${model.version}`}>
                <div>
                  <span>{model.providerId}</span>
                  <h3>{model.modelId}</h3>
                  <p>版本 {model.version}</p>
                </div>
                <div className="model-capabilities">
                  {model.capabilities.map((capability) => (
                    <span key={capability}>{capability}</span>
                  ))}
                </div>
                <strong className={`model-state model-state-${model.status}`}>
                  {model.status.toUpperCase()}
                </strong>
              </article>
            ))}
          </section>

          <section className="model-runtime-boundary">
            <strong>安全边界已启用</strong>
            <ul>
              <li>外网访问：关闭</li>
              <li>完整指令日志：关闭</li>
              <li>绝对路径日志：关闭</li>
              <li>真实写入：仍由 KORYAO Adapter 和确认门控制</li>
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}
