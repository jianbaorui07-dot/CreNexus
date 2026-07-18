import { useCallback, useEffect, useMemo, useState } from "react";

import type { StarBridgeClient } from "../services/client";
import type { Project } from "../types/api";

interface PhotoshopProductionPageProps {
  client: StarBridgeClient;
  runtimeReady: boolean;
  initialProjectId?: string;
  onOpenJob: (jobId: string, projectId: string) => void;
}

export function PhotoshopProductionPage({ client, runtimeReady, initialProjectId, onOpenJob }: PhotoshopProductionPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [sourceAssetId, setSourceAssetId] = useState("");
  const [resizeCanvas, setResizeCanvas] = useState(false);
  const [canvasWidth, setCanvasWidth] = useState(1920);
  const [canvasHeight, setCanvasHeight] = useState(1080);
  const [brightness, setBrightness] = useState(0);
  const [contrast, setContrast] = useState(0);
  const [saturation, setSaturation] = useState(0);
  const [formats, setFormats] = useState<string[]>(["png", "jpeg", "psd"]);
  const [exportSubject, setExportSubject] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedProject = useMemo(
    () => projects.find((project) => project.projectId === projectId),
    [projectId, projects],
  );

  const load = useCallback(async () => {
    if (!runtimeReady) return;
    try {
      const next = (await client.getProjects()).filter((project) => project.workflowId === "photoshop-production-v1");
      setProjects(next);
      setProjectId((current) => next.some((project) => project.projectId === current)
        ? current
        : initialProjectId && next.some((project) => project.projectId === initialProjectId)
          ? initialProjectId
          : next[0]?.projectId ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Photoshop 项目暂时无法读取。");
    }
  }, [client, initialProjectId, runtimeReady]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    setSourceAssetId((current) => selectedProject?.sourceAssets.some((asset) => asset.assetId === current)
      ? current
      : selectedProject?.sourceAssets[0]?.assetId ?? "");
  }, [selectedProject]);

  const toggleFormat = (format: string, checked: boolean) => {
    setFormats((current) => checked
      ? Array.from(new Set([...current, format]))
      : current.filter((item) => item !== format));
  };

  const createJob = async () => {
    if (!projectId || !sourceAssetId || formats.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const job = await client.createCreativeJob({
        projectId,
        workflowId: "photoshop-production-v1",
        sourceAssetId,
        outputFormats: formats,
        resizeCanvas,
        canvasWidth,
        canvasHeight,
        brightness,
        contrast,
        saturation,
        exportSubject,
      });
      onOpenJob(job.jobId, job.projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Photoshop 任务计划没有建立成功。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">photoshop-production-v1</span><h2>只修改受控副本，再导出真实文件</h2><p>StarBridge 先只读确认 Photoshop UXP 会话；获得任务确认后才复制活动文档、导入项目图片并应用固定参数。原文档和项目源素材不会被覆盖。</p></div><span className="state-label planned">实验性</span></header>
      {error ? <div className="error-state" role="alert"><strong>操作未完成</strong><p>{error}</p></div> : null}
      <div className="workflow-builder-grid">
        <section className="record-panel">
          <div className="section-heading"><div><span>项目素材</span><h3>选择明确导入的一张图片</h3></div></div>
          <div className="form-grid"><label>Photoshop 项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">请选择项目</option>{projects.map((project) => <option key={project.projectId} value={project.projectId}>{project.projectName}</option>)}</select></label><label>项目图片<select value={sourceAssetId} onChange={(event) => setSourceAssetId(event.target.value)}><option value="">请选择图片</option>{selectedProject?.sourceAssets.map((asset) => <option key={asset.assetId} value={asset.assetId}>{asset.basename}</option>)}</select></label></div>
          <p className="truth-note">只读取项目安全目录里的托管副本；计划与证据不保存原始绝对路径、活动文档名或图层名。</p>
        </section>
        <section className="record-panel">
          <div className="section-heading"><div><span>固定处理</span><h3>画布与基础调色</h3></div></div>
          <label className="confirmation"><input type="checkbox" checked={resizeCanvas} onChange={(event) => setResizeCanvas(event.target.checked)} />在 Photoshop 副本中调整画布尺寸</label>
          <div className="parameter-grid"><label>宽度<input type="number" min={64} max={8192} value={canvasWidth} disabled={!resizeCanvas} onChange={(event) => setCanvasWidth(Number(event.target.value))} /></label><label>高度<input type="number" min={64} max={8192} value={canvasHeight} disabled={!resizeCanvas} onChange={(event) => setCanvasHeight(Number(event.target.value))} /></label><label>亮度<input type="number" min={-150} max={150} value={brightness} onChange={(event) => setBrightness(Number(event.target.value))} /></label><label>对比度<input type="number" min={-100} max={100} value={contrast} onChange={(event) => setContrast(Number(event.target.value))} /></label><label>饱和度<input type="number" min={-100} max={100} value={saturation} onChange={(event) => setSaturation(Number(event.target.value))} /></label></div>
        </section>
        <section className="record-panel workflow-truth-panel">
          <div className="section-heading"><div><span>真实交付</span><h3>只登记实际生成的格式</h3></div></div>
          <div className="format-checks"><label className="confirmation"><input type="checkbox" checked={formats.includes("png")} onChange={(event) => toggleFormat("png", event.target.checked)} />PNG 预览</label><label className="confirmation"><input type="checkbox" checked={formats.includes("jpeg")} onChange={(event) => toggleFormat("jpeg", event.target.checked)} />JPEG 预览</label><label className="confirmation"><input type="checkbox" checked={formats.includes("psd")} onChange={(event) => toggleFormat("psd", event.target.checked)} />PSD 副本</label><label className="confirmation"><input type="checkbox" checked={exportSubject} onChange={(event) => setExportSubject(event.target.checked)} />尝试选择主体并另存透明 PNG</label></div>
          <ol className="workflow-step-list"><li>只读探测 UXP 与活动文档。</li><li>任务详情页明确确认后创建沙箱副本。</li><li>导入项目图片并应用固定画布、亮度、对比度和饱和度参数。</li><li>先写应用拥有的临时文件，全部成功后再提升为交付文件。</li><li>计算 SHA-256，等待人工确认后进入交付中心。</li></ol>
          <button type="button" className="primary" disabled={busy || !runtimeReady || !projectId || !sourceAssetId || formats.length === 0} onClick={() => void createJob()}>建立 Photoshop 任务计划</button>
        </section>
      </div>
    </div>
  );
}
