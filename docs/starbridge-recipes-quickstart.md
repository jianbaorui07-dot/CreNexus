# StarBridge Recipe Quick Start

This page is the shortest safe path for using StarBridge after the cross-project
research updates. It keeps the public repo in planning, validation, and evidence
mode until a bridge-specific tool receives explicit confirmation.

## Safe Call Order

1. Read `starbridge://safety-policy`.
2. Read `starbridge://capabilities` and use `manifest_version=starbridge.capabilities.v2`.
3. Call `starbridge.recipe_list` to choose a reviewed workflow.
4. Call `starbridge.recipe_plan` to inspect the dry-run action plan and quality gates.
5. For ComfyUI, call `comfyui.queue_snapshot` in plan mode; opt into a live loopback read
   before considering a confirmed submit.
6. Call `starbridge.operation_context` with a caller-supplied safe `before_state`.
7. Call `starbridge.recipe_evidence` to preview the standard `EvidenceManifest`.
8. Only then call a bridge-specific write/export/run tool, and only with the required
   confirmation flag and sandbox output root.
9. After each major action or failure, call `starbridge.operation_context` again with
   the safe `after_state` and chain the returned `context_id`.

## MCP Calls

Start the stdio server from the repo root:

```powershell
npm.cmd run starbridge:mcp
```

List reviewed cross-bridge recipes:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "starbridge.recipe_list",
    "arguments": {}
  }
}
```

Plan one recipe without launching local software:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "starbridge.recipe_plan",
    "arguments": {
      "recipe_id": "comfyui_txt2img_lifecycle"
    }
  }
}
```

Preview its evidence contract:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "starbridge.recipe_evidence",
    "arguments": {
      "recipe_id": "comfyui_txt2img_lifecycle"
    }
  }
}
```

## Current Reviewed Recipes

| Recipe | Bridge | Use when |
| --- | --- | --- |
| `photoshop_preview_export` | Photoshop | You need a safe preview/export sequence before any PSD write path. |
| `comfyui_txt2img_lifecycle` | ComfyUI | You need a generation workflow lifecycle without exposing models or outputs. |
| `cad_dxf_from_spec` | AutoCAD/DXF | You need to turn a structured CAD spec into a validated DXF plan. |
| `illustrator_trace_preflight` | Illustrator | You need preflight gates before any Image Trace or export workflow. |
| `blender_scene_evidence` | Blender | You need a render/reconstruction plan with evidence and error gates first. |

## What To Check Before Confirming Writes

- `bridge_overview.<bridge>.guarded_tools` names the tools that need confirmation.
- `planner_hints.safe_discovery_sequence` gives the safe discovery order.
- `quality_gates` must pass or be intentionally waived before execution.
- `operation_context` accepts only whitelisted metrics and logical evidence IDs; never
  put document names, layer names, prompts, model names, or paths into a state snapshot.
- `queue_snapshot` must return a live `idle` decision before it can satisfy the ComfyUI
  backpressure gate; it never replaces explicit submission confirmation.
- `asset_manifest` must contain only sanitized, repo-relative, or generated asset
  summaries. Do not include customer paths, model paths, account data, or private
  source files.
- Real writes stay inside `starbridge://safe-roots`.

## Bridge-Specific Next Steps

| Bridge | Safe first command |
| --- | --- |
| ComfyUI | `npm.cmd run comfy:lifecycle:template` |
| Blender | `npm.cmd run blender:reference:plan` |
| AutoCAD/DXF | `npm.cmd run cad:dxf:dry-run` |
| Photoshop | `npm.cmd run photoshop:demo:plan` |
| Illustrator | `npm.cmd run illustrator:preflight:plan` |
| CapCut/Jianying | `npm.cmd run capcut:draft:structure` |

