import type { VectorMode } from "../types/api";

export interface VectorModeOption {
  id: VectorMode;
  name: string;
  description: string;
  bestFor: string;
}

export const VECTOR_MODES: VectorModeOption[] = [
  { id: "smart", name: "智能矢量", description: "平衡细节、颜色和文件大小。", bestFor: "插画与常规设计图" },
  { id: "artisan", name: "匠心矢量", description: "使用平滑曲线减少不必要锚点。", bestFor: "标志与精细图形" },
  { id: "lightweight", name: "轻量矢量", description: "优先生成更轻、更易编辑的文件。", bestFor: "网页图形与快速交付" },
  { id: "exact", name: "精确重建", description: "逐像素核对预览，保留原始画面。", bestFor: "像素图与忠实复刻" },
];
