import { useEffect, useState } from "react";

import { ErrorState } from "../components/ErrorState/ErrorState";
import { VECTOR_MODES } from "../content/vectorModes";
import { UserFacingError, type StarBridgeClient } from "../services/client";
import type { VectorJob, VectorMode, VectorSelection } from "../types/api";

interface VectorizationPageProps {
  client: StarBridgeClient;
  runtimeReady: boolean;
  codexConnected: boolean;
  onOpenConnections: () => void;
  onTaskSaved: () => void;
}

function errorCopy(error: unknown) {
  if (error instanceof UserFacingError) return { message: error.message, steps: error.nextSteps };
  return { message: error instanceof Error ? error.message : "这一步没有完成。", steps: ["检查图片和参数后重试；原图不会被修改。"] };
}

export function VectorizationPage({
  client,
  runtimeReady,
  codexConnected,
  onOpenConnections,
  onTaskSaved,
}: VectorizationPageProps) {
  const [selection, setSelection] = useState<VectorSelection | null>(null);
  const [mode, setMode] = useState<VectorMode>("smart");
  const [colors, setColors] = useState(12);
  const [maxDimension, setMaxDimension] = useState(2048);
  const [confirmed, setConfirmed] = useState(false);
  const [job, setJob] = useState<VectorJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; steps: string[] } | null>(null);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) return undefined;
    const timer = window.setTimeout(() => {
      void client.getVectorizationJob(job.jobId).then((next) => {
        setJob(next);
        if (next.status === "completed") onTaskSaved();
      }).catch((reason: unknown) => setError(errorCopy(reason)));
    }, 550);
    return () => window.clearTimeout(timer);
  }, [client, job, onTaskSaved]);

  const choose = async () => {
    setError(null);
    setBusy(true);
    try {
      const next = await client.chooseVectorInput();
      if (next) {
        setSelection(next);
        setJob(null);
        setConfirmed(false);
      }
    } catch (reason) {
      setError(errorCopy(reason));
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!selection) {
      setError({ message: "请先选择一张 PNG 或 JPEG 图片。", steps: ["点击“选择图片”。"] });
      return;
    }
    if (!confirmed) {
      setError({ message: "请确认本次本机执行与导出。", steps: ["检查模式和参数，再勾选确认项。"] });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setJob(await client.startVectorization({
        selectionId: selection.selectionId,
        mode,
        parameters: { colors, maxDimension },
        confirmRun: true,
        confirmWrite: true,
        confirmExport: true,
      }));
    } catch (reason) {
      setError(errorCopy(reason));
    } finally {
      setBusy(false);
    }
  };

  const openOutput = async () => {
    if (!job) return;
    try {
      await client.openVectorOutput(job.jobId);
    } catch (reason) {
      setError(errorCopy(reason));
    }
  };

  const running = job?.status === "queued" || job?.status === "running";
  return (
    <div className="workflow-page">
      <header className="page-intro">
        <div><span className="page-kicker">Community 真实工作流</span><h2>把图片转换为可交付的矢量文件</h2><p>选择图片与模式后，StarBridge 会在本机生成 SVG、预览和质量报告。原图不会被修改。</p></div>
        <span className="local-badge">不上传文件</span>
      </header>

      {!runtimeReady ? <ErrorState title="本地服务尚未就绪" message="图片尚未执行。请先在设置与诊断中重新启动本地服务。" /> : null}
      {runtimeReady && !codexConnected ? (
        <section className="drawing-connection-gate" role="status">
          <div><span aria-hidden="true">↗</span><div><strong>制图入口正在等待 Codex 关联</strong><p>为当前桌面会话完成一次短期配对后，图片选择和执行按钮才会开放。</p></div></div>
          <button type="button" className="primary" onClick={onOpenConnections}>前往连接中心</button>
        </section>
      ) : null}
      {error ? <ErrorState message={error.message} nextSteps={error.steps} /> : null}

      <div className="workflow-grid">
        <section className="workflow-controls">
          <div className="workflow-step">
            <span className="step-number">1</span><div className="step-content"><h3>选择图片</h3><p>支持 PNG 与 JPEG，最大 128 MB。</p>
              <button type="button" className="secondary" disabled={!runtimeReady || !codexConnected || busy || running} onClick={() => void choose()}>{selection ? "重新选择图片" : "选择图片"}</button>
              {selection ? <div className="selected-file"><img src={selection.previewDataUrl} alt="所选原图预览" /><div><strong>{selection.fileName}</strong><span>{selection.width} × {selection.height} px · 校验 {selection.sourceHash}</span></div></div> : <p className="not-run">尚未执行，也没有创建输出文件。</p>}
            </div>
          </div>
          <div className="workflow-step">
            <span className="step-number">2</span><div className="step-content"><h3>选择模式</h3><div className="mode-grid" role="radiogroup" aria-label="矢量化模式">
              {VECTOR_MODES.map((option) => <button type="button" role="radio" aria-checked={mode === option.id} className={mode === option.id ? "mode-card is-selected" : "mode-card"} key={option.id} onClick={() => setMode(option.id)}><strong>{option.name}</strong><span>{option.description}</span><small>{option.bestFor}</small></button>)}
            </div></div>
          </div>
          <div className="workflow-step">
            <span className="step-number">3</span><div className="step-content"><h3>确认参数并执行</h3><div className="parameter-row"><label>目标颜色<input type="number" min="2" max="32" value={colors} disabled={mode === "exact"} onChange={(event) => setColors(Number(event.currentTarget.value))} /></label><label>最大边长<input type="number" min="256" max="8192" step="128" value={maxDimension} onChange={(event) => setMaxDimension(Number(event.currentTarget.value))} /></label></div>
              <label className="confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.currentTarget.checked)} /><span>确认在 StarBridge 应用数据目录执行、写入并导出本次结果。</span></label>
              <button type="button" className="primary" disabled={!runtimeReady || !codexConnected || !selection || busy || running} onClick={() => void run()}>{running ? "正在本机处理" : "开始本机矢量化"}</button>
            </div>
          </div>
        </section>

        <aside className="result-panel" aria-live="polite">
          <div className="result-heading"><div><span>执行结果</span><h3>{job?.stage ?? "等待开始"}</h3></div>{job ? <span className={`result-state state-${job.status}`}>{job.status === "completed" ? "已完成" : job.status === "failed" ? "需处理" : "处理中"}</span> : null}</div>
          {job ? <><progress max="100" value={job.progress}>{job.progress}%</progress><span className="progress-copy">{job.progress}%</span></> : null}
          {!job ? <div className="result-placeholder"><div className="preview-bridge" aria-hidden="true"><span /><i>✦</i></div><h4>尚未执行</h4><p>选择图片并确认参数后，这里会显示真实原图、结果预览和质量指标。</p></div> : null}
          {job?.status === "failed" && job.error ? <ErrorState message={job.error.message} nextSteps={job.error.nextSteps} /> : null}
          {job?.status === "completed" && job.result ? <div className="completed-result">
            <div className="preview-compare"><figure><img src={job.result.sourcePreviewDataUrl} alt="原图预览" /><figcaption>原图</figcaption></figure><figure><img src={job.result.resultPreviewDataUrl} alt="矢量化结果预览" /><figcaption>结果</figcaption></figure></div>
            <dl className="metrics-grid"><div><dt>颜色</dt><dd>{job.result.metrics.colors}</dd></div><div><dt>路径</dt><dd>{job.result.metrics.subpaths}</dd></div><div><dt>锚点</dt><dd>{job.result.metrics.points}</dd></div><div><dt>耗时</dt><dd>{job.result.metrics.elapsedSeconds.toFixed(1)} 秒</dd></div>{job.result.metrics.pixelMatch != null ? <div><dt>像素核对</dt><dd>{job.result.metrics.pixelMatch ? "一致" : "有差异"}</dd></div> : null}</dl>
            <p className="saved-note">任务记录已保存，输出位于 StarBridge 本机应用数据目录。</p>
            <button type="button" className="secondary" onClick={() => void openOutput()}>打开输出文件夹</button>
          </div> : null}
        </aside>
      </div>
    </div>
  );
}
