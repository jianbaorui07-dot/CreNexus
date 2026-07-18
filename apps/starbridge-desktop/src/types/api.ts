export type RuntimeState =
  | "starting"
  | "connected"
  | "offline"
  | "recovering"
  | "failed";

export interface RuntimeStatus {
  state: RuntimeState;
  message: string;
  backendPid?: number;
  port?: number;
  recoveryAttempts: number;
  technicalDetails?: string;
}

export interface VersionInfo {
  desktop: string;
  backend?: string;
}

export interface SoftwareUpdateStatus {
  configured: boolean;
  source: string;
  currentVersion: string;
  available: boolean;
  version?: string;
  notes?: string;
  publishedAt?: string;
  signatureRequired: boolean;
  automaticChecksSupported: boolean;
}

export type SoftwareUpdateProgress =
  | { event: "started"; data: { contentLength?: number } }
  | {
      event: "progress";
      data: {
        chunkLength: number;
        downloadedBytes: number;
        contentLength?: number;
      };
    }
  | { event: "verified" }
  | { event: "installing" };

export type LicenseState = "community" | "active" | "invalid";
export type LicenseEdition = "community" | "pro" | "enterprise";

export interface LicenseStatus {
  state: LicenseState;
  edition: LicenseEdition;
  message: string;
  licenseId?: string;
  issuedOn?: string;
  perpetual?: boolean;
  currentDeviceMatched?: boolean;
  deviceLimit: number;
  features: string[];
  commercialVerifierConfigured: boolean;
  reason?: string;
}

export interface LicenseRequestReceipt {
  requestId: string;
  fileName: string;
  location: string;
  folderOpened: boolean;
}

export type VectorMode = "artisan" | "smart" | "lightweight" | "exact";
export type VectorJobState = "queued" | "running" | "completed" | "failed";

export interface VectorSelection {
  selectionId: string;
  fileName: string;
  width: number;
  height: number;
  sourceHash: string;
  previewDataUrl: string;
}

export interface VectorMetrics {
  colors: number;
  subpaths: number;
  points: number;
  svgBytes: number;
  elapsedSeconds: number;
  pixelMatch?: boolean | null;
  anchorReductionRatio?: number | null;
}

export interface VectorJobResult {
  modeLabel: string;
  sourceHash: string;
  sourcePreviewDataUrl: string;
  resultPreviewDataUrl: string;
  metrics: VectorMetrics;
  warnings: string[];
  outputAvailable: boolean;
}

export interface VectorJobError {
  code: string;
  message: string;
  nextSteps: string[];
}

export interface VectorJob {
  jobId: string;
  status: VectorJobState;
  progress: number;
  stage: string;
  mode: VectorMode;
  createdAt: string;
  completedAt?: string;
  result?: VectorJobResult;
  error?: VectorJobError;
}

export interface VectorHistoryEvent {
  eventId: string;
  createdAt: string;
  mode: VectorMode;
  summary: string;
  sourceHash: string;
  metrics: VectorMetrics;
  outputAvailable: boolean;
}

export interface VectorHistory {
  eventCount: number;
  events: VectorHistoryEvent[];
}

export interface VectorizationStart {
  selectionId: string;
  mode: VectorMode;
  parameters: Record<string, number>;
  confirmRun: boolean;
  confirmWrite: boolean;
  confirmExport: boolean;
}

export type CreativeJobState =
  | "queued"
  | "running"
  | "needs_user"
  | "completed"
  | "failed"
  | "cancelled";

export interface SourceAsset {
  assetId: string;
  basename: string;
  relativePath: string;
  sha256: string;
  mediaType: string;
  sizeBytes: number;
  importedAt: string;
}

export interface Artifact {
  artifactId: string;
  kind: string;
  basename: string;
  relativePath: string;
  sha256: string;
  mediaType: string;
  sizeBytes: number;
  createdAt: string;
  metadata: Record<string, unknown>;
}

export interface QualityMetric {
  name: string;
  value: number | string | boolean | null;
  unit?: string | null;
  target?: number | string | boolean | null;
  passed?: boolean | null;
}

export interface CreativeJobError {
  code: string;
  message: string;
  retryable: boolean;
  nextSteps: string[];
  details: Record<string, unknown>;
}

export interface CreativeJob {
  schemaVersion: number;
  jobId: string;
  projectId: string;
  workflowId: string;
  status: CreativeJobState;
  currentStep: string;
  progress: number;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
  artifacts: Artifact[];
  warnings: string[];
  error?: CreativeJobError | null;
  evidenceId?: string | null;
}

export interface CreativeJobCreateRequest {
  projectId: string;
  workflowId: string;
  sourceAssetId?: string;
  drawingMode?: "artisan" | "smart" | "lightweight";
  parameters?: Record<string, unknown>;
  prompt?: string;
  negativePrompt?: string;
  checkpointName?: string;
  width?: number;
  height?: number;
  seed?: number;
  steps?: number;
  cfg?: number;
  sampler?: string;
  scheduler?: string;
  waitSeconds?: number;
}

export interface Project {
  schemaVersion: number;
  projectId: string;
  projectName: string;
  workflowId: string;
  description: string;
  sourceAssets: SourceAsset[];
  currentJob?: string | null;
  jobHistory: string[];
  artifacts: Artifact[];
  qualityReports: QualityMetric[];
  evidence: string[];
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowSummary {
  workflowId: string;
  name: string;
  capabilityStatus: "stable" | "experimental" | "planned" | "not_implemented";
  recommended: boolean;
  ordinaryCustomerRoute: boolean;
  requiresConfirmation: boolean;
  drawingModes: Array<"artisan" | "smart" | "lightweight">;
  imageTraceFallback: boolean;
}

export interface ApprovalRequest {
  approvalRef: string;
  jobId: string;
  workflowId: string;
  stepId: string;
  planHash: string;
  revision: number;
  safeRootRef: string;
  expiresAt: string;
}

export interface CreativeJobRunResult {
  job: CreativeJob;
  approval?: ApprovalRequest | null;
}

export interface JobHistoryEvent {
  eventId: string;
  jobId: string;
  status: CreativeJobState;
  stepId: string;
  message: string;
  createdAt: string;
  details: Record<string, unknown>;
}

export interface ProjectDelivery {
  projectId: string;
  projectName: string;
  artifacts: Artifact[];
  evidenceIds: string[];
  formats: string[];
  fabricatedOutputs: false;
}

export interface ApiErrorShape {
  code?: string;
  message?: string;
  next_steps?: string[];
}

export interface ApiEnvelope<T> {
  ok: boolean;
  data?: T;
  error?: ApiErrorShape | string;
  [key: string]: unknown;
}

export interface TransportResponse<T> {
  status: number;
  body: T;
}

export interface TransportRequest {
  method: "GET" | "POST";
  path: string;
  body?: Record<string, unknown>;
}
