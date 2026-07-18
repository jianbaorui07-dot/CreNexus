import { DesktopTransport, type InvokeLike } from "./desktopTransport";
import { HttpTransport } from "./httpTransport";
import type { StarBridgeTransport } from "./transport";

interface RuntimeScope {
  __TAURI_INTERNALS__?: unknown;
}

export function isTauriRuntime(scope: RuntimeScope = globalThis as RuntimeScope): boolean {
  return Boolean(scope.__TAURI_INTERNALS__);
}

export function createTransport(options?: {
  desktop?: boolean;
  invoke?: InvokeLike;
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}): StarBridgeTransport {
  const desktop = options?.desktop ?? isTauriRuntime();
  if (desktop) {
    return new DesktopTransport(options?.invoke);
  }
  return new HttpTransport(options?.baseUrl, options?.fetchImpl);
}
