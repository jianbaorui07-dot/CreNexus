import { useCallback, useEffect, useMemo, useState } from "react";
import { IconGridDots } from "@tabler/icons-react";

import { EmptyState } from "../components/EmptyState/EmptyState";
import type { CreNexusClient } from "../services/client";
import type { Project, WorkflowSummary } from "../types/api";

type DrawingMode = "artisan" | "smart" | "lightweight" | "exact";

interface WorkflowsPageProps {
  client: CreNexusClient;
  runtimeReady: boolean;
  initialProjectId?: string;
  onOpenProjects: () => void;
  onOpenJob: (jobId: string, projectId: string) => void;
}

const MODE_COPY: Record<DrawingMode, [string, string]> = {
  artisan: ["工匠曲线", "适合 Logo 和扁平几何；优先使用贝塞尔曲线和更少锚点。"],
  smart: ["智能矢量", "适合插画与纹样，在细节、稳定性和锚点数量之间平衡。"],
  lightweight: ["轻量矢量", "生成更精简的结构，适合快速交付和后续编辑。"],
  exact: ["像素重建", "把 RGBA 像素重建为真实 SVG 几何，并逐像素验证一致性。"],
};

export function WorkflowsPage({ client, runtimeReady, initialProjectId, onOpenProjects, onOpenJob }: WorkflowsPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [assetId, setAssetId] = useState("");
  const [drawingMode, setDrawingMode] = useState<DrawingMode>("exact");
  const [exactMaxDimension, setExactMaxDimension] = useState(1024);
  const [exactMaxSvgSizeMb, setExactMaxSvgSizeMb] = useState(128);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!runtimeReady) return;
    try {
      const [nextProjects, nextWorkflows] = await Promise.all([
        client.getProjects(),
        client.getWorkflows(),
      ]);
      const vectorProjects = nextProjects.filter((project) => project.workflowId === "vector-delivery-v1");
      setProjects(vectorProjects);
      setWorkflows(nextWorkflows);
      setProjectId((current) => current || initialProjectId || vectorProjects[0]?.projectId || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "工作流暂时无法读取。");
    }
  }, [client, initialProjectId, runtimeReady]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.projectId === projectId),
    [projectId, projects],
  );
  const selectedWorkflow = workflows.find((workflow) => workflow.workflowId === "vector-delivery-v1");

  useEffect(() => {
    setAssetId((current) =>
      selectedProject?.sourceAssets.some((asset) => asset.assetId === current)
        ? current
        : selectedProject?.sourceAssets[0]?.assetId ?? "",
    );
  }, [selectedProject]);

  const createJob = async () => {
    if (!selectedProject || !assetId) return;
    setBusy(true);
    setError("");
    try {
      const job = await client.createCreativeJob({
        projectId: selectedProject.projectId,
        workflowId: "vector-delivery-v1",
        sourceAssetId: assetId,
        drawingMode,
        parameters: { exact: { maxDimension: exactMaxDimension, maxSvgSizeMb: exactMaxSvgSizeMb } },
      });
      onOpenJob(job.jobId, job.projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务计划没有建立成功。");
    } finally {
      setBusy(false);
    }
  };

  if (!runtimeReady) {
    return <div className="standard-page"><header className="page-intro"><div><span className="page-kicker">创意工作流</span><h2>本地服务正在启动</h2><p>项目与素材会在安全 sidecar 就绪后自动载入，请稍候。</p></div></header><EmptyState title="正在连接本地创意引擎" description="无需重复选择或刷新；服务就绪后此页会自动显示已有项目。" /></div>;
  }

  if (projects.length === 0 && runtimeReady) {
    return <div className="standard-page"><header className="page-intro"><div><span className="page-kicker">创意工作流</span><h2>从一个项目开始</h2><p>工作流需要项目来保存素材、任务、真实产物和证据。</p></div></header><EmptyState title="还没有可用项目" description="先创建项目并导入一张明确选择的图片。" action={<button type="button" className="primary" onClick={onOpenProjects}>创建项目</button>} /></div>;
  }

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">vector-delivery-v1</span><h2>像素重建优先，需要时再生成可编辑矢量</h2><p>默认顺序为：源素材验证 → 像素重建 → 逐像素核对 → 人工确认 → SVG 交付。选择其他模式时，才会继续生成第二份可编辑矢量；不会回退到 Illustrator Image Trace。</p></div><span className="state-label planned">{selectedWorkflow?.capabilityStatus === "experimental" ? "实验性" : "状态待确认"}</span></header>
      {error ? <div className="error-state" role="alert"><strong>操作未完成</strong><p>{error}</p></div> : null}
      <div className="workflow-builder-grid">
        <section className="record-panel">
          <div className="section-heading"><div><span>输入</span><h3>项目与源素材</h3></div></div>
          <div className="form-grid">
            <label>项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}>{projects.map((project) => <option key={project.projectId} value={project.projectId}>{project.projectName}</option>)}</select></label>
            <label>源素材<select value={assetId} onChange={(event) => setAssetId(event.target.value)}><option value="">请选择已导入素材</option>{selectedProject?.sourceAssets.map((asset) => <option key={asset.assetId} value={asset.assetId}>{asset.basename}</option>)}</select></label>
          </div>
          {selectedProject && selectedProject.sourceAssets.length === 0 ? <p className="truth-note">这个项目还没有源素材。请回到项目页明确选择并导入图片。</p> : null}
        </section>
        <section className="record-panel">
          <div className="section-heading"><div><span>处理方式</span><h3>选择像素重建或可编辑矢量</h3></div><span className="state-label neutral">主推：像素重建</span></div>
          <div className="mode-grid">
            {(Object.keys(MODE_COPY) as DrawingMode[]).map((mode) => <button type="button" key={mode} aria-label={`选择${MODE_COPY[mode][0]}模式`} aria-pressed={drawingMode === mode} className={`mode-card ${mode === "exact" ? "mode-card-exact" : ""} ${drawingMode === mode ? "is-selected" : ""}`} onClick={() => setDrawingMode(mode)}>{mode === "exact" ? <IconGridDots className="mode-card-icon" role="img" aria-label="像素重建图标" /> : null}<strong>{MODE_COPY[mode][0]}</strong><span>{MODE_COPY[mode][1]}</span>{mode === "exact" ? <small>主推 · 像素级验证</small> : null}</button>)}
          </div>
        </section>
        <section className={`record-panel pixel-vector-panel ${drawingMode === "exact" ? "is-active" : ""}`}>
          <div className="pixel-vector-feature">
            <div className="pixel-vector-mark"><IconGridDots className="pixel-vector-icon" aria-hidden="true" /></div>
            <div className="pixel-vector-copy">
              <span>像素重建 / PIXEL RECONSTRUCTION</span>
              <h3>像素重建参数</h3>
              <p>把每个 RGBA 像素重建为真实 SVG 几何，并逐像素核对结果。</p>
            </div>
            <span className={`state-label ${drawingMode === "exact" ? "planned" : "neutral"}`}>{drawingMode === "exact" ? "当前主模式" : "固定基线"}</span>
          </div>
          <div className="form-grid">
            <label>像素重建最长边<select aria-label="像素重建最长边" value={exactMaxDimension} onChange={(event) => setExactMaxDimension(Number(event.target.value))}><option value={1024}>1024 像素（推荐）</option><option value={512}>512 像素（复杂大图）</option><option value={1600}>1600 像素（更高细节）</option><option value={2048}>2048 像素（可能较慢）</option><option value={0}>原始尺寸（可能超出安全上限）</option></select></label>
            <label>SVG 安全上限<select aria-label="SVG 安全上限" value={exactMaxSvgSizeMb} onChange={(event) => setExactMaxSvgSizeMb(Number(event.target.value))}><option value={64}>64 MB（兼容优先）</option><option value={128}>128 MB（推荐）</option><option value={256}>256 MB（大型文件）</option></select></label>
          </div>
          <p className="truth-note">像素重建会把本地工作副本的 RGBA 像素转换为真实、无嵌入位图的 SVG 几何。源图片不会被缩小或覆盖；只有选择其他模式时，才会继续生成第二份绘制型矢量。</p>
        </section>
        <section className="record-panel workflow-truth-panel">
          <div className="section-heading"><div><span>安全边界</span><h3>写入会分段确认</h3></div></div>
          <ol className="workflow-step-list"><li>导入时只复制明确选择的文件。</li><li>像素重建写入前单独确认。</li>{drawingMode === "exact" ? <li>像素核对通过后直接进入人工审核。</li> : <li>绘制型矢量写入前再次确认。</li>}<li>交付前由你审核实际生成的产物。</li></ol>
          <p className="truth-note">任务计划与确认令牌绑定到同一个项目、工作流、步骤和计划哈希；令牌一次使用并会过期。</p>
          <div className="button-row"><button type="button" className="secondary" onClick={onOpenProjects}>管理项目</button><button type="button" className="primary" disabled={!runtimeReady || busy || !assetId} onClick={() => void createJob()}>{drawingMode === "exact" ? "建立像素重建任务" : "建立双阶段任务"}</button></div>
        </section>
      </div>
    </div>
  );
}
