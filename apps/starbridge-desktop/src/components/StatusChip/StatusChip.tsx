import type { RuntimeState } from "../../types/api";

const LABELS: Record<RuntimeState, string> = {
  starting: "正在启动",
  connected: "运行正常 · 仅本机",
  offline: "本地服务离线",
  recovering: "正在恢复",
  failed: "需要处理",
};

export function StatusChip({ state }: { state: RuntimeState }) {
  return (
    <span className={`status-chip status-chip-${state}`} role="status">
      <span aria-hidden="true" />
      {LABELS[state]}
    </span>
  );
}
