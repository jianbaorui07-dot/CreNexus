---
name: starbridge-photoshop-mcp
description: Use StarBridge Photoshop MCP safely from Codex. Use when the user mentions Photoshop, PS, PSD, layers, document info, subject cutout, camera raw, BatchPlay validation, Photoshop recipes, Photoshop COM, UXP or node proxy, or asks Codex to inspect or extend Photoshop-related StarBridge MCP tools.
---

# StarBridge Photoshop MCP

## Core Rule

Treat Photoshop as a local authorized desktop app with private user assets. Prefer StarBridge read-only probes, document summaries, recipe plans, and validation before any GUI action or export.

Do not open private PSD files, scan source-image folders, run arbitrary JSX/BatchPlay, save/export real artwork, read Creative Cloud cache, or write outside approved sandbox output.

## Read First

Read only what is needed:

- `examples/photoshop_bridge/README.md`
- `docs/03-codex-photoshop.md`
- `docs/photoshop-codex-bridge.md`
- `starbridge_mcp/adapters/photoshop/`
- `starbridge_mcp/core/tool_registry.py`
- `tests/test_photoshop_*.py`
- `docs/adobe-mcp-github-research.md` only when comparing outside projects

If changing shared MCP behavior, also read `.codex/skills/starbridge-mcp/SKILL.md`.

## Safe Commands

```powershell
npm.cmd run photoshop:diagnose
npm.cmd run photoshop:info
python -m starbridge_mcp.server tools --json --safe-only
python examples\bridge_status.py --json --redact-paths --soft-exit
python -m unittest discover -s tests
python scripts\security_check.py
```

Use `npm.cmd`, not bare `npm`, on Windows PowerShell.

## Tool Routing

| Need | Preferred tool path | Boundary |
| --- | --- | --- |
| Check availability | `ps.probe`, `photoshop.session_info` | Read-only, no PSD open |
| Inspect active document | `ps.document.info`, `photoshop.document_info` | Active document only, no save/export |
| Inspect layers | `ps.layers.list` | Layer tree summary only |
| Validate BatchPlay | `ps.batchplay.validate` | Validate descriptors, never execute arbitrary BatchPlay |
| Plan actions | `photoshop.recipe_list`, `photoshop.recipe_plan` | Dry-run first |
| Prepare Illustrator trace source | `photoshop.recipe_run` + `prepare_vector_trace` | One authorized PNG/JPEG; copy first; write/export confirmations |
| Validate recipe | `photoshop.recipe_validate` | Check manifest and sandbox paths |
| Debug recipe | `photoshop.recipe_debug` | Return guidance only |

## Write Rules

Any real Photoshop write/export must require:

- `confirm_write=true` or `confirm_export=true`
- sandbox output under ignored output directories
- sanitized JSON result
- declared expected output files
- EvidenceManifest entry
- no absolute user path in returned text

Never add a raw "execute script" tool. Add audited recipe-level actions instead.

For `prepare_vector_trace`, keep the fixed flow: validate authorization → copy the explicit source into `examples/output/photoshop` → run only the repository JSX → save a redacted EvidenceManifest → pass only the prepared sandbox PNG to Illustrator.

## Validation

After Photoshop MCP changes, run:

```powershell
python -m unittest discover -s tests
python scripts\starbridge_preflight.py --markdown
python scripts\security_check.py
python -m starbridge_mcp.server tools --json --safe-only
npm.cmd test
```

Report local Photoshop as unavailable if it is not installed, not licensed, not open, or not reachable through COM/UXP. Do not turn that into pass.
