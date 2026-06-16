# StarBridge Photoshop UXP Bridge

This is the local UXP plugin side of the StarBridge Photoshop bridge.

## Current State

- `src/index.js` exposes JSON-RPC handlers for `starbridge.ping`, `ps.document.info`, `ps.layers.list`, `ps.preview.export`, `ps.camera_raw.tune`, `ps.batchplay.validate.local`, and `ps.batchplay.execute_confirmed`.
- `src/bridge-client.js` connects to the local Node Proxy WebSocket client endpoint.
- `src/batchplay-schema.js` and `src/batchplay-runner.js` enforce a typed allowlist and wrap write-like execution in `executeAsModal`.
- Real writes still require explicit confirmation and must stay on sandbox copies.
- Camera Raw tuning is experimental. V1 supports parameter planning and safe validation. Real Photoshop apply requires a verified local BatchPlay descriptor and explicit confirmation.

## Intended Chain

`Codex -> MCP Server -> Node Proxy -> UXP Plugin -> Photoshop DOM / batchPlay / executeAsModal`

## What To Add Later

- Host-specific preview bitmap encoding if the local Photoshop build exposes a reliable export path from UXP
- Additional typed descriptors beyond the current allowlist
