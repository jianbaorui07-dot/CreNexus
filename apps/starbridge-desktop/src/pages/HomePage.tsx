import type { PageId } from "../app/routes";
import { EmptyState } from "../components/EmptyState/EmptyState";
import type { CreativeJob, RuntimeStatus } from "../types/api";

interface HomePageProps {
  status: RuntimeStatus;
  recentTasks: CreativeJob[];
  onNavigate: (page: PageId) => void;
}

const STATUS_LABELS: Record<CreativeJob["status"], string> = {
  queued: "等待开始",
  running: "运行中",
  needs_user: "等待确认",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function HomePage({ status, recentTasks, onNavigate }: HomePageProps) {
  const ready = status.state === "connected";
  const recent = recentTasks[0];
  return (
    <div className="home-page">
      <section className="home-hero">
        <div>
          <span className="privacy-pill">仅本机处理</span>
          <h2>从项目开始一次可审计的创作</h2>
          <p>项目把源素材、确认步骤、任务历史、真实产物和证据组织在一起。<br />你的图片和设计文件不会上传到 StarBridge 服务器。</p>
        </div>
        <div className="hero-trajectory" aria-hidden="true"><span /><span /><i>✦</i></div>
        <div className="hero-actions">
          <button type="button" className="primary" disabled={!ready} onClick={() => onNavigate("projects")}>新建或打开项目</button>
          <button type="button" className="secondary" onClick={() => onNavigate("tasks")}>打开任务中心</button>
          <button type="button" className="quiet-button" onClick={() => onNavigate("integrations")}>查看软件连接</button>
        </div>
        {!ready ? <p className="inline-guidance">本地服务就绪后即可开始。你可以前往“设置与诊断”重新启动。</p> : null}
      </section>

      <section className="home-grid">
        <div className="section-panel recent-panel">
          <div className="section-heading"><div><span>最近任务</span><h3>继续上次的创作</h3></div><button type="button" className="text-button" onClick={() => onNavigate("tasks")}>查看全部</button></div>
          {recent ? <article className="home-job-summary"><span className="task-kind">{recent.workflowId}</span><h3>{recent.currentStep}</h3><p>{STATUS_LABELS[recent.status]} · {recent.progress}% · {recent.artifacts.length} 个真实产物</p></article> : <EmptyState title="还没有任务记录" description="创建项目并建立工作流计划后，任务会出现在这里。" />}
        </div>
        <div className="section-panel software-panel">
          <div className="section-heading"><div><span>软件状态</span><h3>连接声明以探测证据为准</h3></div></div>
          <ul className="software-list">
            <li><span className="software-monogram ai">Ai</span><div><strong>Illustrator</strong><small>公开交付协议存在；真实桌面连接尚未验收</small></div><span className="state-label planned">待验收</span></li>
            <li><span className="software-monogram ps">Ps</span><div><strong>Photoshop</strong><small>公开桥接实现存在；当前未执行本机探测</small></div><span className="state-label neutral">未知</span></li>
            <li><span className="software-monogram co">Co</span><div><strong>ComfyUI</strong><small>实验工作流已接入；当前未执行本机服务探测</small></div><span className="state-label neutral">未知</span></li>
          </ul>
        </div>
      </section>
    </div>
  );
}
