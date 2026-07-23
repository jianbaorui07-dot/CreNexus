import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { KORYAOClient } from "../services/client";
import { UserFacingError } from "../services/client";
import type { ConnectionOverview, RuntimeStatus } from "../types/api";
import { App } from "./App";

const PAIRED_CONNECTIONS: ConnectionOverview = {
  schema_version: "starbridge.desktop-connections.v2",
  checked_at: "2026-07-18T08:00:00Z",
  drawing_enabled: true,
  codex: {
    state: "paired",
    app_available: true,
    connector_configured: true,
    session_paired: true,
    pairing_code: "ABCD2345",
    message: "Codex 已关联当前桌面会话，制图入口已开放。",
    next_steps: [],
  },
  applications: [],
  safety: {
    loopback_only: true,
    credentials_read: false,
    external_apps_force_restarted: false,
  },
};

function makeClient(status: RuntimeStatus | Promise<RuntimeStatus>): KORYAOClient {
  return {
    getRuntimeStatus: vi.fn().mockImplementation(() => Promise.resolve(status)),
    getHealth: vi.fn().mockResolvedValue({ ok: true }),
    getBootstrap: vi.fn().mockResolvedValue({ ok: true }),
    restartBackend: vi.fn().mockResolvedValue({
      state: "connected",
      message: "本地服务已恢复。",
      recoveryAttempts: 1,
    }),
    openLogsDirectory: vi.fn().mockResolvedValue("<LOCAL_APP_DATA>/KORYAO/logs"),
    openProjectArtifacts: vi
      .fn()
      .mockResolvedValue("<LOCAL_APP_DATA>/KORYAO/artifacts/project-test"),
    exportAdobeFile: vi.fn().mockResolvedValue(null),
    listAdobeExports: vi.fn().mockResolvedValue([]),
    getConnections: vi.fn().mockResolvedValue(PAIRED_CONNECTIONS),
    getModelRuntimeStatus: vi.fn().mockRejectedValue(new Error("model runtime offline")),
    installCodexConnector: vi.fn().mockResolvedValue({
      installed: true,
      connector: "starbridge-desktop",
      message: "连接器已安装。",
      restart_required: true,
      next_steps: [],
    }),
    resetCodexConnection: vi.fn().mockResolvedValue({ reset: true, pairing_code: "WXYZ6789" }),
    openCodexPairing: vi.fn().mockResolvedValue(undefined),
    openCodexTask: vi.fn().mockResolvedValue(undefined),
    openGitHubProject: vi.fn().mockResolvedValue(undefined),
    pairCreativeApplication: vi.fn(),
    reconnectCreativeApplication: vi.fn(),
    disconnectCreativeApplication: vi.fn(),
    getVersion: vi.fn().mockResolvedValue({ desktop: "0.1.0" }),
    getUpdateStatus: vi.fn().mockResolvedValue({
      configured: false,
      source: "GitHub Releases",
      currentVersion: "0.1.0",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: false,
    }),
    checkForUpdate: vi.fn().mockResolvedValue({
      configured: false,
      source: "GitHub Releases",
      currentVersion: "0.1.0",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: false,
    }),
    installUpdate: vi.fn().mockResolvedValue(undefined),
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
      fileName: "KORYAO-license-request-request-test.json",
      location: "<LOCAL_APP_DATA>/KORYAO/license/requests",
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
    getWorkflows: vi.fn().mockResolvedValue([]),
    getProjects: vi.fn().mockResolvedValue([]),
    createProject: vi.fn(),
    importProjectAsset: vi.fn().mockResolvedValue(null),
    getCreativeJobs: vi.fn().mockResolvedValue([]),
    createCreativeJob: vi.fn(),
    getCreativeJob: vi.fn(),
    runCreativeJob: vi.fn(),
    cancelCreativeJob: vi.fn(),
    getCreativeJobEvents: vi.fn().mockResolvedValue([]),
    getProjectDelivery: vi.fn(),
    chooseVectorInput: vi.fn().mockResolvedValue(null),
    startVectorization: vi.fn(),
    getVectorizationJob: vi.fn(),
    getVectorizationHistory: vi.fn().mockResolvedValue({ eventCount: 0, events: [] }),
    openVectorOutput: vi.fn().mockResolvedValue(undefined),
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

describe("desktop runtime status", () => {
  it("shows the product home while the runtime starts", () => {
    const pending = new Promise<RuntimeStatus>(() => undefined);
    render(<App client={makeClient(pending)} />);

    expect(screen.getByText("从项目开始一次可审计的创作")).toBeInTheDocument();
    expect(screen.getByText("正在启动")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "连接 Codex 后开始制图" })).toBeDisabled();
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
    expect(await screen.findByRole("button", { name: "新建或打开项目" })).toBeEnabled();
    expect(screen.queryByText(/49152/)).not.toBeInTheDocument();
  });

  it("does not report that projects are empty while the local project list is still loading", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    const projectsRequest = deferred<Awaited<ReturnType<KORYAOClient["getProjects"]>>>();
    client.getProjects = vi.fn().mockReturnValue(projectsRequest.promise);

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "项目" }));

    expect(await screen.findByText("正在读取本机项目")).toBeInTheDocument();
    expect(screen.queryByText("还没有项目")).not.toBeInTheDocument();

    projectsRequest.resolve([]);
    expect(await screen.findByText("还没有项目")).toBeInTheDocument();
  });

  it("does not present a failed project read as an empty customer account", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    client.getProjects = vi.fn().mockRejectedValue(new Error("本机服务暂时没有响应。"));

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "项目" }));

    expect(await screen.findByText("项目列表没有载入")).toBeInTheDocument();
    expect(screen.getByText("本机服务暂时没有响应。")).toBeInTheDocument();
    expect(screen.queryByText("还没有项目")).not.toBeInTheDocument();
  });

  it("keeps delivery in a loading state until the selected project's records arrive", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    const project = {
      schemaVersion: 1,
      projectId: "project-delivery-loading",
      projectName: "客户交付加载测试",
      workflowId: "vector-delivery-v1",
      description: "",
      sourceAssets: [],
      currentJob: null,
      jobHistory: [],
      artifacts: [],
      qualityReports: [],
      evidence: [],
      createdAt: "2026-07-22T08:00:00Z",
      updatedAt: "2026-07-22T08:00:00Z",
    } as const;
    const deliveryRequest = deferred<Awaited<ReturnType<KORYAOClient["getProjectDelivery"]>>>();
    client.getProjects = vi.fn().mockResolvedValue([project]);
    client.getProjectDelivery = vi.fn().mockReturnValue(deliveryRequest.promise);
    client.listAdobeExports = vi.fn().mockResolvedValue([]);

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "交付与证据" }));

    expect(await screen.findByText("正在读取交付记录")).toBeInTheDocument();
    expect(screen.queryByText("这个项目还没有可交付产物")).not.toBeInTheDocument();

    deliveryRequest.resolve({
      projectId: project.projectId,
      projectName: project.projectName,
      artifacts: [],
      evidenceIds: [],
      formats: [],
      fabricatedOutputs: false,
    });
    expect(await screen.findByText("这个项目还没有可交付产物")).toBeInTheDocument();
  });

  it("opens the fixed GitHub project from the top bar", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "GitHub 项目" }));
    expect(client.openGitHubProject).toHaveBeenCalledOnce();
  });

  it("locks drawing until the current Codex session is paired", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    client.getConnections = vi.fn().mockResolvedValue({
      ...PAIRED_CONNECTIONS,
      drawing_enabled: false,
      codex: {
        ...PAIRED_CONNECTIONS.codex,
        state: "awaiting_pairing",
        session_paired: false,
        message: "连接器已配置，正在等待 Codex 确认当前桌面会话。",
      },
    });
    render(<App client={client} />);

    const connect = await screen.findByRole("button", { name: "连接 Codex 后开始制图" });
    fireEvent.click(connect);
    expect(await screen.findByText("先关联 Codex，再连接本机创意软件")).toBeInTheDocument();
    expect(screen.getByText("ABCD2345")).toBeInTheDocument();
  });

  it("installs the managed connector before opening a new Codex pairing task", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    client.getConnections = vi.fn().mockResolvedValue({
      ...PAIRED_CONNECTIONS,
      drawing_enabled: false,
      codex: {
        ...PAIRED_CONNECTIONS.codex,
        state: "connector_required",
        connector_configured: false,
        session_paired: false,
        message: "已找到 Codex；需要安装 KORYAO 本地连接器。",
      },
    });
    client.installCodexConnector = vi.fn().mockResolvedValue({
      installed: true,
      connector: "starbridge-desktop",
      message: "旧版 Codex 连接器已备份并迁移到 KORYAO 托管配置。",
      migrated_existing_connector: true,
      backup_created: true,
      backup_file: "config.koryao-backup-example.toml",
      restart_required: true,
      next_steps: [],
    });
    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "连接 Codex 后开始制图" }));
    fireEvent.click(await screen.findByRole("button", { name: "安装连接器并打开 Codex" }));

    await waitFor(() => expect(client.installCodexConnector).toHaveBeenCalledWith(true));
    expect(client.openCodexPairing).toHaveBeenCalledWith("ABCD2345");
    expect(
      await screen.findByText("已备份旧 Codex 配置并安全迁移同名连接器。首次安装后请完全退出并重新打开 Codex，再新建任务发送关联指令。"),
    ).toBeInTheDocument();
  });

  it("pairs a running creative application without claiming a process-only bridge can edit", async () => {
    const client = makeClient({
      state: "connected",
      message: "安全本地服务已经就绪。",
      recoveryAttempts: 0,
    });
    const blender = {
      id: "blender",
      name: "Blender",
      mark: "Bl",
      state: "running" as const,
      installed: true,
      running: true,
      bridge_available: false,
      managed: false,
      message: "软件正在运行，等待与当前 KORYAO 会话配对。",
      pairing_state: "ready_to_pair" as const,
      paired: false,
      adapter_kind: "process" as const,
      control_level: "session_detection" as const,
      capabilities: ["进程会话检测", "本机任务路由"],
      next_steps: [],
    };
    client.getConnections = vi.fn().mockResolvedValue({
      ...PAIRED_CONNECTIONS,
      applications: [blender],
    });
    client.pairCreativeApplication = vi.fn().mockResolvedValue({
      ...blender,
      paired: true,
      pairing_state: "paired_limited",
      message: "当前软件会话已配对；目前仅支持检测和任务路由。",
    });
    render(<App client={client} />);

    fireEvent.click(await screen.findByRole("button", { name: "连接中心" }));
    fireEvent.click(await screen.findByRole("button", { name: "开始配对" }));

    await waitFor(() => expect(client.pairCreativeApplication).toHaveBeenCalledWith("blender"));
    expect(await screen.findByText(/当前仅提供存在性检测和任务路由/)).toBeInTheDocument();
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

  it("shows a signed GitHub update and requires explicit install confirmation", async () => {
    const client = makeClient({ state: "connected", message: "connected", recoveryAttempts: 0 });
    const update = {
      configured: true,
      source: "GitHub Releases",
      currentVersion: "0.1.0",
      available: true,
      version: "0.2.0",
      notes: "稳定性改进",
      signatureRequired: true,
      automaticChecksSupported: true,
    };
    client.getUpdateStatus = vi.fn().mockResolvedValue(update);
    client.checkForUpdate = vi.fn().mockResolvedValue(update);
    render(<App client={client} />);

    expect(await screen.findByRole("button", { name: "可更新至 v0.2.0" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "可更新至 v0.2.0" }));
    const install = screen.getByRole("button", { name: "更新到 v0.2.0" });
    expect(install).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /我已保存正在进行的工作/ }));
    expect(install).toBeEnabled();
    fireEvent.click(install);
    await waitFor(() => expect(client.installUpdate).toHaveBeenCalledWith(
      "0.2.0",
      true,
      expect.any(Function),
    ));
  });

  it("states that a development build cannot claim public updates", async () => {
    render(<App client={makeClient({ state: "connected", message: "connected", recoveryAttempts: 0 })} />);
    fireEvent.click(await screen.findByRole("button", { name: "打开设置与诊断" }));
    expect(screen.getByText("发布通道未启用")).toBeInTheDocument();
    expect(screen.getByText(/没有正式更新验签公钥/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "立即检查更新" })).not.toBeInTheDocument();
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

  it("builds a Community workflow task from an imported project asset", async () => {
    const client = makeClient({
      state: "connected",
      message: "运行正常。",
      recoveryAttempts: 0,
    });
    const project = {
      schemaVersion: 1,
      projectId: "project-test",
      projectName: "品牌图标",
      workflowId: "vector-delivery-v1",
      description: "",
      sourceAssets: [{
        assetId: "asset-test",
        basename: "example.png",
        relativePath: "projects/project-test/source/example.png",
        sha256: "a".repeat(64),
        mediaType: "image/png",
        sizeBytes: 2048,
        importedAt: "2026-07-17T08:00:00Z",
      }],
      currentJob: null,
      jobHistory: [],
      artifacts: [],
      qualityReports: [],
      evidence: [],
      createdAt: "2026-07-17T08:00:00Z",
      updatedAt: "2026-07-17T08:00:00Z",
    } as const;
    const job = {
      schemaVersion: 1,
      jobId: "job-test",
      projectId: "project-test",
      workflowId: "vector-delivery-v1",
      status: "queued",
      currentStep: "validate-source",
      progress: 0,
      createdAt: "2026-07-17T08:00:00Z",
      updatedAt: "2026-07-17T08:00:00Z",
      completedAt: null,
      artifacts: [],
      warnings: [],
      error: null,
      evidenceId: null,
    } as const;
    client.getProjects = vi.fn().mockResolvedValue([project]);
    client.getWorkflows = vi.fn().mockResolvedValue([{
      workflowId: "vector-delivery-v1",
      name: "图片 → 精确重建 → 绘制型矢量 → 交付",
      capabilityStatus: "experimental",
      recommended: true,
      ordinaryCustomerRoute: true,
      requiresConfirmation: true,
      drawingModes: ["artisan", "smart", "lightweight", "exact"],
      imageTraceFallback: false,
    }]);
    client.createCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJobEvents = vi.fn().mockResolvedValue([]);

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "图片矢量化" }));
    expect(await screen.findByText("example.png")).toBeInTheDocument();
    expect(screen.getAllByText(/像素重建/).length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: "像素重建图标" })).toBeInTheDocument();
    expect(screen.getByText("像素重建 / PIXEL RECONSTRUCTION")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "选择像素重建模式" }));
    fireEvent.change(screen.getByLabelText("像素重建最长边"), { target: { value: "512" } });
    fireEvent.change(screen.getByLabelText("SVG 安全上限"), { target: { value: "64" } });
    const createButton = screen.getByRole("button", { name: "建立像素重建任务" });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    await waitFor(() => expect(client.createCreativeJob).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: "project-test",
        sourceAssetId: "asset-test",
        drawingMode: "exact",
        parameters: { exact: { maxDimension: 512, maxSvgSizeMb: 64 } },
      }),
    ));
    expect((await screen.findAllByText("等待开始")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "运行到下一确认点" })).toBeInTheDocument();
  });

  it("builds a single confirmed ComfyUI task plan from temporary inputs", async () => {
    const client = makeClient({
      state: "connected",
      message: "运行正常。",
      recoveryAttempts: 0,
    });
    const project = {
      schemaVersion: 1,
      projectId: "project-comfy",
      projectName: "夏季海报概念图",
      workflowId: "comfyui-generation-v1",
      description: "",
      sourceAssets: [],
      currentJob: null,
      jobHistory: [],
      artifacts: [],
      qualityReports: [],
      evidence: [],
      createdAt: "2026-07-17T08:00:00Z",
      updatedAt: "2026-07-17T08:00:00Z",
    } as const;
    const job = {
      schemaVersion: 1,
      jobId: "job-comfy",
      projectId: "project-comfy",
      workflowId: "comfyui-generation-v1",
      status: "queued",
      currentStep: "validate-workflow",
      progress: 0,
      createdAt: "2026-07-17T08:00:00Z",
      updatedAt: "2026-07-17T08:00:00Z",
      completedAt: null,
      artifacts: [],
      warnings: [],
      error: null,
      evidenceId: null,
    } as const;
    client.getProjects = vi.fn().mockResolvedValue([project]);
    client.createCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJobEvents = vi.fn().mockResolvedValue([]);

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "AI 图片生成" }));
    await screen.findByRole("option", { name: "夏季海报概念图" });
    fireEvent.change(screen.getByLabelText("正向提示词"), {
      target: { value: "minimal summer poster, warm light" },
    });
    fireEvent.change(screen.getByLabelText("负向提示词（可选）"), {
      target: { value: "watermark" },
    });
    fireEvent.change(screen.getByLabelText("Checkpoint 文件名"), {
      target: { value: "local-model.safetensors" },
    });
    const createButton = screen.getByRole("button", { name: "建立生成任务计划" });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    await waitFor(() => expect(client.createCreativeJob).toHaveBeenCalledTimes(1));
    expect(client.createCreativeJob).toHaveBeenCalledWith({
      projectId: "project-comfy",
      workflowId: "comfyui-generation-v1",
      prompt: "minimal summer poster, warm light",
      negativePrompt: "watermark",
      checkpointName: "local-model.safetensors",
      width: 512,
      height: 512,
      steps: 24,
      cfg: 7,
      sampler: "dpmpp_2m",
      scheduler: "karras",
      waitSeconds: 0,
    });
    expect((await screen.findAllByText("等待开始")).length).toBeGreaterThan(0);
  });

  it("builds a fixed Photoshop copy-first task from a managed project image", async () => {
    const client = makeClient({ state: "connected", message: "运行正常。", recoveryAttempts: 0 });
    const project = {
      schemaVersion: 1,
      projectId: "project-photoshop",
      projectName: "Photoshop 安全副本",
      workflowId: "photoshop-production-v1",
      description: "",
      sourceAssets: [{
        assetId: "asset-photoshop",
        basename: "selected-image.png",
        relativePath: "projects/project-photoshop/source/asset-photoshop.png",
        sha256: "b".repeat(64),
        mediaType: "image/png",
        sizeBytes: 4096,
        importedAt: "2026-07-18T08:00:00Z",
      }],
      currentJob: null,
      jobHistory: [],
      artifacts: [],
      qualityReports: [],
      evidence: [],
      createdAt: "2026-07-18T08:00:00Z",
      updatedAt: "2026-07-18T08:00:00Z",
    } as const;
    const job = {
      schemaVersion: 1,
      jobId: "job-photoshop",
      projectId: "project-photoshop",
      workflowId: "photoshop-production-v1",
      status: "queued",
      currentStep: "validate-source",
      progress: 0,
      createdAt: "2026-07-18T08:00:00Z",
      updatedAt: "2026-07-18T08:00:00Z",
      completedAt: null,
      artifacts: [],
      warnings: [],
      error: null,
      evidenceId: null,
    } as const;
    client.getProjects = vi.fn().mockResolvedValue([project]);
    client.createCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJob = vi.fn().mockResolvedValue(job);
    client.getCreativeJobEvents = vi.fn().mockResolvedValue([]);

    render(<App client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "项目" }));
    expect(await screen.findByText("selected-image.png")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开工作流" }));
    expect(await screen.findByText("只修改受控副本，再导出真实文件")).toBeInTheDocument();
    const createButton = screen.getByRole("button", { name: "建立 Photoshop 任务计划" });
    await waitFor(() => expect(createButton).toBeEnabled());
    fireEvent.click(createButton);

    await waitFor(() => expect(client.createCreativeJob).toHaveBeenCalledTimes(1));
    expect(client.createCreativeJob).toHaveBeenCalledWith(expect.objectContaining({
      projectId: "project-photoshop",
      workflowId: "photoshop-production-v1",
      sourceAssetId: "asset-photoshop",
      outputFormats: ["png", "jpeg", "psd"],
      resizeCanvas: false,
      brightness: 0,
      contrast: 0,
      saturation: 0,
      exportSubject: false,
    }));
    expect((await screen.findAllByText("等待开始")).length).toBeGreaterThan(0);
  });
});
