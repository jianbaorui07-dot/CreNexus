---
name: starbridge-mcp
description: Use StarBridge Creative Software MCP from Codex. Use when the task involves configuring, running, inspecting, validating, or extending the StarBridge MCP stdio server; connecting Codex/Cursor/Claude Code to local creative software bridges; choosing safe MCP tools for Photoshop, Illustrator, ComfyUI, Blender, AutoCAD/DXF, CapCut/Jianying, or Adobe research; debugging MCP tools/list or tools/call; preparing redacted status reports; or deciding whether a request should use MCP, Computer Use, local scripts, or manual user action.
---

# StarBridge MCP

## Core Rule

Treat StarBridge as a local-first, safety-first MCP layer. Prefer structured, redacted, dry-run or read-only tools before GUI automation or real desktop writes.

Never read private assets, model folders, customer drawings, PSD/AI/DWG/AEP/PRPROJ/INDD projects, CapCut drafts, browser profiles, OAuth caches, Creative Cloud caches, generated images, rendered video, or local output folders unless the user explicitly provides a public test file and the repository contract allows it.

## Read First

Read only the files relevant to the task:

- General MCP use: `README.md`, `docs/local-mcp-setup.md`, `docs/client-compatibility.md`
- Tool inventory: `starbridge_mcp/core/tool_registry.py`, `starbridge_mcp/mcp_server.py`, `starbridge_mcp/server.py`
- Safety and publishing: `AGENTS.md`, `SECURITY.md`, `scripts/security_check.py`
- Bridge status: `examples/bridge_status.py`, `examples/*_bridge/bridge_status.json`
- Adobe research: `docs/adobe-mcp-github-research.md`, `docs/github-comparison.md`
- Computer Use routing: `docs/07-codex-computer-use.md`

For code changes to MCP tools, also use the local StarBridge code-engineering rules if present at `.codex/skills/starbridge-code-engineer/SKILL.md`. For CI or release validation, also use `.codex/skills/starbridge-preflight-skill/SKILL.md`.

## Specialized Skills

Use a narrower skill when the task focuses on one software bridge:

| User focus | Use skill |
| --- | --- |
| Photoshop, PS, PSD, layers, BatchPlay, Photoshop recipes | `.codex/skills/starbridge-photoshop-mcp/SKILL.md` |
| Illustrator, AI vector files, `.ai`, artboards, Image Trace, SVG/PDF/PNG export | `.codex/skills/starbridge-illustrator-mcp/SKILL.md` |
| CAD, AutoCAD, DXF, DWG, CAD JSON plan, engineering drawings | `.codex/skills/starbridge-cad-mcp/SKILL.md` |
| Blender, `.blend`, scene plan, 3D objects, render, viewport | `.codex/skills/starbridge-blender-mcp/SKILL.md` |
| Canvas, tldraw, realtime visual board, selected shapes, inserting generated images | `.codex/skills/starbridge-canvas-mcp/SKILL.md` |

## Quick Commands

Use Windows-safe commands in this repository:

```powershell
npm.cmd run starbridge:status
npm.cmd run starbridge:tools:safe
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.mcp_server
python examples\bridge_status.py --json --redact-paths --soft-exit
python scripts\starbridge_preflight.py --markdown
python scripts\security_check.py
npm.cmd test
```

Use slash paths when editing CI docs:

```bash
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.mcp_server
python examples/bridge_status.py --json --redact-paths --soft-exit
python scripts/starbridge_preflight.py --markdown
python scripts/security_check.py
npm test
```

## MCP Client Config

Use this stdio command for local MCP clients:

```json
{
  "mcpServers": {
    "starbridge": {
      "command": "python",
      "args": ["-m", "starbridge_mcp.mcp_server"]
    }
  }
}
```

If a client requires a working directory, configure it locally. Do not commit absolute user paths, software install paths, source image paths, export directories, account identifiers, or tokens.

## Tool Routing

Start with discovery:

1. Run `python -m starbridge_mcp.server tools --json --safe-only`.
2. Pick the narrowest safe tool.
3. Prefer dry-run or read-only calls.
4. If a real write/export is requested, require explicit confirmation and sandboxed output.

Use this routing table:

| Task | Preferred MCP area | Boundary |
| --- | --- | --- |
| Overall status | `starbridge.status`, `starbridge.tools` | Read-only, redacted |
| Evidence/job state | `starbridge.evidence_init`, `starbridge.evidence_validate`, `starbridge.job_status` | No private file reads |
| ComfyUI | `comfyui.system_probe`, `comfyui.workflow_validate`, workflow draft/build/repair tools | Probe and validate before queueing; do not expose model paths or generated images |
| AutoCAD/DXF | `cad_autocad.environment_probe`, `autocad_dxf.*` | Prefer offline DXF plan validation; real writes need sandbox and confirmation |
| Photoshop | `photoshop.session_info`, `ps.probe`, `ps.document.info`, `ps.layers.list`, recipe tools | Inspect active session only; do not open private PSD or run arbitrary scripts |
| Illustrator | `illustrator.document_info`, `illustrator.preflight` | Use redacted document summaries; no private `.ai` or Image Trace source images by default |
| Blender | `blender.environment_probe`, `blender.scene_plan` | Dry-run scene plans unless a public sandbox render path exists |
| CapCut/Jianying | `jianying_capcut.draft_probe`, `jianying_capcut.draft_structure` | Do not recurse private drafts or output draft names/material paths |
| Computer Use vs MCP | MCP first for repeatable structured checks; GUI only for visual inspection or app-state diagnosis | Convert GUI findings back into redacted MCP inputs where possible |

## Writing Or Extending Tools

Before adding or changing an MCP tool:

1. Add or update Chinese docs.
2. Add schema and risk metadata in the registry.
3. Add tests for `tools/list`, dry-run behavior, confirmation refusal, path sandboxing, sanitizer output, and safe-only visibility.
4. Keep writes behind `confirm_write=true` or `confirm_export=true`.
5. Return structured errors instead of crashing.
6. Redact paths and private identifiers.
7. Run validation commands before reporting success.

Never add tools that execute arbitrary JSX, arbitrary PowerShell, arbitrary Python, or arbitrary local file paths. Use whitelisted actions and audited parameters.

## Validation

For most MCP work, run:

```powershell
python -m unittest discover -s tests
python scripts\starbridge_preflight.py --markdown
python scripts\security_check.py
python -m starbridge_mcp.server tools --json --safe-only
npm.cmd test
```

If local software is unavailable, report it as unavailable or skipped. Do not turn unavailable desktop software into a pass.

## Response Format

When finishing a StarBridge MCP task, report:

- What changed or what was inspected.
- Which MCP/client path was used.
- Commands run and pass/fail/skipped status.
- Safety result: whether private paths, tokens, models, PSD/AI/DWG/CapCut drafts, customer assets, or generated outputs are at risk.
- What remains manual, especially login, licensing, OAuth, Adobe authorization, or GUI confirmation.
