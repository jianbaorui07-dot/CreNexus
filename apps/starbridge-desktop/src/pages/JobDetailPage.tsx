import { useCallback, useEffect, useState } from "react";

import type { StarBridgeClient } from "../services/client";
import type { ApprovalRequest, CreativeJob, JobHistoryEvent } from "../types/api";

const STATUS_LABELS: Record<CreativeJob["status"], string> = {
  queued: "等待开始",
  running: "运行中",
  needs_user: "等待确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

interface JobDetailPageProps {
  client: StarBridgeClient;
  jobId?: string;
  onOpenDelivery: (projectId: string) => void;
  onBack: () => void;
  onJobChanged: () => void;
}

export function JobDetailPage({ client, jobId, onOpenDelivery, onBack, onJobChanged }: JobDetailPageProps) {
  const [job, setJob] = useState<CreativeJob | null>(null);
  const [events, setEvents] = useState<JobHistoryEvent[]>([]);
  const [approval, setApproval] = useState<ApprovalRequest | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [cancelConfirmed, setCancelConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!jobId) return;
    try {
      const [nextJob, nextEvents] = await Promise.all([
        client.getCreativeJob(jobId),
        client.getCreativeJobEvents(jobId),
      ]);
      setJob(nextJob);
      setEvents(nextEvents);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务详情暂时无法读取。");
    }
  }, [client, jobId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = async () => {
    if (!jobId) return;
    setBusy(true);
    setError("");
    try {
      const result = await client.runCreativeJob(
        jobId,
        approval?.approvalRef,
        approval ? confirmed : false,
      );
      setJob(result.job);
      setApproval(result.approval ?? null);
      setConfirmed(false);
      setEvents(await client.getCreativeJobEvents(jobId));
      onJobChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务没有继续执行。");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!jobId || !cancelConfirmed) return;
    setBusy(true);
    setError("");
    try {
      const next = await client.cancelCreativeJob(jobId, true);
      setJob(next);
      setEvents(await client.getCreativeJobEvents(jobId));
      onJobChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务没有取消成功。");
    } finally {
      setBusy(false);
    }
  };

  if (!jobId) return <div className="standard-page"><div className="error-state"><strong>没有选择任务</strong><p>请回到任务中心选择一个任务。</p></div><button type="button" className="secondary" onClick={onBack}>返回任务中心</button></div>;

  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">{job?.workflowId ?? "创意任务"}</span><h2>{job ? STATUS_LABELS[job.status] : "正在读取任务"}</h2><p>每个写入步骤都在安全目录内执行，并在需要时等待你的明确确认。</p></div><button type="button" className="secondary" onClick={onBack}>返回任务中心</button></header>
      {error ? <div className="error-state" role="alert"><strong>操作未完成</strong><p>{error}</p></div> : null}
      {job ? <>
        <section className="record-panel job-progress-panel">
          <div className="record-heading"><div><span className="task-kind">当前步骤</span><h3>{job.currentStep}</h3></div><span className={`job-status status-${job.status}`}>{STATUS_LABELS[job.status]}</span></div>
          <div className="progress-row"><progress max={100} value={job.progress} /><span>{job.progress}%</span></div>
          {job.error ? <div className="error-state"><strong>{job.error.message}</strong>{job.error.nextSteps.length ? <ul>{job.error.nextSteps.map((step) => <li key={step}>{step}</li>)}</ul> : null}</div> : null}
          {approval ? <div className="approval-panel"><strong>此步骤需要写入确认：{approval.stepId}</strong><p>确认范围：{approval.safeRootRef} · 计划修订 {approval.revision} · {new Date(approval.expiresAt).toLocaleString()} 前有效</p><label className="confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核对当前步骤，同意在 StarBridge 项目安全目录内执行这一次写入。</label></div> : null}
          <div className="button-row">
            {job.status === "queued" || job.status === "running" || job.status === "needs_user" ? <button type="button" className="primary" disabled={busy || Boolean(approval && !confirmed)} onClick={() => void run()}>{approval ? "确认并继续" : job.status === "needs_user" ? "只读刷新同一任务" : "运行到下一确认点"}</button> : null}
            {job.status === "completed" ? <button type="button" className="primary" onClick={() => onOpenDelivery(job.projectId)}>查看真实交付物</button> : null}
          </div>
          {job.status === "queued" || job.status === "running" || job.status === "needs_user" ? <div className="cancel-row"><label className="confirmation"><input type="checkbox" checked={cancelConfirmed} onChange={(event) => setCancelConfirmed(event.target.checked)} />我确认取消这项任务；已经生成的诊断或安全产物可能会保留。</label><button type="button" className="quiet-button danger-button" disabled={busy || !cancelConfirmed} onClick={() => void cancel()}>取消任务</button></div> : null}
        </section>

        <section className="record-panel">
          <div className="section-heading"><div><span>历史</span><h3>持久化事件</h3></div><span className="state-label neutral">{events.length} 条</span></div>
          <ol className="event-list">{events.map((event) => <li key={event.eventId}><span className={`event-dot status-${event.status}`} /><div><strong>{event.message}</strong><p>{event.stepId} · {new Date(event.createdAt).toLocaleString()}</p></div></li>)}</ol>
        </section>

        <details className="technical-panel"><summary>技术详情</summary><pre>{JSON.stringify({ job, approval, events }, null, 2)}</pre></details>
      </> : null}
    </div>
  );
}
