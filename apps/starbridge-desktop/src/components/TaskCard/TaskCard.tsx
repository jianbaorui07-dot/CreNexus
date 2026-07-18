import type { VectorHistoryEvent } from "../../types/api";

const MODE_LABEL: Record<string, string> = {
  artisan: "匠心矢量",
  smart: "智能矢量",
  lightweight: "轻量矢量",
  exact: "精确重建",
};

export function TaskCard({ event, compact = false }: { event: VectorHistoryEvent; compact?: boolean }) {
  return (
    <article className={`task-card${compact ? " task-card-compact" : ""}`}>
      <div>
        <span className="task-kind">{MODE_LABEL[event.mode] ?? "图片矢量化"}</span>
        <h3>{event.summary}</h3>
        <p>{new Date(event.createdAt).toLocaleString("zh-CN", { hour12: false })}</p>
      </div>
      <dl>
        <div><dt>路径</dt><dd>{event.metrics.subpaths}</dd></div>
        <div><dt>锚点</dt><dd>{event.metrics.points}</dd></div>
        <div><dt>耗时</dt><dd>{event.metrics.elapsedSeconds.toFixed(1)} 秒</dd></div>
      </dl>
    </article>
  );
}
