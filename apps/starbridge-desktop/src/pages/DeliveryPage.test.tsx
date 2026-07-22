import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CreNexusClient } from "../services/client";
import type { Project, ProjectDelivery } from "../types/api";
import { DeliveryPage } from "./DeliveryPage";

const PROJECT = {
  schemaVersion: 1,
  projectId: "project-test",
  projectName: "客户项目",
  workflowId: "vector-delivery-v1",
  description: "",
  sourceAssets: [],
  currentJob: null,
  jobHistory: [],
  artifacts: [],
  qualityReports: [],
  evidence: [],
  createdAt: "2026-07-22T00:00:00Z",
  updatedAt: "2026-07-22T00:00:00Z",
} satisfies Project;

const DELIVERY = {
  projectId: "project-test",
  projectName: "客户项目",
  artifacts: [
    {
      artifactId: "artifact-svg",
      kind: "smart-vector",
      basename: "vector.svg",
      relativePath: "artifacts/project-test/job-test/vector.svg",
      sha256: "a".repeat(64),
      mediaType: "image/svg+xml",
      sizeBytes: 2048,
      createdAt: "2026-07-22T00:00:00Z",
      metadata: {},
    },
  ],
  evidenceIds: ["evidence-test"],
  formats: ["svg"],
  fabricatedOutputs: false,
} satisfies ProjectDelivery;

describe("Adobe delivery export", () => {
  it("restores safe history, requires confirmation, and reports a native AI receipt without exposing a path", async () => {
    const exportAdobeFile = vi.fn().mockResolvedValue({
      receiptId: "receipt-new",
      format: "ai",
      fileName: "customer.ai",
      sizeBytes: 4096,
      sourceBasename: "vector.svg",
      sha256: "b".repeat(64),
      createdAtUnixSeconds: 1784678400,
      nativeReopenValidated: true,
      sourceOverwritten: false,
      targetPathPersisted: false,
      historyRecorded: true,
    });
    const listAdobeExports = vi.fn().mockResolvedValue([{
      receiptId: "receipt-existing",
      format: "psd",
      fileName: "historical.psd",
      sizeBytes: 8192,
      sourceBasename: "preview.png",
      sha256: "c".repeat(64),
      createdAtUnixSeconds: 1784592000,
      nativeReopenValidated: true,
      sourceOverwritten: false,
      targetPathPersisted: false,
      historyRecorded: true,
    }]);
    const client = {
      getProjects: vi.fn().mockResolvedValue([PROJECT]),
      getProjectDelivery: vi.fn().mockResolvedValue(DELIVERY),
      openProjectArtifacts: vi.fn(),
      exportAdobeFile,
      listAdobeExports,
    } as unknown as CreNexusClient;

    render(<DeliveryPage client={client} initialProjectId="project-test" />);
    await screen.findByRole("option", { name: /vector\.svg/ });
    expect(await screen.findByText("historical.psd")).toBeInTheDocument();
    expect(listAdobeExports).toHaveBeenCalledWith("project-test");
    expect(screen.queryByText(/C:\\/)).not.toBeInTheDocument();
    const exportButton = screen.getByRole("button", { name: "选择路径并导出 .ai" });
    expect(exportButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(exportButton);

    await waitFor(() => expect(exportAdobeFile).toHaveBeenCalledWith({
      projectId: "project-test",
      artifactRelativePath: "artifacts/project-test/job-test/vector.svg",
      format: "ai",
      confirmExport: true,
    }));
    expect(await screen.findByText(/customer\.ai.*4 KB/)).toBeInTheDocument();
    expect(screen.getByText(/源产物未覆盖/)).toBeInTheDocument();
    expect(screen.getByText("customer.ai")).toBeInTheDocument();
    expect(screen.getAllByText(/保存路径未记录/).length).toBeGreaterThan(0);
  });
});
