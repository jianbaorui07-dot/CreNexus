import type {
  LicenseRequestReceipt,
  LicenseStatus,
  RuntimeStatus,
  TransportRequest,
  TransportResponse,
  VersionInfo,
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
  getVersion(): Promise<VersionInfo>;
  getLicenseStatus(): Promise<LicenseStatus>;
  createLicenseRequest(): Promise<LicenseRequestReceipt>;
  importLicenseFile(contents: string): Promise<LicenseStatus>;
}
