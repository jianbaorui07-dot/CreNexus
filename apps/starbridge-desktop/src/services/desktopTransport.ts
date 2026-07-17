import { invoke as tauriInvoke } from "@tauri-apps/api/core";

import type {
  LicenseRequestReceipt,
  LicenseStatus,
  RuntimeStatus,
  TransportRequest,
  TransportResponse,
  VersionInfo,
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

  getVersion(): Promise<VersionInfo> {
    return this.call<VersionInfo>("version_info");
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
}
