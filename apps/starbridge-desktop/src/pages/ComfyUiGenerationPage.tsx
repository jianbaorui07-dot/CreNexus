import { useCallback, useEffect, useState } from "react";

import type { StarBridgeClient } from "../services/client";
import type { Project } from "../types/api";

interface ComfyUiGenerationPageProps {
  client: StarBridgeClient;
  runtimeReady: boolean;
  initialProjectId?: string;
  onOpenJob: (jobId: string, projectId: string) => void;
}

export function ComfyUiGenerationPage({ client, runtimeReady, initialProjectId, onOpenJob }: ComfyUiGenerationPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [newProjectName, setNewProjectName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [checkpointName, setCheckpointName] = useState("");
  const [width, setWidth] = useState(512);
  const [height, setHeight] = useState(512);
  const [steps, setSteps] = useState(24);
  const [cfg, setCfg] = useState(7);
  const [sampler, setSampler] = useState("dpmpp_2m");
  const [scheduler, setScheduler] = useState("karras");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!runtimeReady) return;
    try {
      const next = (await client.getProjects()).filter((project) => project.workflowId === "comfyui-generation-v1");
      setProjects(next);
      setProjectId((current) => next.some((project) => project.projectId === current) ? current : initialProjectId && next.some((project) => project.projectId === initialProjectId) ? initialProjectId : next[0]?.projectId ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ComfyUI 项目暂时无法读取。");
    }
  }, [client, initialProjectId, runtimeReady]);

  useEffect(() => { void load(); }, [load]);

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const project = await client.createProject(newProjectName.trim(), "comfyui-generation-v1", "");
      setProjects((current) => [project, ...current]);
      setProjectId(project.projectId);
      setNewProjectName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目没有创建成功。");
    } finally {
      setBusy(false);
    }
  };

  const createJob = async () => {
    if (!projectId || !prompt.trim() || !checkpointName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const job = await client.createCreativeJob({
        projectId,
        workflowId: "comfyui-generation-v1",
        prompt: prompt.trim(),
        negativePrompt: negativePrompt.trim(),
        checkpointName: checkpointName.trim(),
        width,
        height,
        steps,
        cfg,
        sampler,
        scheduler,
        waitSeconds: 0,
      });
      setPrompt("");
      setNegativePrompt("");
      setCheckpointName("");
      onOpenJob(job.jobId, job.projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ComfyUI 任务计划没有建立成功。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">comfyui-generation-v1</span><h2>验证后再提交到本机 ComfyUI</h2><p>StarBridge 先构建并校验 API workflow，再只读探测回环服务。真正请求 /prompt 前会在任务详情页等待你的明确确认。</p></div><span className="state-label planned">实验性</span></header>
      {error ? <div className="error-state" role="alert"><strong>操作未完成</strong><p>{error}</p></div> : null}
      <div className="workflow-builder-grid">
        <section className="record-panel">
          <div className="section-heading"><div><span>项目</span><h3>选择或新建生成项目</h3></div></div>
          <div className="form-grid"><label>已有项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">请选择项目</option>{projects.map((project) => <option key={project.projectId} value={project.projectId}>{project.projectName}</option>)}</select></label><label>新项目名称<input value={newProjectName} maxLength={80} onChange={(event) => setNewProjectName(event.target.value)} placeholder="例如：夏季海报概念图" /></label></div>
          <button type="button" className="secondary" disabled={busy || !runtimeReady || !newProjectName.trim()} onClick={() => void createProject()}>创建 ComfyUI 项目</button>
        </section>
        <section className="record-panel">
          <div className="section-heading"><div><span>临时敏感输入</span><h3>提示词与本机模型</h3></div></div>
          <div className="form-grid comfy-prompt-grid"><label>正向提示词<textarea value={prompt} maxLength={4000} rows={5} onChange={(event) => setPrompt(event.target.value)} /></label><label>负向提示词（可选）<textarea value={negativePrompt} maxLength={4000} rows={5} onChange={(event) => setNegativePrompt(event.target.value)} /></label><label>Checkpoint 文件名<input value={checkpointName} maxLength={180} onChange={(event) => setCheckpointName(event.target.value)} placeholder="model.safetensors" /></label></div>
          <p className="truth-note">这些值只保存在当前后端进程的限时内存保险库；Project、CreativeJob、plan 和 Evidence 不持久化提示词、模型名或完整 workflow。</p>
        </section>
        <section className="record-panel workflow-truth-panel">
          <div className="section-heading"><div><span>受控参数</span><h3>尺寸与采样</h3></div></div>
          <div className="parameter-grid"><label>宽度<input type="number" min={64} max={2048} step={8} value={width} onChange={(event) => setWidth(Number(event.target.value))} /></label><label>高度<input type="number" min={64} max={2048} step={8} value={height} onChange={(event) => setHeight(Number(event.target.value))} /></label><label>步数<input type="number" min={1} max={100} value={steps} onChange={(event) => setSteps(Number(event.target.value))} /></label><label>CFG<input type="number" min={1} max={30} step={0.5} value={cfg} onChange={(event) => setCfg(Number(event.target.value))} /></label><label>采样器<select value={sampler} onChange={(event) => setSampler(event.target.value)}><option value="dpmpp_2m">DPM++ 2M</option><option value="dpmpp_2m_sde">DPM++ 2M SDE</option><option value="euler">Euler</option><option value="euler_ancestral">Euler a</option></select></label><label>调度器<select value={scheduler} onChange={(event) => setScheduler(event.target.value)}><option value="karras">Karras</option><option value="normal">Normal</option><option value="exponential">Exponential</option><option value="sgm_uniform">SGM Uniform</option></select></label></div>
          <ol className="workflow-step-list"><li>dry-run 校验不会请求网络或读取模型目录。</li><li>探测仅访问配置的 127.0.0.1 / localhost / ::1。</li><li>确认后只提交一次；状态不明时不会自动重复生成。</li><li>完成后通过回环 /view 复制实际图片并计算 SHA-256。</li></ol>
          <div className="button-row"><button type="button" className="primary" disabled={busy || !runtimeReady || !projectId || !prompt.trim() || !checkpointName.trim()} onClick={() => void createJob()}>建立生成任务计划</button></div>
        </section>
      </div>
    </div>
  );
}
