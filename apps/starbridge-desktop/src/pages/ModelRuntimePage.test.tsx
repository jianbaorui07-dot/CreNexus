import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { KORYAOClient } from "../services/client";
import { ModelRuntimePage } from "./ModelRuntimePage";

describe("ModelRuntimePage", () => {
  it("shows the loopback model and privacy boundary", async () => {
    const client = {
      getModelRuntimeStatus: vi.fn().mockResolvedValue({
        schema: "koryao-model-contract/v1",
        serviceId: "koryao-model-runtime",
        serviceVersion: "0.1.0",
        status: "healthy",
        runtimeMode: "local",
        supportedContracts: ["koryao-model-contract/v1"],
        network: { bindAddress: "127.0.0.1", externalNetworkAccess: false },
        privacy: {
          acceptsRawAssets: false,
          logsAbsolutePaths: false,
          logsFullInstructions: false,
        },
        models: [
          {
            modelId: "koryao-c1-planner",
            version: "0.1.0",
            providerId: "rule-based",
            status: "experimental",
            capabilities: ["plan", "evaluate", "repair"],
          },
        ],
      }),
    } as unknown as KORYAOClient;

    render(<ModelRuntimePage client={client} runtimeReady />);
    expect(await screen.findByText("koryao-c1-planner")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1 / LOOPBACK")).toBeInTheDocument();
    expect(screen.getByText("不接收")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新检测" }));
    expect(client.getModelRuntimeStatus).toHaveBeenCalledTimes(2);
  });

  it("does not probe while the KORYAO backend is offline", async () => {
    const client = {
      getModelRuntimeStatus: vi.fn(),
    } as unknown as KORYAOClient;
    render(<ModelRuntimePage client={client} runtimeReady={false} />);
    expect(await screen.findByText("本地模型运行端未连接")).toBeInTheDocument();
    expect(client.getModelRuntimeStatus).not.toHaveBeenCalled();
  });
});
