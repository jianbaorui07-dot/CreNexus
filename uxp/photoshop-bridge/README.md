# StarBridge Photoshop UXP Bridge

This is a placeholder UXP plugin for `Codex + Photoshop local advanced bridge v1`.

## Current State

- `manifest.json` is loadable by UXP Developer Tool after local adjustment.
- `src/index.js` exposes a mock command entrypoint.
- `src/bridge-client.js` builds the reserved JSON-RPC envelope.
- No live Photoshop DOM, BatchPlay execute, or file write behavior is enabled here yet.

## Intended Chain

`Codex -> MCP Server -> Node Proxy or Local Bridge -> UXP Plugin -> Photoshop`

## What To Add Later

- typed BatchPlay wrappers
- schema validation for request and response payloads
- local bridge transport
- UXP test harness
- DOM and BatchPlay preview export path
