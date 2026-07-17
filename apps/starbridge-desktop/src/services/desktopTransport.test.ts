import { describe, expect, it, vi } from "vitest";

import { DesktopTransport } from "./desktopTransport";

describe("desktop license transport", () => {
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

  it("does not expose unexpected objects returned by the invoke boundary", async () => {
    const invoke = vi.fn().mockRejectedValue({ localPath: "private" });
    const transport = new DesktopTransport(invoke);

    await expect(transport.createLicenseRequest()).rejects.toMatchObject({
      code: "license_action_failed",
      message: "本机授权操作未完成。",
    });
  });
});
