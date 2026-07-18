import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "../components/EmptyState/EmptyState";
import type { StarBridgeClient } from "../services/client";
import type { Project } from "../types/api";

interface ProjectsPageProps {
  client: StarBridgeClient;
  runtimeReady: boolean;
  onOpenWorkflow: (projectId: string, workflowId: string) => void;
}

const usesImportedAsset = (workflowId: string) =>
  workflowId === "vector-delivery-v1" || workflowId === "photoshop-production-v1";

export function ProjectsPage({ client, runtimeReady, onOpenWorkflow }: ProjectsPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectName, setProjectName] = useState("");
  const [description, setDescription] = useState("");
  const [workflowId, setWorkflowId] = useState("vector-delivery-v1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importConfirmations, setImportConfirmations] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    if (!runtimeReady) return;
    try {
      setProjects(await client.getProjects());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目列表暂时无法读取。");
    }
  }, [client, runtimeReady]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createProject = async () => {
    if (!projectName.trim()) return;
    setBusy(true);
    setError("");
    try {
      const project = await client.createProject(
        projectName.trim(),
        workflowId,
        description.trim(),
      );
      setProjectName("");
      setDescription("");
      setProjects((current) => [project, ...current]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目没有创建成功。");
    } finally {
      setBusy(false);
    }
  };

  const importAsset = async (projectId: string) => {
    if (!importConfirmations[projectId]) return;
    setBusy(true);
    setError("");
    try {
      const updated = await client.importProjectAsset(projectId, true);
      if (updated) {
        setProjects((current) =>
          current.map((project) => (project.projectId === projectId ? updated : project)),
        );
      }
      setImportConfirmations((current) => ({ ...current, [projectId]: false }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "素材没有导入成功。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="standard-page">
      <header className="page-intro">
        <div>
          <span className="page-kicker">项目是任务与交付的边界</span>
          <h2>先建立项目，再导入明确选择的素材</h2>
          <p>StarBridge 只复制你在文件选择器里明确选择的单个图片，不扫描文件夹，也不在界面或记录里展示原始路径。</p>
        </div>
        <span className="local-badge">仅本机保存</span>
      </header>

      {error ? <div className="error-state" role="alert"><strong>操作未完成</strong><p>{error}</p></div> : null}

      <section className="record-panel project-create-panel">
        <div className="section-heading"><div><span>新建项目</span><h3>选择一个普通客户工作流</h3></div><span className="state-label planned">实验性</span></div>
        <div className="form-grid">
          <label>项目名称<input value={projectName} maxLength={80} onChange={(event) => setProjectName(event.target.value)} placeholder="例如：品牌图标重制" /></label>
          <label>项目说明（可选）<input value={description} maxLength={240} onChange={(event) => setDescription(event.target.value)} placeholder="仅保存项目说明，不保存素材原路径" /></label>
          <label>工作流<select value={workflowId} onChange={(event) => setWorkflowId(event.target.value)}><option value="vector-delivery-v1">图片矢量交付</option><option value="comfyui-generation-v1">本机 ComfyUI 图片生成</option><option value="photoshop-production-v1">Photoshop 安全副本与交付</option></select></label>
        </div>
        <button type="button" className="primary" disabled={!runtimeReady || busy || !projectName.trim()} onClick={() => void createProject()}>创建项目</button>
      </section>

      {projects.length === 0 ? (
        <EmptyState title="还没有项目" description="创建第一个项目后，再从系统文件选择器导入一张 PNG 或 JPEG 图片。" />
      ) : (
        <div className="record-list">
          {projects.map((project) => (
            <article className="record-panel project-card" key={project.projectId}>
              <div className="record-heading">
                <div><span className="task-kind">{project.workflowId}</span><h3>{project.projectName}</h3><p>{project.description || "未填写项目说明"}</p></div>
                <span className="state-label neutral">{project.sourceAssets.length} 个素材</span>
              </div>
              {usesImportedAsset(project.workflowId) && project.sourceAssets.length > 0 ? (
                <ul className="asset-list">
                  {project.sourceAssets.map((asset) => <li key={asset.assetId}><strong>{asset.basename}</strong><span>{Math.ceil(asset.sizeBytes / 1024)} KB · SHA-256 {asset.sha256.slice(0, 12)}…</span></li>)}
                </ul>
              ) : usesImportedAsset(project.workflowId) ? <p className="truth-note">尚未导入素材。原始路径不会被保存到项目记录。</p> : <p className="truth-note">提示词与模型名只在建立任务后进入进程内临时保险库，不保存到项目。</p>}
              {usesImportedAsset(project.workflowId) ? <label className="confirmation">
                <input type="checkbox" checked={importConfirmations[project.projectId] ?? false} onChange={(event) => setImportConfirmations((current) => ({ ...current, [project.projectId]: event.target.checked }))} />
                我确认把接下来明确选择的一张图片复制到 StarBridge 的项目安全目录。
              </label> : null}
              <div className="button-row">
                {usesImportedAsset(project.workflowId) ? <button type="button" className="secondary" disabled={busy || !importConfirmations[project.projectId]} onClick={() => void importAsset(project.projectId)}>选择并导入图片</button> : null}
                <button type="button" className="primary" disabled={usesImportedAsset(project.workflowId) && project.sourceAssets.length === 0} onClick={() => onOpenWorkflow(project.projectId, project.workflowId)}>打开工作流</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
