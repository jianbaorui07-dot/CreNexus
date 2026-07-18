import { Channel, invoke as tauriInvoke } from "@tauri-apps/api/core";

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

export type InvokeLike = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

export class DesktopTransport implements StarBridgeTransport {
  readonly kind = "desktop" as const;

  constructor(private readonly invoke: InvokeLike = tauriInvoke) {}

  private async call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
    try {
      return await this.invoke<T>(command, args);
    } catch (error) {
      throw new TransportError(
        "desktop_invoke_failed",
        "StarBridge Desktop 暂时无法完成该操作。",
        error instanceof Error ? error.message : String(error),
      );
    }
  }

  private async callLicense<T>(
    command: "license_status" | "create_license_request" | "import_license_file",
    args?: Record<string, unknown>,
  ): Promise<T> {
    try {
      return await this.invoke<T>(command, args);
    } catch (error) {
      const message =
        typeof error === "string" && error.length <= 180
          ? error
          : "本机授权操作未完成。";
      throw new TransportError(
        "license_action_failed",
        message,
        `Tauri command ${command} rejected the request`,
      );
    }
  }

  private async callUpdate<T>(
    command: "update_channel_status" | "check_for_update" | "install_update",
    args?: Record<string, unknown>,
  ): Promise<T> {
    try {
      return await this.invoke<T>(command, args);
    } catch (error) {
      const message =
        typeof error === "string" && error.length <= 240
          ? error
          : "软件更新操作未完成；当前版本可以继续使用。";
      throw new TransportError(
        "update_action_failed",
        message,
        `Tauri command ${command} rejected the request`,
      );
    }
  }

  request<T>(request: TransportRequest): Promise<TransportResponse<T>> {
    return this.call<TransportResponse<T>>("backend_request", { request });
  }

  getRuntimeStatus(): Promise<RuntimeStatus> {
    return this.call<RuntimeStatus>("backend_status");
  }

  restartBackend(): Promise<RuntimeStatus> {
    return this.call<RuntimeStatus>("restart_backend");
  }

  openLogsDirectory(): Promise<string> {
    return this.call<string>("open_logs_directory");
  }

  installCodexConnector(
    confirmInstall: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectorInstallResult>>> {
    return this.call("install_codex_connector", { confirmInstall });
  }

  resetCodexConnection(
    confirmReset: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CodexConnectionResetResult>>> {
    return this.call("reset_codex_connection", { confirmReset });
  }

  openCodexPairing(pairingCode: string): Promise<void> {
    return this.call("open_codex_pairing", { pairingCode });
  }

  openGitHubProject(): Promise<void> {
    return this.call("open_github_project");
  }

  pairCreativeApplication(
    applicationId: string,
    confirmPairing: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    return this.call("pair_creative_application", { applicationId, confirmPairing });
  }

  reconnectCreativeApplication(
    applicationId: string,
    confirmReconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    return this.call("reconnect_creative_application", { applicationId, confirmReconnect });
  }

  disconnectCreativeApplication(
    applicationId: string,
    confirmDisconnect: boolean,
  ): Promise<TransportResponse<ApiEnvelope<CreativeApplicationConnection>>> {
    return this.call("disconnect_creative_application", { applicationId, confirmDisconnect });
  }

  getVersion(): Promise<VersionInfo> {
    return this.call<VersionInfo>("version_info");
  }

  getUpdateStatus(): Promise<SoftwareUpdateStatus> {
    return this.callUpdate<SoftwareUpdateStatus>("update_channel_status");
  }

  checkForUpdate(): Promise<SoftwareUpdateStatus> {
    return this.callUpdate<SoftwareUpdateStatus>("check_for_update");
  }

  installUpdate(
    version: string,
    confirmInstall: boolean,
    onProgress: (event: SoftwareUpdateProgress) => void,
  ): Promise<void> {
    const channel = new Channel<SoftwareUpdateProgress>();
    channel.onmessage = onProgress;
    return this.callUpdate<void>("install_update", {
      expectedVersion: version,
      confirmInstall,
      onEvent: channel,
    });
  }

  getLicenseStatus(): Promise<LicenseStatus> {
    return this.callLicense<LicenseStatus>("license_status");
  }

  createLicenseRequest(): Promise<LicenseRequestReceipt> {
    return this.callLicense<LicenseRequestReceipt>("create_license_request");
  }

  importLicenseFile(contents: string): Promise<LicenseStatus> {
    return this.callLicense<LicenseStatus>("import_license_file", { contents });
  }

  importProjectAsset(
    projectId: string,
    confirmImport: boolean,
  ): Promise<TransportResponse<ApiEnvelope<{ asset: unknown; project: Project }>> | null> {
    return this.call("import_project_asset", { projectId, confirmImport });
  }

  chooseVectorInput(): Promise<TransportResponse<ApiEnvelope<VectorSelection>> | null> {
    return this.call("choose_vector_input");
  }

  startVectorization(
    request: VectorizationStart,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>> {
    return this.call("start_vectorization", {
      selectionId: request.selectionId,
      mode: request.mode,
      parameters: request.parameters,
      confirmRun: request.confirmRun,
      confirmWrite: request.confirmWrite,
      confirmExport: request.confirmExport,
    });
  }

  getVectorizationJob(
    jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<VectorJob>>> {
    return this.call("vectorization_job", { jobId });
  }

  getVectorizationHistory(): Promise<
    TransportResponse<ApiEnvelope<VectorHistory>>
  > {
    return this.call("vectorization_history");
  }

  openVectorOutput(
    jobId: string,
  ): Promise<TransportResponse<ApiEnvelope<{ opened: boolean }>>> {
    return this.call("open_vector_output", { jobId });
  }
}
