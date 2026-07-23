export type PageId =
  | "home"
  | "codex-conversation"
  | "projects"
  | "workflows"
  | "diagramforge"
  | "vectorization"
  | "ai-generation"
  | "photoshop-production"
  | "tasks"
  | "integrations"
  | "models"
  | "delivery"
  | "batch"
  | "license"
  | "diagnostics"
  | "job-detail"
  | "legacy-vectorization";

export interface NavigationItem {
  id: PageId;
  label: string;
  caption: string;
}

export const NAVIGATION_ITEMS: NavigationItem[] = [
  { id: "home", label: "首页", caption: "HOME" },
  { id: "codex-conversation", label: "Codex 对话", caption: "CODEX CONVERSATION" },
  { id: "projects", label: "项目", caption: "PROJECTS" },
  { id: "workflows", label: "创意工作流", caption: "WORKFLOWS" },
  { id: "diagramforge", label: "图枢", caption: "DIAGRAMFORGE" },
  { id: "vectorization", label: "图片矢量化", caption: "VECTORIZATION" },
  { id: "ai-generation", label: "AI 图片生成", caption: "AI GENERATION" },
  { id: "tasks", label: "任务中心", caption: "TASK CENTER" },
  { id: "integrations", label: "连接中心", caption: "CONNECTIONS" },
  { id: "models", label: "模型运行端", caption: "MODEL RUNTIME" },
  { id: "delivery", label: "交付与证据", caption: "DELIVERABLES" },
  { id: "batch", label: "批量生产", caption: "BATCH PRODUCTION" },
  { id: "license", label: "版本与授权", caption: "VERSIONS & LICENSE" },
  { id: "diagnostics", label: "设置与诊断", caption: "SETTINGS & DIAG" },
];

export const PAGE_TITLES: Record<PageId, string> = {
  home: "首页",
  "codex-conversation": "Codex 对话",
  projects: "项目",
  workflows: "创意工作流",
  diagramforge: "图枢 DiagramForge",
  vectorization: "图片矢量化",
  "ai-generation": "AI 图片生成",
  "photoshop-production": "Photoshop 安全副本",
  tasks: "任务中心",
  integrations: "连接中心",
  models: "模型运行端",
  delivery: "交付与证据",
  batch: "批量生产",
  license: "版本与授权",
  diagnostics: "设置与诊断",
  "job-detail": "任务详情",
  "legacy-vectorization": "旧版矢量化兼容入口",
};

export const PAGE_CAPTIONS: Record<PageId, string> = {
  home: "HOME",
  "codex-conversation": "CODEX CONVERSATION",
  projects: "PROJECTS",
  workflows: "WORKFLOWS",
  diagramforge: "DIAGRAMFORGE",
  vectorization: "VECTORIZATION",
  "ai-generation": "AI GENERATION",
  "photoshop-production": "PHOTOSHOP PRODUCTION",
  tasks: "TASK CENTER",
  integrations: "CONNECTIONS",
  models: "MODEL RUNTIME",
  delivery: "DELIVERABLES",
  batch: "BATCH PRODUCTION",
  license: "VERSIONS & LICENSE",
  diagnostics: "SETTINGS & DIAGNOSTICS",
  "job-detail": "JOB DETAIL",
  "legacy-vectorization": "LEGACY VECTORIZATION",
};
