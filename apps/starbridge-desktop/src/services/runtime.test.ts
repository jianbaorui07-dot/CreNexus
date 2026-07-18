import { describe, expect, it, vi } from "vitest";

import { createTransport, isTauriRuntime } from "./runtime";

describe("transport selection", () => {
  it("detects the Tauri runtime marker", () => {
    expect(isTauriRuntime({ __TAURI_INTERNALS__: {} })).toBe(true);
    expect(isTauriRuntime({})).toBe(false);
  });

  it("uses DesktopTransport in the desktop runtime", () => {
    const invoke = vi.fn();
    const transport = createTransport({ desktop: true, invoke });

    expect(transport.kind).toBe("desktop");
  });

  it("uses HttpTransport for browser development", () => {
    const transport = createTransport({
      desktop: false,
      fetchImpl: vi.fn(),
      baseUrl: "http://127.0.0.1:8765",
    });

    expect(transport.kind).toBe("http");
  });
});
