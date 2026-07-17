import type {
  ApiEnvelope,
  LicenseRequestReceipt,
  LicenseStatus,
  RuntimeStatus,
  TransportRequest,
  VersionInfo,
} from "../types/api";
import { createTransport } from "./runtime";
import { TransportError, type StarBridgeTransport } from "./transport";

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

export interface StarBridgeClient {
  getRuntimeStatus(): Promise<RuntimeStatus>;
  getHealth(): Promise<ApiEnvelope<unknown>>;
  getBootstrap(): Promise<ApiEnvelope<unknown>>;
  restartBackend(): Promise<RuntimeStatus>;
  openLogsDirectory(): Promise<string>;
  getVersion(): Promise<VersionInfo>;
  getLicenseStatus(): Promise<LicenseStatus>;
  createLicenseRequest(): Promise<LicenseRequestReceipt>;
  importLicenseFile(contents: string): Promise<LicenseStatus>;
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
  };

  return new UserFacingError(
    code,
    friendly[code] ?? structured?.message ?? fallback,
    `HTTP ${status}; ${code}`,
    structured?.next_steps ?? [],
    status,
  );
}

export class StarBridgeApiClient implements StarBridgeClient {
  constructor(private readonly transport: StarBridgeTransport = createTransport()) {}

  private async request<T>(request: TransportRequest): Promise<ApiEnvelope<T>> {
    try {
      const response = await this.transport.request<ApiEnvelope<T>>(request);
      if (response.status >= 400 || !response.body.ok) {
        throw errorFromEnvelope(response.status, response.body);
      }
      return response.body;
    } catch (error) {
      if (error instanceof UserFacingError) {
        throw error;
      }
      if (error instanceof TransportError) {
        throw new UserFacingError(
          error.code,
          error.message,
          error.technicalDetails ?? error.code,
          ["查看诊断信息。", "重新启动本地服务后再试。"],
        );
      }
      throw new UserFacingError(
        "unexpected_client_error",
        "StarBridge 暂时无法完成该操作。",
        error instanceof Error ? error.message : String(error),
      );
    }
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

  getVersion(): Promise<VersionInfo> {
    return this.transport.getVersion();
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
}
