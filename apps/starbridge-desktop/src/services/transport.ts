import type {
  ApiEnvelope,
  CodexConnectionResetResult,
  CodexConnectorInstallResult,
  CreativeApplicationConnection,
  LicenseRequestReceipt,
  LicenseStatus,
  Project,
  RuntimeStatus,
  SoftwareUpdateProgress,
  SoftwareUpdateStatus,
  TransportRequest,
  TransportResponse,
  VersionInfo,
  VectorHistory,
  VectorJob,
  VectorSelection,
  VectorizationStart,
} from "../types/api";

export class TransportError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly technicalDetails?: string,
  ) {
    super(message);
    this.name = "TransportError";
  }
}

export interface StarBridgeTransport {
  readonly kind: "http" | "desktop";
  request<T>(request: TransportRequest): Promise<TransportResponse<T>>;
  getRuntimeStatus(): Promise<RuntimeStatus>;
  restartBackend(): Promise<RuntimeStatus>;
  openLogsDirectory(): Promise<string>;
  installCodexConnector(
    confirmInstall: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectorInstallResult>>>;
  resetCodexConnection(
    confirmReset: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectionResetResult>>>;
  openCodexPairing(pairingCode: string): Promise<void>;
  openGitHubProject(): Promise<void>;
  pairCreativeApplication(
    applicationId: string,
    confirmPairing: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>>;
  reconnectCreativeApplication(
    applicationId: string,
    confirmReconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>>;
  disconnectCreativeApplication(
    applicationId: string,
    confirmDisconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>>;
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
  importProjectAsset(
    projectId: string,
    confirmImport: boolean,
  ): Promise<TransportResponse<ApiEnvelope<{ asset: unknown; project: Project }>> | null>;
  chooseVectorInput(): Promise<TransportResponse<ApiEnvelope<VectorSelection>> | null>;
  startVectorization(
    request: VectorizationStart,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>>;
  getVectorizationJob(
    jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>>;
  getVectorizationHistory(): Promise<
    TransportResponse<ApiEnvelope<VectorHistory>>
  >;
  openVectorOutput(
    jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<{ opened: boolean }>>>;
}
