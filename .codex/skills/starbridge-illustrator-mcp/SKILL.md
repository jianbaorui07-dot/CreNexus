---
name: starbridge-illustrator-mcp
description: Use StarBridge Illustrator MCP safely from Codex. Use when the user mentions Adobe Illustrator, AI vector files, .ai, artboards, vector trace, Image Trace, SVG/PDF/PNG export, Illustrator COM, JSX, preflight, document_info, or asks Codex to inspect or extend Illustrator-related StarBridge MCP tools.
---

# StarBridge Illustrator MCP

## Core Rule

In this repository, `AI` usually means Adobe Illustrator `.ai` vector files, not artificial intelligence. Treat Illustrator documents, source images, linked assets, fonts, and exports as private unless the user provides a public test asset.

Prefer read-only environment checks, redacted document summaries, preflight, and sandbox demo plans before GUI actions or exports.

For ordinary PNG/JPEG-to-vector or “convert this image to AI” requests, enforce two stages. First use `exact_pixel_vector.py` as the pixel-level print/exact reconstruction baseline: rebuild the original RGBA grid as grouped rectangle compound paths and verify the raster-free SVG. Second, only when the customer needs a more editable drawn vector, use Artisan Vector or a customer-selected Smart/Lightweight mode on that verified baseline. Do not use Illustrator Image Trace in customer delivery. If exact reconstruction exceeds its safety limits, stop and ask the user to reduce dimensions or change the delivery goal; never silently fall back to tracing.

If the Smart/Artisan result is fragmented, cracked, visibly inaccurate, or over the user's difference limit, switch to `$starbridge-smart-vector-refinement`. Score the actual final SVG render, not the internal processed preview, before any Illustrator handoff.

## Read First

Read only what is needed:

- `docs/05-codex-illustrator.md`
- `.codex/skills/starbridge-smart-vector-refinement/SKILL.md` when repairing a weak curve result
- `docs/color-faithful-vectorization.md`
- `examples/illustrator_bridge/`
- `examples/illustrator_bridge/scripts/preflight_plan.py`
- `starbridge_mcp/bridges/illustrator_preflight.py`
- `starbridge_mcp/core/tool_registry.py`
- `tests/test_mcp_tools_adobe.py`
- `docs/adobe-mcp-github-research.md` only when comparing outside projects

If changing shared MCP behavior, also read `.codex/skills/starbridge-mcp/SKILL.md`.

## Safe Commands

```powershell
npm.cmd run illustrator:preflight:plan
npm.cmd run illustrator:info
npm.cmd run illustrator:vectorize:offline -- --input "<explicit-image.png>" --reference-id reference
python examples\illustrator_bridge\scripts\preflight_plan.py --json
python -m unittest tests.test_color_vectorization
python -m unittest tests.test_color_vector_repair
powershell -ExecutionPolicy Bypass -File examples\illustrator_bridge\scripts\color_vectorize.ps1
python -m starbridge_mcp.server tools --json --safe-only
python examples\bridge_status.py --json --redact-paths --soft-exit
python scripts\security_check.py
```

Do not hardcode local Illustrator install paths in docs, tests, or examples.

## Tool Routing

| Need | Preferred tool path | Boundary |
| --- | --- | --- |
| Check availability | `illustrator.document_info` or bridge status probe | Read-only, no private `.ai` open |
| Review document risk | `illustrator.preflight` | Use redacted summaries |
| Inspect artboards/layers | future `document_info` expansion | Active session summary only |
| Image→SVG / AI delivery | `exact_pixel_vector.py` then Illustrator Save As | Default and required route; explicit single image, sandbox SVG, no Image Trace, no embedded raster |
| Legacy trace plan | `illustrator.color_vectorize_plan` | Compatibility/research only; do not select for ordinary image-to-vector delivery |
| Validate trace quality | `illustrator.color_vectorize_validate` | Sanitized metrics only; no reference/preview file read |
| Compare trace preview | `illustrator.color_vectorize_compare` | One authorized PNG/JPEG + one sandbox PNG; no path, pixel, or metadata returned |
| Plan bounded repair | `illustrator.color_vectorize_repair_plan` | Sanitized findings to allowlisted parameters plus dry-run execute/compare templates; at most 3 rounds; no script or desktop execution |
| Execute color trace | `illustrator.color_vectorize_execute` | Default dry-run; fixed JSX, explicit single image, dual confirmation, sandbox only |
| Export | color trace executor or demo export | Confirmed sandbox export only |

## Forbidden Work

Do not add tools that:

- open arbitrary `.ai` files
- run arbitrary JSX
- read linked asset paths
- scan font folders or Creative Cloud cache
- use Image Trace on private source images
- export SVG/PDF/PNG to user directories
- use Illustrator Image Trace for ordinary image-to-vector delivery
- fall back to Image Trace when exact pixel reconstruction exceeds a limit

Use whitelisted actions with explicit parameters and sanitized output.

## Validation

After Illustrator MCP changes, run:

```powershell
python -m unittest discover -s tests
python scripts\starbridge_preflight.py --markdown
python scripts\security_check.py
python -m starbridge_mcp.server tools --json --safe-only
npm.cmd test
```

Report Illustrator desktop validation separately from CI. CI must not require Illustrator, COM, GUI state, fonts, source images, or private `.ai` files.
