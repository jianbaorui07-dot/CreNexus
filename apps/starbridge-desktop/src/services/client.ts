import type {
  AdobeExportReceipt,
  AdobeExportRequest,
  ApiEnvelope,
  CodexConnectionResetResult,
  CodexConnectorInstallResult,
  ConnectionOverview,
  CreativeJob,
  CreativeJobCreateRequest,
  CreativeJobRunResult,
  CreativeApplicationConnection,
  JobHistoryEvent,
  LicenseRequestReceipt,
  LicenseStatus,
  Project,
  ProjectDelivery,
  RuntimeStatus,
  SoftwareUpdateProgress,
  SoftwareUpdateStatus,
  TransportRequest,
  VersionInfo,
  VectorHistory,
  VectorJob,
  VectorSelection,
  VectorizationStart,
  WorkflowSummary,
} from "../types/api";
import { createTransport } from "./runtime";
import { TransportError, type CreNexusTransport } from "./transport";

export class UserFacingError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly technicalDetails: string,
    public readonly nextSteps: string[] = [],
    public readonly status?: number,
  ) {
    super(message);
    this.name = "UserFacingError";
  }
}

export interface CreNexusClient {
  getRuntimeStatus(): Promise<RuntimeStatus>;
  getHealth(): Promise<ApiEnvelope<unknown>>;
  getBootstrap(): Promise<ApiEnvelope<unknown>>;
  restartBackend(): Promise<RuntimeStatus>;
  openLogsDirectory(): Promise<string>;
  openProjectArtifacts(projectId: string): Promise<string>;
  exportAdobeFile(request: AdobeExportRequest): Promise<AdobeExportReceipt | null>;
  listAdobeExports(projectId: string): Promise<AdobeExportReceipt[]>;
  getConnections(): Promise<ConnectionOverview>;
  installCodexConnector(confirmInstall: boolean): Promise<CodexConnectorInstallResult>;
  resetCodexConnection(confirmReset: boolean): Promise<CodexConnectionResetResult>;
  openCodexPairing(pairingCode: string): Promise<void>;
  openCodexTask(prompt: string, confirmOpen: boolean): Promise<void>;
  openGitHubProject(): Promise<void>;
  pairCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection>;
  reconnectCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection>;
  disconnectCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection>;
  getVersion(): Promise<VersionInfo>;
  getUpdateStatus(): Promise<SoftwareUpdateStatus>;
  checkForUpdate(): Promise<SoftwareUpdateStatus>;
  installUpdate(
    version: string,
    confirmInstall: boolean,
    onProgress: (event: SoftwareUpdateProgress) => void,
  ): Promise<void>;
  getLicenseStatus(): Promise<LicenseStatus>;
  createLicenseRequest(): Promise<LicenseRequestReceipt>;
  importLicenseFile(contents: string): Promise<LicenseStatus>;
  getWorkflows(): Promise<WorkflowSummary[]>;
  getProjects(): Promise<Project[]>;
  createProject(projectName: string, workflowId: string, description: string): Promise<Project>;
  importProjectAsset(projectId: string, confirmImport: boolean): Promise<Project | null>;
  getCreativeJobs(): Promise<CreativeJob[]>;
  createCreativeJob(request: CreativeJobCreateRequest): Promise<CreativeJob>;
  getCreativeJob(jobId: string): Promise<CreativeJob>;
  runCreativeJob(
    jobId: string,
    approvalRef?: string,
    confirmExecute?: boolean,
  ): Promise<CreativeJobRunResult>;
  cancelCreativeJob(jobId: string, confirmCancel: boolean): Promise<CreativeJob>;
  getCreativeJobEvents(jobId: string): Promise<JobHistoryEvent[]>;
  getProjectDelivery(projectId: string): Promise<ProjectDelivery>;
  chooseVectorInput(): Promise<VectorSelection | null>;
  startVectorization(request: VectorizationStart): Promise<VectorJob>;
  getVectorizationJob(jobId: string): Promise<VectorJob>;
  getVectorizationHistory(): Promise<VectorHistory>;
  openVectorOutput(jobId: string): Promise<void>;
}

function errorFromEnvelope(
  status: number,
  envelope: ApiEnvelope<unknown>,
): UserFacingError {
  const structured = typeof envelope.error === "object" ? envelope.error : undefined;
  const code = structured?.code ?? `http_${status}`;
  const fallback = typeof envelope.error === "string" ? envelope.error : "请求未完成";

  const friendly: Record<string, string> = {
    authentication_required: "本地服务需要重新授权，请重新连接桌面会话。",
    authentication_failed: "桌面会话已失效，请重新启动本地服务。",
    origin_not_allowed: "当前页面不能直接访问本地服务。",
    request_too_large: "这次请求包含的内容过大，请减少输入后重试。",
    codex_association_required: "请先在连接中心关联当前 Codex 会话，再开始制图。",
  };

  return new UserFacingError(
    code,
    friendly[code] ?? structured?.message ?? fallback,
    `HTTP ${status}; ${code}`,
    structured?.next_steps ?? [],
    status,
  );
}

export class CreNexusApiClient implements CreNexusClient {
  constructor(private readonly transport: CreNexusTransport = createTransport()) {}

  private async execute<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (error instanceof UserFacingError) {
        throw error;
      }
      if (error instanceof TransportError) {
        const nextSteps = error.code.startsWith("update_")
          ? ["确认可以访问 GitHub 后重新检查。", "更新失败时保留当前版本继续使用。"]
          : ["查看诊断信息。", "重新启动本地服务后再试。"];
        throw new UserFacingError(
          error.code,
          error.message,
          error.technicalDetails ?? error.code,
          nextSteps,
        );
      }
      throw new UserFacingError(
        "unexpected_client_error",
        "CreNexus 暂时无法完成该操作。",
        error instanceof Error ? error.message : String(error),
      );
    }
  }

  private unwrap<T>(status: number, envelope: ApiEnvelope<T>): T {
    if (status >= 400 || !envelope.ok || envelope.data === undefined) {
      throw errorFromEnvelope(status, envelope);
    }
    return envelope.data;
  }

  private async request<T>(request: TransportRequest): Promise<ApiEnvelope<T>> {
    return this.execute(async () => {
      const response = await this.transport.request<ApiEnvelope<T>>(request);
      if (response.status >= 400 || !response.body.ok) {
        throw errorFromEnvelope(response.status, response.body);
      }
      return response.body;
    });
  }

  private async requestData<T>(request: TransportRequest): Promise<T> {
    return this.execute(async () => {
      const response = await this.transport.request<ApiEnvelope<T>>(request);
      return this.unwrap(response.status, response.body);
    });
  }

  getRuntimeStatus(): Promise<RuntimeStatus> {
    return this.transport.getRuntimeStatus();
  }

  getHealth(): Promise<ApiEnvelope<unknown>> {
    return this.request({ method: "GET", path: "/api/health" });
  }

  getBootstrap(): Promise<ApiEnvelope<unknown>> {
    return this.request({ method: "GET", path: "/api/bootstrap" });
  }

  restartBackend(): Promise<RuntimeStatus> {
    return this.transport.restartBackend();
  }

  openLogsDirectory(): Promise<string> {
    return this.transport.openLogsDirectory();
  }

  openProjectArtifacts(projectId: string): Promise<string> {
    return this.execute(() => this.transport.openProjectArtifacts(projectId));
  }

  exportAdobeFile(request: AdobeExportRequest): Promise<AdobeExportReceipt | null> {
    return this.execute(() => this.transport.exportAdobeFile(request));
  }

  listAdobeExports(projectId: string): Promise<AdobeExportReceipt[]> {
    return this.execute(() => this.transport.listAdobeExports(projectId));
  }

  getConnections(): Promise<ConnectionOverview> {
    return this.execute(async () => {
      const response = await this.transport.request<ApiEnvelope<ConnectionOverview>>({
        method: "GET",
        path: "/api/connections",
      });
      return this.unwrap(response.status, response.body);
    });
  }

  installCodexConnector(confirmInstall: boolean): Promise<CodexConnectorInstallResult> {
    return this.execute(async () => {
      const response = await this.transport.installCodexConnector(confirmInstall);
      return this.unwrap(response.status, response.body);
    });
  }

  resetCodexConnection(confirmReset: boolean): Promise<CodexConnectionResetResult> {
    return this.execute(async () => {
      const response = await this.transport.resetCodexConnection(confirmReset);
      return this.unwrap(response.status, response.body);
    });
  }

  openCodexPairing(pairingCode: string): Promise<void> {
    return this.execute(() => this.transport.openCodexPairing(pairingCode));
  }

  openCodexTask(prompt: string, confirmOpen: boolean): Promise<void> {
    return this.execute(() => this.transport.openCodexTask(prompt, confirmOpen));
  }

  openGitHubProject(): Promise<void> {
    return this.execute(() => this.transport.openGitHubProject());
  }

  pairCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection> {
    return this.execute(async () => {
      const response = await this.transport.pairCreativeApplication(applicationId, true);
      return this.unwrap(response.status, response.body);
    });
  }

  reconnectCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection> {
    return this.execute(async () => {
      const response = await this.transport.reconnectCreativeApplication(applicationId, true);
      return this.unwrap(response.status, response.body);
    });
  }

  disconnectCreativeApplication(applicationId: string): Promise<CreativeApplicationConnection> {
    return this.execute(async () => {
      const response = await this.transport.disconnectCreativeApplication(applicationId, true);
      return this.unwrap(response.status, response.body);
    });
  }

  getVersion(): Promise<VersionInfo> {
    return this.transport.getVersion();
  }

  getUpdateStatus(): Promise<SoftwareUpdateStatus> {
    return this.execute(() => this.transport.getUpdateStatus());
  }

  checkForUpdate(): Promise<SoftwareUpdateStatus> {
    return this.execute(() => this.transport.checkForUpdate());
  }

  installUpdate(
    version: string,
    confirmInstall: boolean,
    onProgress: (event: SoftwareUpdateProgress) => void,
  ): Promise<void> {
    return this.execute(() =>
      this.transport.installUpdate(version, confirmInstall, onProgress),
    );
  }

  getLicenseStatus(): Promise<LicenseStatus> {
    return this.transport.getLicenseStatus();
  }

  createLicenseRequest(): Promise<LicenseRequestReceipt> {
    return this.transport.createLicenseRequest();
  }

  importLicenseFile(contents: string): Promise<LicenseStatus> {
    return this.transport.importLicenseFile(contents);
  }

  async getWorkflows(): Promise<WorkflowSummary[]> {
    const data = await this.requestData<{ workflows: WorkflowSummary[] }>({
      method: "GET",
      path: "/api/workflows",
    });
    return data.workflows;
  }

  async getProjects(): Promise<Project[]> {
    const data = await this.requestData<{ projectCount: number; projects: Project[] }>({
      method: "GET",
      path: "/api/projects",
    });
    return data.projects;
  }

  createProject(
    projectName: string,
    workflowId: string,
    description: string,
  ): Promise<Project> {
    return this.requestData({
      method: "POST",
      path: "/api/projects",
      body: { projectName, workflowId, description },
    });
  }

  async importProjectAsset(
    projectId: string,
    confirmImport: boolean,
  ): Promise<Project | null> {
    return this.execute(async () => {
      const response = await this.transport.importProjectAsset(projectId, confirmImport);
      return response ? this.unwrap(response.status, response.body).project : null;
    });
  }

  async getCreativeJobs(): Promise<CreativeJob[]> {
    const data = await this.requestData<{ jobCount: number; jobs: CreativeJob[] }>({
      method: "GET",
      path: "/api/jobs",
    });
    return data.jobs;
  }

  createCreativeJob(request: CreativeJobCreateRequest): Promise<CreativeJob> {
    return this.requestData({ method: "POST", path: "/api/jobs", body: { ...request } });
  }

  getCreativeJob(jobId: string): Promise<CreativeJob> {
    return this.requestData({ method: "GET", path: `/api/jobs/${jobId}` });
  }

  runCreativeJob(
    jobId: string,
    approvalRef?: string,
    confirmExecute = false,
  ): Promise<CreativeJobRunResult> {
    return this.requestData({
      method: "POST",
      path: `/api/jobs/${jobId}/run`,
      body: { approvalRef, confirmExecute },
    });
  }

  cancelCreativeJob(jobId: string, confirmCancel: boolean): Promise<CreativeJob> {
    return this.requestData({
      method: "POST",
      path: `/api/jobs/${jobId}/cancel`,
      body: { confirmCancel },
    });
  }

  async getCreativeJobEvents(jobId: string): Promise<JobHistoryEvent[]> {
    const data = await this.requestData<{
      eventCount: number;
      events: JobHistoryEvent[];
    }>({ method: "GET", path: `/api/jobs/${jobId}/events` });
    return data.events;
  }

  getProjectDelivery(projectId: string): Promise<ProjectDelivery> {
    return this.requestData({
      method: "GET",
      path: `/api/projects/${projectId}/delivery`,
    });
  }

  chooseVectorInput(): Promise<VectorSelection | null> {
    return this.execute(async () => {
      const response = await this.transport.chooseVectorInput();
      return response ? this.unwrap(response.status, response.body) : null;
    });
  }

  startVectorization(request: VectorizationStart): Promise<VectorJob> {
    return this.execute(async () => {
      const response = await this.transport.startVectorization(request);
      return this.unwrap(response.status, response.body);
    });
  }

  getVectorizationJob(jobId: string): Promise<VectorJob> {
    return this.execute(async () => {
      const response = await this.transport.getVectorizationJob(jobId);
      return this.unwrap(response.status, response.body);
    });
  }

  getVectorizationHistory(): Promise<VectorHistory> {
    return this.execute(async () => {
      const response = await this.transport.getVectorizationHistory();
      return this.unwrap(response.status, response.body);
    });
  }

  async openVectorOutput(jobId: string): Promise<void> {
    await this.execute(async () => {
      const response = await this.transport.openVectorOutput(jobId);
      this.unwrap(response.status, response.body);
    });
  }
}
