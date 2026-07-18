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

  async installCodexConnector(
    _confirmInstall: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectorInstallResult>>> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中配置 Codex 连接器。",
    );
  }

  async resetCodexConnection(
    _confirmReset: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectionResetResult>>> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中重新关联 Codex。",
    );
  }

  async openCodexPairing(_pairingCode: string): Promise<void> {
    throw new TransportError(
      "desktop_required",
      "浏览器预览不能打开本机 Codex 应用。",
    );
  }

  async openGitHubProject(): Promise<void> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中打开 GitHub 项目。",
    );
  }

  async pairCreativeApplication(
    _applicationId: string,
    _confirmPairing: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中配对创意软件。",
    );
  }

  async reconnectCreativeApplication(
    _applicationId: string,
    _confirmReconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中重新连接创意软件。",
    );
  }

  async disconnectCreativeApplication(
    _applicationId: string,
    _confirmDisconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    throw new TransportError(
      "desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中解除创意软件配对。",
    );
  }

  async getVersion(): Promise<VersionInfo> {
    return { desktop: "web-development" };
  }

  async getUpdateStatus(): Promise<SoftwareUpdateStatus> {
    return {
      configured: false,
      source: "GitHub Releases",
      currentVersion: "web-development",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: false,
    };
  }

  async checkForUpdate(): Promise<SoftwareUpdateStatus> {
    throw new TransportError(
      "update_desktop_required",
      "请在安装后的 StarBridge Windows 桌面版中检查更新。",
    );
  }

  async installUpdate(
    _version: string,
    _confirmInstall: boolean,
    _onProgress: (event: SoftwareUpdateProgress) => void,
  ): Promise<void> {
    throw new TransportError(
      "update_desktop_required",
      "浏览器预览不能安装桌面软件更新。",
    );
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

  async importProjectAsset(
    _projectId: string,
    _confirmImport: boolean,
  ): Promise<TransportResponse<ApiEnvelope<{ asset: unknown; project: Project }>> | null> {
    throw new TransportError(
      "desktop_required",
      "浏览器预览不能读取本机文件路径，请在 StarBridge Windows 桌面版中导入素材。",
    );
  }

  async chooseVectorInput(): Promise<
    TransportResponse<ApiEnvelope<VectorSelection>> | null
  > {
    throw new TransportError(
      "desktop_required",
      "请在 StarBridge Windows 桌面版中选择本机图片。",
    );
  }

  async startVectorization(
    _request: VectorizationStart,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>> {
    throw new TransportError(
      "desktop_required",
      "请在 StarBridge Windows 桌面版中运行本机矢量化。",
    );
  }

  async getVectorizationJob(
    _jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>> {
    throw new TransportError("desktop_required", "浏览器预览不读取桌面任务。");
  }

  async getVectorizationHistory(): Promise<
    TransportResponse<ApiEnvelope<VectorHistory>>
  > {
    throw new TransportError("desktop_required", "浏览器预览不读取桌面任务记录。");
  }

  async openVectorOutput(
    _jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<{ opened: boolean }>>> {
    throw new TransportError("desktop_required", "请在桌面版中打开输出文件夹。");
  }
}
