import { EmptyState } from "../components/EmptyState/EmptyState";
import type { CreativeJob } from "../types/api";

const STATUS_LABELS: Record<CreativeJob["status"], string> = {
  queued: "等待开始",
  running: "运行中",
  needs_user: "等待确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

interface TasksPageProps {
  tasks: CreativeJob[];
  onStart: () => void;
  onOpenJob: (jobId: string, projectId: string) => void;
}

export function TasksPage({ tasks, onStart, onOpenJob }: TasksPageProps) {
  return (
    <div className="standard-page">
      <header className="page-intro"><div><span className="page-kicker">CreativeJob</span><h2>统一任务中心</h2><p>项目工作流使用六种固定状态；这里显示持久化进度、当前步骤和实际产物数量，不显示原始文件路径。</p></div><button type="button" className="primary" onClick={onStart}>新建创意任务</button></header>
      {tasks.length > 0 ? <div className="record-list">{tasks.map((job) => <article className="record-panel creative-job-card" key={job.jobId}><div className="record-heading"><div><span className="task-kind">{job.workflowId}</span><h3>{job.currentStep}</h3><p>更新于 {new Date(job.updatedAt).toLocaleString()}</p></div><span className={`job-status status-${job.status}`}>{STATUS_LABELS[job.status]}</span></div><div className="progress-row"><progress max={100} value={job.progress} /><span>{job.progress}%</span></div><div className="record-footer"><span>{job.artifacts.length} 个真实产物{job.evidenceId ? " · 已登记证据" : ""}</span><button type="button" className="secondary" onClick={() => onOpenJob(job.jobId, job.projectId)}>查看任务</button></div></article>)}</div> : <EmptyState title="还没有创意任务" description="建立项目并选择工作流后，任务计划会保存在本机。" action={<button type="button" className="secondary" onClick={onStart}>建立第一个任务</button>} />}
    </div>
  );
}
