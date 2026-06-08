# Codex + Photoshop Local MCP v1

This document describes the local-only Photoshop bridge upgrade in this repository.

## Scope

`Codex + Photoshop local advanced bridge v1` adds a safe Photoshop adapter under `starbridge_mcp/adapters/photoshop`, a placeholder UXP plugin under `uxp/photoshop-bridge`, evidence-first MCP tools, and mock-first tests. It does not modify real PSD files by default and does not enable destructive Photoshop operations.

## Architecture

The intended chain is:

1. Codex calls the local MCP stdio server.
2. `starbridge_mcp` routes Photoshop requests into the adapter layer.
3. The adapter uses one of these bridge kinds:
   - `mock`: local sandbox and test fallback
   - `com`: Windows COM probe and read-only fallback
   - `node_proxy`: reserved for a local bridge service
   - `uxp`: reserved for the Photoshop plugin channel
4. The future steady-state write path is `Codex -> MCP Server -> Node Proxy or Local Bridge -> UXP Plugin -> Photoshop`.

In v1, the advanced chain is designed and documented, while live write operations remain disabled.

## Risk Levels

- `level_0_read_only`: probe, inspect, validate
- `level_1_sandbox_write`: preview or evidence files inside `sandbox/` or `output/`
- `level_2_confirmed_write`: explicit confirmed write tools, disabled in v1
- `level_3_destructive_batch`: destructive or batch execution, disabled in v1

Each Photoshop v1 tool schema carries:

- `risk_level`
- `requires_confirmation`
- `dry_run`
- `writes_files`
- `touches_user_psd`
- `bridge_kind`
- `output_dir`

## Enabled Tools

The example Codex config only enables these tools:

- `ps.probe`
- `ps.document.info`
- `ps.layers.list`
- `ps.preview.export`
- `ps.evidence.capture`
- `ps.batchplay.validate`

These stay disabled by default in v1:

- `ps.batchplay.execute_confirmed`
- `ps.script.execute_confirmed`
- `ps.history.undo`
- `ps.mask.refine`
- `ps.smartobject.place`
- `ps.adjustment.apply`
- `ps.text.edit`
- `ps.export.psd_copy`

## JSON-RPC Envelope

The local bridge design reserves this message shape for the future Node Proxy and UXP path:

```json
{
  "jsonrpc": "2.0",
  "id": "job-optional",
  "method": "ps.preview.export",
  "params": {
    "job_id": "preview-001",
    "risk_level": "level_1_sandbox_write",
    "dry_run": true,
    "requires_confirmation": true,
    "bridge_kind": "uxp",
    "evidence_path": "sandbox/evidence/ps_preview_export_preview-001_manifest.json"
  }
}
```

Reserved top-level payload fields:

- `method`
- `params`
- `job_id`
- `risk_level`
- `dry_run`
- `requires_confirmation`
- `evidence_path`

## EvidenceManifest

`ps.preview.export`, `ps.evidence.capture`, and `ps.batchplay.validate` all return an `evidence_manifest` object. When `dry_run=false`, the manifest is also written to `sandbox/evidence/` or `output/evidence/`.

Manifest fields:

- `job_id`
- `created_at`
- `adapter_name`
- `adapter_version`
- `tool_name`
- `risk_level`
- `requires_confirmation`
- `dry_run`
- `input_summary`
- `output_files`
- `preview_files`
- `source_files`
- `photoshop_available`
- `bridge_kind`
- `status`
- `warnings`
- `errors`

## Local Run

Run tests:

```powershell
python -m pytest tests\test_photoshop_adapter_v1.py tests\test_mcp_tools_adobe.py tests\test_mcp_stdio_server.py tests\test_tool_registry.py
```

Start the MCP server:

```powershell
python -m starbridge_mcp.mcp_server
```

Manual stdio probe:

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual-test","version":"1"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ps.probe","arguments":{"bridge_kind":"mock"}}}
'@ | python -m starbridge_mcp.mcp_server
```

## Codex Config

Use the example file at `.codex/config.example.toml`. Do not edit the real `~/.codex/config.toml` from this repository.

Recommended workflow:

1. Copy the example into your local Codex config area.
2. Keep only the safe Photoshop tools enabled.
3. Leave `dry_run` enabled by default.
4. Point all preview and evidence outputs at `sandbox/` or `output/`.

## What Is Real in v1

Real now:

- MCP tool registration
- mock bridge execution
- COM-based probe fallback
- active-document summary via COM when Photoshop is already open
- layer list fallback via COM when available
- EvidenceManifest generation
- BatchPlay static validation

Safe placeholders for later:

- live UXP plugin control
- typed BatchPlay execution
- arbitrary Photoshop script execution
- history mutation
- PSD copy export
- mask, text, layout, smart-object, and adjustment writes

## Upgrade Path

To move beyond v1:

1. Add a local Node Proxy or HTTP bridge that forwards only typed JSON-RPC calls.
2. Move preview export from placeholder files to real UXP DOM or BatchPlay rendering.
3. Add typed BatchPlay wrappers plus schema validation on both sides.
4. Add UXP-side test fixtures and plugin smoke tests.
5. Keep evidence-first iteration so Codex reviews previews and layer trees before any confirmed write path is enabled.
