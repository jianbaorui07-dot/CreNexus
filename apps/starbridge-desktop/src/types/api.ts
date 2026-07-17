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

export type LicenseState = "community" | "active" | "invalid";
export type LicenseEdition = "community" | "pro" | "enterprise";

export interface LicenseStatus {
  state: LicenseState;
  edition: LicenseEdition;
  message: string;
  licenseId?: string;
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
