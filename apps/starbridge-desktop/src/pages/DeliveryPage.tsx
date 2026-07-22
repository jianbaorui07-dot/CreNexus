import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "../components/EmptyState/EmptyState";
import type { CreNexusClient } from "../services/client";
import type { AdobeExportFormat, AdobeExportReceipt, Project, ProjectDelivery } from "../types/api";

interface DeliveryPageProps {
  client: CreNexusClient;
  initialProjectId?: string;
}

export function DeliveryPage({ client, initialProjectId }: DeliveryPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  const [delivery, setDelivery] = useState<ProjectDelivery | null>(null);
  const [error, setError] = useState("");
  const [openMessage, setOpenMessage] = useState("");
  const [exportFormat, setExportFormat] = useState<AdobeExportFormat>("ai");
  const [exportSource, setExportSource] = useState("");
  const [confirmExport, setConfirmExport] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportHistory, setExportHistory] = useState<AdobeExportReceipt[]>([]);
  const [historyError, setHistoryError] = useState("");

  const compatibleArtifacts = useMemo(() => {
    if (!delivery) return [];
    return delivery.artifacts.filter((artifact) => {
      const extension = artifact.basename.split(".").pop()?.toLowerCase();
      return exportFormat === "ai"
        ? extension === "svg"
        : extension === "png" || extension === "jpg" || extension === "jpeg";
    });
  }, [delivery, exportFormat]);

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
    if (!projectId) { setDelivery(null); setExportHistory([]); return; }
    setError("");
    setHistoryError("");
    void client.getProjectDelivery(projectId).then(setDelivery).catch((reason) => setError(reason instanceof Error ? reason.message : "交付记录暂时无法读取。"));
    void client.listAdobeExports(projectId).then(setExportHistory).catch((reason) => {
      setExportHistory([]);
      setHistoryError(reason instanceof Error ? reason.message : "Adobe 导出历史暂时无法读取。");
    });
  }, [client, projectId]);
  useEffect(() => {
    setExportSource((current) => compatibleArtifacts.some((artifact) => artifact.relativePath === current)
      ? current
      : compatibleArtifacts[0]?.relativePath ?? "");
    setConfirmExport(false);
  }, [compatibleArtifacts]);

  const openArtifacts = async () => {
    if (!projectId) return;
    setError("");
    setOpenMessage("");
    try {
      await client.openProjectArtifacts(projectId);
      setOpenMessage("已打开这个项目的真实产物目录。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法打开项目交付目录。");
    }
  };

  const exportAdobeFile = async () => {
    if (!projectId || !exportSource || !confirmExport) return;
    setExportBusy(true);
    setError("");
    setOpenMessage("");
    try {
      const receipt = await client.exportAdobeFile({
        projectId,
        artifactRelativePath: exportSource,
        format: exportFormat,
        confirmExport: true,
      });
      if (receipt) {
        if (receipt.historyRecorded) {
          setExportHistory((current) => [receipt, ...current.filter((item) => item.receiptId !== receipt.receiptId)].slice(0, 100));
          setOpenMessage(`已生成 ${receipt.fileName}（${Math.ceil(receipt.sizeBytes / 1024)} KB），并通过 Adobe 原生重开验证；源产物未覆盖。`);
        } else {
          setOpenMessage(`已生成并验证 ${receipt.fileName}，但本次审计记录未能保存。交付文件仍然有效，CreNexus 未记录其绝对路径。`);
        }
      } else {
        setOpenMessage("已取消导出，没有创建或覆盖文件。");
      }
      setConfirmExport(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Adobe 导出没有完成，源产物未被修改。" );
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">从实际产物生成</span><h2>交付与证据</h2><p>这里不会预先声称存在 PDF、AI 或其他格式。只有已经注册、具有文件哈希的真实产物才会列出。</p></div><span className="local-badge">不伪造格式</span></header>
      {error ? <div className="error-state" role="alert"><strong>读取未完成</strong><p>{error}</p></div> : null}
      {openMessage ? <div className="success-state" role="status"><strong>{openMessage}</strong></div> : null}
      <section className="record-panel delivery-selector"><label>项目<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">请选择项目</option>{projects.map((project) => <option key={project.projectId} value={project.projectId}>{project.projectName}</option>)}</select></label></section>
      {delivery && delivery.artifacts.length > 0 ? <>
        <div className="delivery-summary"><div><span>实际格式</span><strong>{delivery.formats.join(" · ") || "无扩展名"}</strong></div><div><span>产物</span><strong>{delivery.artifacts.length}</strong></div><div><span>证据</span><strong>{delivery.evidenceIds.length}</strong></div></div>
        <div className="button-row"><button type="button" className="primary" onClick={() => void openArtifacts()}>打开项目交付目录</button></div>
        <section className="record-panel adobe-export-panel">
          <div className="section-heading"><div><span>Adobe 原生交付</span><h3>选择产物与保存路径</h3></div><span className="state-label neutral">不覆盖已有文件</span></div>
          <div className="adobe-export-format" role="group" aria-label="Adobe 导出格式">
            <button type="button" className={exportFormat === "ai" ? "is-selected" : ""} onClick={() => setExportFormat("ai")}><strong>AI</strong><span>用真实 SVG 生成 Illustrator 工程</span></button>
            <button type="button" className={exportFormat === "psd" ? "is-selected" : ""} onClick={() => setExportFormat("psd")}><strong>PSD</strong><span>用 PNG/JPEG 预览生成 Photoshop 图层文档</span></button>
          </div>
          <div className="form-grid">
            <label>转换来源<select aria-label="转换来源" value={exportSource} onChange={(event) => { setExportSource(event.target.value); setConfirmExport(false); }}><option value="">请选择兼容产物</option>{compatibleArtifacts.map((artifact) => <option key={artifact.artifactId} value={artifact.relativePath}>{artifact.basename} · {artifact.kind} · {Math.ceil(artifact.sizeBytes / 1024)} KB</option>)}</select></label>
          </div>
          <label className="confirmation-check"><input type="checkbox" checked={confirmExport} onChange={(event) => setConfirmExport(event.target.checked)} /><span>我确认调用本机 {exportFormat === "ai" ? "Illustrator" : "Photoshop"}，随后在系统窗口选择一个新的保存路径；CreNexus 不覆盖已有文件。</span></label>
          <div className="button-row"><button type="button" className="primary" disabled={exportBusy || !exportSource || !confirmExport} onClick={() => void exportAdobeFile()}>{exportBusy ? "Adobe 正在保存并重开验证…" : `选择路径并导出 .${exportFormat}`}</button></div>
          {!compatibleArtifacts.length ? <p className="truth-note">当前项目没有可用于 .{exportFormat} 的真实来源产物。先完成矢量工作流，再回到这里导出。</p> : null}
        </section>
        <section className="record-panel adobe-export-history">
          <div className="section-heading"><div><span>可追溯交付</span><h3>Adobe 导出历史</h3></div><span className="state-label neutral">不保存绝对路径</span></div>
          {historyError ? <p className="truth-note" role="status">{historyError}</p> : null}
          {exportHistory.length > 0 ? <div className="adobe-history-list">{exportHistory.map((receipt) => <article key={receipt.receiptId}>
            <div><span className="task-kind">{receipt.format.toUpperCase()}</span><strong>{receipt.fileName}</strong><p>{Math.ceil(receipt.sizeBytes / 1024)} KB · 来源 {receipt.sourceBasename}</p></div>
            <dl><div><dt>导出时间</dt><dd>{new Date(receipt.createdAtUnixSeconds * 1000).toLocaleString("zh-CN", { hour12: false })}</dd></div><div><dt>SHA-256</dt><dd>{receipt.sha256}</dd></div><div><dt>验证</dt><dd>{receipt.nativeReopenValidated ? "Adobe 原生重开通过" : "未验证"} · 保存路径未记录</dd></div></dl>
          </article>)}</div> : !historyError ? <p className="truth-note">还没有 PSD/AI 导出记录。成功导出后，重启软件仍可核对文件名、大小、校验值与原生验证结果。</p> : null}
        </section>
        <div className="record-list">{delivery.artifacts.map((artifact) => <article className="record-panel artifact-card" key={artifact.artifactId}><div><span className="task-kind">{artifact.kind}</span><h3>{artifact.basename}</h3><p>{artifact.mediaType} · {Math.ceil(artifact.sizeBytes / 1024)} KB</p></div><dl><div><dt>SHA-256</dt><dd>{artifact.sha256}</dd></div><div><dt>安全相对路径</dt><dd>{artifact.relativePath}</dd></div></dl></article>)}</div>
        <details className="technical-panel"><summary>证据标识与交付 JSON</summary><pre>{JSON.stringify(delivery, null, 2)}</pre></details>
      </> : <EmptyState title={projectId ? "这个项目还没有可交付产物" : "请选择项目"} description={projectId ? "完成创意工作流后，实际生成并登记的文件会出现在这里。" : "选择一个项目查看它的真实产物与证据。"} />}
    </div>
  );
}
