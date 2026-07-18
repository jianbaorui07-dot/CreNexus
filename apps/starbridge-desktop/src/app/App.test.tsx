import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StarBridgeClient } from "../services/client";
import { UserFacingError } from "../services/client";
import type { RuntimeStatus } from "../types/api";
import { App } from "./App";

function makeClient(status: RuntimeStatus | Promise<RuntimeStatus>): StarBridgeClient {
  return {
    getRuntimeStatus: vi.fn().mockImplementation(() => Promise.resolve(status)),
    getHealth: vi.fn().mockResolvedValue({ ok: true }),
    getBootstrap: vi.fn().mockResolvedValue({ ok: true }),
    restartBackend: vi.fn().mockResolvedValue({
      state: "connected",
      message: "本地服务已恢复。",
      recoveryAttempts: 1,
    }),
    openLogsDirectory: vi.fn().mockResolvedValue("<LOCAL_APP_DATA>/StarBridge/logs"),
    getVersion: vi.fn().mockResolvedValue({ desktop: "0.1.0" }),
    getLicenseStatus: vi.fn().mockResolvedValue({
      state: "community",
      edition: "community",
      message: "Community 免费版正在本机运行，不需要授权文件。",
      deviceLimit: 0,
      features: [],
      commercialVerifierConfigured: false,
    }),
    createLicenseRequest: vi.fn().mockResolvedValue({
      requestId: "request-test",
      fileName: "StarBridge-license-request-request-test.json",
      location: "<LOCAL_APP_DATA>/StarBridge/license/requests",
      folderOpened: true,
    }),
    importLicenseFile: vi.fn().mockResolvedValue({
      state: "active",
      edition: "pro",
      message: "离线授权签名和当前设备绑定均已验证。",
      licenseId: "SB-PRO-TEST",
      deviceLimit: 1,
      features: ["batch.processing"],
      commercialVerifierConfigured: true,
    }),
    chooseVectorInput: vi.fn().mockResolvedValue(null),
    startVectorization: vi.fn(),
    getVectorizationJob: vi.fn(),
    getVectorizationHistory: vi.fn().mockResolvedValue({ eventCount: 0, events: [] }),
    openVectorOutput: vi.fn().mockResolvedValue(undefined),
  };
}

describe("desktop runtime status", () => {
  it("shows the product home while the runtime starts", () => {
    const pending = new Promise<RuntimeStatus>(() => undefined);
    render(<App client={makeClient(pending)} />);

    expect(screen.getByText("StarBridge 已准备好")).toBeInTheDocument();
    expect(screen.getByText("正在启动")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始图片矢量化" })).toBeDisabled();
  });

  it("shows a connected state in ordinary language", async () => {
    render(
      <App
        client={makeClient({
          state: "connected",
          message: "安全本地服务已经就绪。",
          recoveryAttempts: 0,
          port: 49152,
        })}
      />,
    );

    expect(await screen.findByText("运行正常 · 仅本机")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始图片矢量化" })).toBeEnabled();
    expect(screen.queryByText(/49152/)).not.toBeInTheDocument();
  });

  it("shows offline recovery guidance and technical details", async () => {
    render(
      <App
        client={makeClient({
          state: "offline",
          message: "没有检测到本地服务，请尝试重新启动。",
          recoveryAttempts: 1,
          technicalDetails: "backend process not found",
        })}
      />,
    );

    expect(await screen.findByText("本地服务离线")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开设置与诊断" }));
    expect(screen.getByRole("button", { name: "重新启动本地服务" })).toBeInTheDocument();
    expect(screen.getByText("技术详情")).toBeInTheDocument();
    expect(screen.getByText("backend process not found")).toBeInTheDocument();
  });

  it("turns a 401 or 403 style error into a user-facing failure", async () => {
    const client = makeClient({
      state: "connected",
      message: "connected",
      recoveryAttempts: 0,
    });
    client.getRuntimeStatus = vi.fn().mockRejectedValue(
      new UserFacingError(
        "authentication_failed",
        "桌面会话已失效，请重新启动本地服务。",
        "HTTP 403; authentication_failed",
        [],
        403,
      ),
    );
    render(<App client={client} />);

    expect(await screen.findByText("需要处理")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开设置与诊断" }));
    expect(screen.getByText("桌面会话已失效，请重新启动本地服务。")).toBeInTheDocument();
    expect(screen.getByText("HTTP 403; authentication_failed")).toBeInTheDocument();
  });

  it("offers a manual restart and reports recovery", async () => {
    const client = makeClient({
      state: "failed",
      message: "启动失败。",
      recoveryAttempts: 1,
    });
    render(<App client={client} />);
    await screen.findByText("需要处理");
    fireEvent.click(screen.getByRole("button", { name: "打开设置与诊断" }));

    fireEvent.click(screen.getByRole("button", { name: "重新启动本地服务" }));

    await waitFor(() => expect(client.restartBackend).toHaveBeenCalledOnce());
    expect(await screen.findByText("运行正常 · 仅本机")).toBeInTheDocument();
  });

  it("shows the offline Community license flow without claiming Pro is active", async () => {
    const client = makeClient({
      state: "connected",
      message: "connected",
      recoveryAttempts: 0,
    });
    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "版本与授权" }));
    expect(screen.getByText("你可以直接使用免费功能，无需登录、无需联网，也不需要授权文件。"))
      .toBeInTheDocument();
    expect(screen.queryByText("授权有效")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导出设备申请" }));
    await waitFor(() => expect(client.createLicenseRequest).toHaveBeenCalledOnce());
    expect(await screen.findByText(/文件夹已打开/)).toBeInTheDocument();
  });

  it("explains how to recover from an invalid license while keeping Community available", async () => {
    const client = makeClient({ state: "connected", message: "connected", recoveryAttempts: 0 });
    client.getLicenseStatus = vi.fn().mockResolvedValue({
      state: "invalid",
      edition: "community",
      message: "授权签名未通过验证。",
      deviceLimit: 0,
      features: [],
      commercialVerifierConfigured: true,
      reason: "signature_invalid",
    });
    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "版本与授权" }));
    expect(screen.getByText("授权文件未生效")).toBeInTheDocument();
    expect(screen.getByText(/授权签名未通过验证/)).toBeInTheDocument();
    expect(screen.getByText(/Community 免费功能仍可继续使用/)).toBeInTheDocument();
  });

  it("runs the Community vectorization flow through selection, confirmation and result", async () => {
    const client = makeClient({
      state: "connected",
      message: "运行正常。",
      recoveryAttempts: 0,
    });
    client.chooseVectorInput = vi.fn().mockResolvedValue({
      selectionId: "selection-test",
      fileName: "example.png",
      width: 320,
      height: 240,
      sourceHash: "abc123",
      previewDataUrl: "data:image/png;base64,AA==",
    });
    client.startVectorization = vi.fn().mockResolvedValue({
      jobId: "vector-test",
      status: "queued",
      progress: 6,
      stage: "已确认，正在准备",
      mode: "smart",
      createdAt: "2026-07-17T08:00:00Z",
    });
    client.getVectorizationJob = vi.fn().mockResolvedValue({
      jobId: "vector-test",
      status: "completed",
      progress: 100,
      stage: "处理完成",
      mode: "smart",
      createdAt: "2026-07-17T08:00:00Z",
      completedAt: "2026-07-17T08:00:01Z",
      result: {
        modeLabel: "智能矢量",
        sourceHash: "abc123",
        sourcePreviewDataUrl: "data:image/png;base64,AA==",
        resultPreviewDataUrl: "data:image/png;base64,AA==",
        metrics: { colors: 8, subpaths: 12, points: 36, svgBytes: 2048, elapsedSeconds: 1.2 },
        warnings: [],
        outputAvailable: true,
      },
    });

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "开始图片矢量化" }));
    fireEvent.click(screen.getByRole("button", { name: "选择图片" }));
    expect(await screen.findByText("example.png")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "开始本机矢量化" }));

    await waitFor(() => expect(client.startVectorization).toHaveBeenCalledWith(
      expect.objectContaining({
        selectionId: "selection-test",
        confirmRun: true,
        confirmWrite: true,
        confirmExport: true,
      }),
    ));
    expect(await screen.findByText("任务记录已保存，输出位于 StarBridge 本机应用数据目录。", {}, { timeout: 2000 })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开输出文件夹" }));
    await waitFor(() => expect(client.openVectorOutput).toHaveBeenCalledWith("vector-test"));
  });
});
