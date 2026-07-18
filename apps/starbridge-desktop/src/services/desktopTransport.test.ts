import { describe, expect, it, vi } from "vitest";

import { DesktopTransport } from "./desktopTransport";

describe("desktop license transport", () => {
  it("imports a project asset only through the fixed desktop picker command", async () => {
    const invoke = vi.fn().mockResolvedValue(null);
    const transport = new DesktopTransport(invoke);

    await transport.importProjectAsset("project-test", true);

    expect(invoke).toHaveBeenCalledWith("import_project_asset", {
      projectId: "project-test",
      confirmImport: true,
    });
  });

  it("uses fixed commands for the Codex connector lifecycle", async () => {
    const invoke = vi.fn().mockResolvedValue({ status: 200, body: { ok: true } });
    const transport = new DesktopTransport(invoke);

    await transport.installCodexConnector(true);
    await transport.resetCodexConnection(true);
    await transport.openCodexPairing("ABCD2345");
    await transport.openGitHubProject();
    await transport.pairCreativeApplication("photoshop", true);
    await transport.reconnectCreativeApplication("photoshop", true);
    await transport.disconnectCreativeApplication("photoshop", true);

    expect(invoke).toHaveBeenNthCalledWith(1, "install_codex_connector", {
      confirmInstall: true,
    });
    expect(invoke).toHaveBeenNthCalledWith(2, "reset_codex_connection", {
      confirmReset: true,
    });
    expect(invoke).toHaveBeenNthCalledWith(3, "open_codex_pairing", {
      pairingCode: "ABCD2345",
    });
    expect(invoke).toHaveBeenNthCalledWith(4, "open_github_project", undefined);
    expect(invoke).toHaveBeenNthCalledWith(5, "pair_creative_application", {
      applicationId: "photoshop",
      confirmPairing: true,
    });
    expect(invoke).toHaveBeenNthCalledWith(6, "reconnect_creative_application", {
      applicationId: "photoshop",
      confirmReconnect: true,
    });
    expect(invoke).toHaveBeenNthCalledWith(7, "disconnect_creative_application", {
      applicationId: "photoshop",
      confirmDisconnect: true,
    });
  });

  it("preserves the sanitized Rust license rejection for the user", async () => {
    const invoke = vi
      .fn()
      .mockRejectedValue("当前 Community 构建未配置商业版验签公钥。");
    const transport = new DesktopTransport(invoke);

    await expect(transport.importLicenseFile("{}")).rejects.toMatchObject({
      code: "license_action_failed",
      message: "当前 Community 构建未配置商业版验签公钥。",
      technicalDetails: "Tauri command import_license_file rejected the request",
    });
  });

  it("uses only the fixed Rust updater command boundary", async () => {
    const invoke = vi.fn().mockResolvedValue({
      configured: true,
      source: "GitHub Releases",
      currentVersion: "0.1.0",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: true,
    });
    const transport = new DesktopTransport(invoke);

    await transport.checkForUpdate();
    expect(invoke).toHaveBeenCalledWith("check_for_update", undefined);
  });

  it("preserves a safe updater recovery message", async () => {
    const invoke = vi.fn().mockRejectedValue(
      "暂时无法连接 GitHub 检查更新；当前版本可以继续离线使用。",
    );
    const transport = new DesktopTransport(invoke);

    await expect(transport.checkForUpdate()).rejects.toMatchObject({
      code: "update_action_failed",
      message: "暂时无法连接 GitHub 检查更新；当前版本可以继续离线使用。",
    });
  });

  it("does not expose unexpected objects returned by the invoke boundary", async () => {
    const invoke = vi.fn().mockRejectedValue({ localPath: "private" });
    const transport = new DesktopTransport(invoke);

    await expect(transport.createLicenseRequest()).rejects.toMatchObject({
      code: "license_action_failed",
      message: "本机授权操作未完成。",
    });
  });
});
