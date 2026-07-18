export type PageId =
  | "home"
  | "projects"
  | "workflows"
  | "vectorization"
  | "ai-generation"
  | "photoshop-production"
  | "tasks"
  | "integrations"
  | "delivery"
  | "batch"
  | "license"
  | "diagnostics"
  | "job-detail"
  | "legacy-vectorization";

export interface NavigationItem {
  id: PageId;
  label: string;
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  { id: "home", label: "首页" },
  { id: "projects", label: "项目" },
  { id: "workflows", label: "创意工作流" },
  { id: "vectorization", label: "图片矢量化" },
  { id: "ai-generation", label: "AI 图片生成" },
  { id: "tasks", label: "任务中心" },
  { id: "integrations", label: "连接中心" },
  { id: "delivery", label: "交付与证据" },
  { id: "batch", label: "批量生产" },
  { id: "license", label: "版本与授权" },
  { id: "diagnostics", label: "设置与诊断" },
];

export const PAGE_TITLES: Record<PageId, string> = {
  home: "首页",
  projects: "项目",
  workflows: "创意工作流",
  vectorization: "图片矢量化",
  "ai-generation": "AI 图片生成",
  "photoshop-production": "Photoshop 安全副本",
  tasks: "任务中心",
  integrations: "连接中心",
  delivery: "交付与证据",
  batch: "批量生产",
  license: "版本与授权",
  diagnostics: "设置与诊断",
  "job-detail": "任务详情",
  "legacy-vectorization": "旧版矢量化兼容入口",
};
