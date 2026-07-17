import type {
  ApiEnvelope,
  LicenseRequestReceipt,
  LicenseStatus,
  RuntimeStatus,
  TransportRequest,
  TransportResponse,
  VersionInfo,
} from "../types/api";
import { TransportError, type StarBridgeTransport } from "./transport";

type FetchLike = typeof fetch;

export class HttpTransport implements StarBridgeTransport {
  readonly kind = "http" as const;

  constructor(
    private readonly baseUrl = "http://127.0.0.1:8765",
    private readonly fetchImpl: FetchLike = fetch,
  ) {}

  async request<T>(request: TransportRequest): Promise<TransportResponse<T>> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (request.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${request.path}`, {
        method: request.method,
        headers,
        body: request.body === undefined ? undefined : JSON.stringify(request.body),
        cache: "no-store",
      });
    } catch (error) {
      throw new TransportError(
        "backend_offline",
        "本地服务没有响应。",
        error instanceof Error ? error.message : "HTTP request failed",
      );
    }

    const raw = await response.text();
    try {
      return {
        status: response.status,
        body: (raw ? JSON.parse(raw) : {}) as T,
      };
    } catch {
      throw new TransportError(
        "invalid_backend_response",
        "本地服务返回了无法识别的结果。",
        `HTTP ${response.status}; response was not JSON`,
      );
    }
  }

  async getRuntimeStatus(): Promise<RuntimeStatus> {
    try {
      const response = await this.request<ApiEnvelope<unknown>>({
        method: "GET",
        path: "/api/health",
      });
      if (response.status === 200 && response.body.ok) {
        return {
          state: "connected",
          message: "本地开发服务已连接。",
          recoveryAttempts: 0,
        };
      }
    } catch {
      // The user-facing status below is more useful than a raw fetch exception.
    }
    return {
      state: "offline",
      message: "本地开发服务尚未启动。",
      recoveryAttempts: 0,
      technicalDetails: `Expected ${this.baseUrl}/api/health`,
    };
  }

  async restartBackend(): Promise<RuntimeStatus> {
    throw new TransportError(
      "desktop_required",
      "浏览器开发模式不能管理本地服务进程。",
      "Start the development backend from the repository scripts.",
    );
  }

  async openLogsDirectory(): Promise<string> {
    throw new TransportError(
      "desktop_required",
      "浏览器开发模式不能打开应用日志目录。",
    );
  }

  async getVersion(): Promise<VersionInfo> {
    return { desktop: "web-development" };
  }

  async getLicenseStatus(): Promise<LicenseStatus> {
    return {
      state: "community",
      edition: "community",
      message: "浏览器开发模式使用 Community 功能，不处理商业授权文件。",
      deviceLimit: 0,
      features: [],
      commercialVerifierConfigured: false,
    };
  }

  async createLicenseRequest(): Promise<LicenseRequestReceipt> {
    throw new TransportError(
      "desktop_required",
      "请在 StarBridge Windows 桌面版中导出设备授权申请。",
    );
  }

  async importLicenseFile(_contents: string): Promise<LicenseStatus> {
    throw new TransportError(
      "desktop_required",
      "请在 StarBridge Windows 桌面版中导入授权文件。",
    );
  }
}
