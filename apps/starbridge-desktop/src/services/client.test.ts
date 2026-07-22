import { describe, expect, it } from "vitest";

import type { CreNexusTransport } from "./transport";
import { CreNexusApiClient, UserFacingError } from "./client";

function transportReturning(status: number, body: Record<string, unknown>): CreNexusTransport {
  return {
    kind: "desktop",
    request: async () => ({ status, body }),
    getRuntimeStatus: async () => ({
      state: "connected",
      message: "connected",
      recoveryAttempts: 0,
    }),
    restartBackend: async () => ({
      state: "connected",
      message: "connected",
      recoveryAttempts: 1,
    }),
    openLogsDirectory: async () => "logs",
    installCodexConnector: async () => ({ status: 200, body: { ok: true } }),
    resetCodexConnection: async () => ({ status: 200, body: { ok: true } }),
    openCodexPairing: async () => undefined,
    openCodexTask: async () => undefined,
    openGitHubProject: async () => undefined,
    pairCreativeApplication: async () => ({ status: 200, body: { ok: true } }),
    reconnectCreativeApplication: async () => ({ status: 200, body: { ok: true } }),
    disconnectCreativeApplication: async () => ({ status: 200, body: { ok: true } }),
    getVersion: async () => ({ desktop: "test" }),
    getUpdateStatus: async () => ({
      configured: false,
      source: "GitHub Releases",
      currentVersion: "test",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: false,
    }),
    checkForUpdate: async () => ({
      configured: false,
      source: "GitHub Releases",
      currentVersion: "test",
      available: false,
      signatureRequired: true,
      automaticChecksSupported: false,
    }),
    installUpdate: async () => undefined,
    getLicenseStatus: async () => ({
      state: "community",
      edition: "community",
      message: "community",
      deviceLimit: 0,
      features: [],
      commercialVerifierConfigured: false,
    }),
    createLicenseRequest: async () => ({
      requestId: "request-test",
      fileName: "request.json",
      location: "license/requests",
      folderOpened: false,
    }),
    importLicenseFile: async () => ({
      state: "active",
      edition: "pro",
      message: "active",
      deviceLimit: 1,
      features: [],
      commercialVerifierConfigured: true,
    }),
    importProjectAsset: async () => null,
    chooseVectorInput: async () => null,
    startVectorization: async () => ({ status: 202, body: { ok: false } }),
    getVectorizationJob: async () => ({ status: 404, body: { ok: false } }),
    getVectorizationHistory: async () => ({
      status: 200,
      body: { ok: true, data: { eventCount: 0, events: [] } },
    }),
    openVectorOutput: async () => ({ status: 200, body: { ok: true, data: { opened: true } } }),
    openProjectArtifacts: async () => "artifacts",
    exportAdobeFile: async () => null,
    listAdobeExports: async () => [],
  } as CreNexusTransport;
}

describe("API error translation", () => {
  it.each([
    [401, "authentication_required", "重新授权"],
    [403, "authentication_failed", "会话已失效"],
  ])("translates HTTP %s without hiding technical details", async (status, code, phrase) => {
    const client = new CreNexusApiClient(
      transportReturning(status, {
        ok: false,
        error: { code, message: "raw backend message" },
      }),
    );

    await expect(client.getBootstrap()).rejects.toMatchObject({
      message: expect.stringContaining(phrase),
      technicalDetails: `HTTP ${status}; ${code}`,
      status,
    } satisfies Partial<UserFacingError>);
  });
});
