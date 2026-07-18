import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "../components/EmptyState/EmptyState";
import type { StarBridgeClient } from "../services/client";
import type { Project, ProjectDelivery } from "../types/api";

interface DeliveryPageProps {
  client: StarBridgeClient;
  initialProjectId?: string;
}

export function DeliveryPage({ client, initialProjectId }: DeliveryPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [delivery, setDelivery] = useState<ProjectDelivery | null>(null);
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    try {
      const next = await client.getProjects();
      setProjects(next);
      setProjectId((current) => current || initialProjectId || next[0]?.projectId || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目列表暂时无法读取。");
    }
  }, [client, initialProjectId]);

  useEffect(() => { void loadProjects(); }, [loadProjects]);
  useEffect(() => {
    if (!projectId) { setDelivery(null); return; }
    setError("");
    void client.getProjectDelivery(projectId).then(setDelivery).catch((reason) => setError(reason instanceof Error ? reason.message : "交付记录暂时无法读取。"));
  }, [client, projectId]);

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">从实际产物生成</span><h2>交付与证据</h2><p>这里不会预先声称存在 PDF、AI 或其他格式。只有已经注册、具有文件哈希的真实产物才会列出。</p></div><span className="local-badge">不伪造格式</span></header>
      {error ? <div className="error-state" role="alert"><strong>读取未完成</strong><p>{error}</p></div> : null}
      <section className="record-panel delivery-selector"><label>项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">请选择项目</option>{projects.map((project) => <option key={project.projectId} value={project.projectId}>{project.projectName}</option>)}</select></label></section>
      {delivery && delivery.artifacts.length > 0 ? <>
        <div className="delivery-summary"><div><span>实际格式</span><strong>{delivery.formats.join(" · ") || "无扩展名"}</strong></div><div><span>产物</span><strong>{delivery.artifacts.length}</strong></div><div><span>证据</span><strong>{delivery.evidenceIds.length}</strong></div></div>
        <div className="record-list">{delivery.artifacts.map((artifact) => <article className="record-panel artifact-card" key={artifact.artifactId}><div><span className="task-kind">{artifact.kind}</span><h3>{artifact.basename}</h3><p>{artifact.mediaType} · {Math.ceil(artifact.sizeBytes / 1024)} KB</p></div><dl><div><dt>SHA-256</dt><dd>{artifact.sha256}</dd></div><div><dt>安全相对路径</dt><dd>{artifact.relativePath}</dd></div></dl></article>)}</div>
        <details className="technical-panel"><summary>证据标识与交付 JSON</summary><pre>{JSON.stringify(delivery, null, 2)}</pre></details>
      </> : <EmptyState title={projectId ? "这个项目还没有可交付产物" : "请选择项目"} description={projectId ? "完成创意工作流后，实际生成并登记的文件会出现在这里。" : "选择一个项目查看它的真实产物与证据。"} />}
    </div>
  );
}
