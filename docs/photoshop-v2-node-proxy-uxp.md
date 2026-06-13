# Photoshop v2 Node Proxy + UXP Bridge

This document describes the v2 Photoshop control path for StarBridge.

```text
Codex / MCP client
  -> StarBridge MCP tools
  -> local Node Proxy
  -> Photoshop UXP plugin
  -> Photoshop DOM / typed batchPlay / executeAsModal
```

The v2 path is still experimental. It is designed to make Photoshop control observable and guarded, not to run arbitrary scripts against private PSD files.

## What v2 Adds

| Area | Capability |
| --- | --- |
| Node Proxy | Local HTTP JSON-RPC endpoint, UXP WebSocket endpoint, `/health`, `/bridge/status`, `/events` |
| UXP plugin | Registers Photoshop host info, reconnects after proxy restarts, exposes typed handlers |
| Read-only tools | `ps.probe`, `ps.document.info`, `ps.layers.list` |
| Guarded write path | `ps.preview.export`, `ps.batchplay.execute_confirmed` behind confirmation and sandbox policy |
| Evidence | Returns `EvidenceManifest` fields for bridge kind, UXP status, host info, layer snapshot, validation result |

## Start the Node Proxy

```powershell
npm.cmd run photoshop:node-proxy
```

Default local endpoints:

```text
http://127.0.0.1:8971/health
http://127.0.0.1:8971/bridge/status
http://127.0.0.1:8971/events
ws://127.0.0.1:8971/uxp
```

Use `STARBRIDGE_PHOTOSHOP_PROXY_PORT` if you need another local port.

## Load the UXP Plugin

Open Adobe UXP Developer Tool and load:

```text
uxp/photoshop-bridge
```

Then start the plugin in Photoshop. On connect, the plugin registers with the Node Proxy and sends basic host metadata:

- app name
- Photoshop version
- connection timestamp

If the Node Proxy restarts, the UXP client attempts to reconnect automatically.

## Run the MCP Server

```powershell
python -m starbridge_mcp.mcp_server
```

Then call:

- `ps.probe`
- `ps.document.info`
- `ps.layers.list`
- `ps.batchplay.validate`

`ps.probe` should show:

- `node_proxy_running`
- `uxp_client_connected`
- `photoshop_host_seen`
- `photoshop_host`
- COM fallback state

## Safe BatchPlay Contract

All write-like actions must pass through the typed allowlist and explicit confirmation.

Allowed descriptor families are intentionally narrow:

- `get`
- `duplicate`
- `make`
- `set`
- `move`

Denied descriptor families include destructive or arbitrary execution paths:

- `delete`
- merge / flatten / rasterize
- arbitrary JavaScript
- raw nested `batchPlay`
- overwrite-style saves

Confirmed execution requires:

- `requires_confirmation=true`
- `confirm_write=true`
- sandbox output only
- a prior `ps.batchplay.validate` result with no blocked descriptors

## Local Smoke Checks

These checks do not require Photoshop to be installed:

```powershell
python -m unittest tests.test_photoshop_node_proxy
python -m unittest tests.test_photoshop_adapter_v1
```

With local Photoshop and the UXP plugin running:

```powershell
npm.cmd run photoshop:node-proxy
python -m starbridge_mcp.mcp_server
```

Then call `ps.probe` from an MCP client and confirm the bridge reports `node_proxy_uxp`.

## Current Limits

- UXP preview export is routed but bitmap encoding still depends on local Photoshop host support.
- The bridge does not open private PSD files by itself.
- Arbitrary script execution remains disabled.
- Real outputs must stay in sandbox or ignored output directories.
- Account, Creative Cloud, licensed asset, and private project data must not be committed.
