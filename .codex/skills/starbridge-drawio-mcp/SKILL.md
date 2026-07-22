---
name: starbridge-drawio-mcp
description: Use DiagramForge from Codex for native editable Draw.io diagrams, stable-ID incremental patches, structural validation, safe SVG/PDF export, and resumable diagram batches. Use for research frameworks, architecture diagrams, flowcharts, UML, BPMN, network diagrams, mind maps, Mermaid or CSV conversion, and Draw.io MCP integration.
---

# 图枢 DiagramForge

## Core Rule

Treat DiagramForge as the structured-diagram system and CreNexus Canvas as the freeform ideation surface. Prefer the deterministic headless compiler for native `.drawio`, editable SVG previews, stable IDs, validation, and tests. Use an external live Draw.io MCP only when the user explicitly needs a live editor session.

Never scan private folders for diagram inputs. Read only explicit text/spec content or one explicit safe-root `.drawio` path. All materialization, patching, SVG export, and PDF export require `confirm_write=true` and stay inside `sandbox/`, `output/`, or `examples/output/diagramforge/`.

## Read First

- `docs/04-codex-drawio.md`
- `examples/drawio_bridge/README.md`
- `examples/drawio_bridge/protocols/diagram_recipe.v1.schema.json`
- `starbridge_mcp/adapters/drawio/`
- `tests/test_drawio_*.py`

## Safe Commands

```powershell
npm.cmd run drawio:probe
npm.cmd run drawio:capabilities
npm.cmd run drawio:plan
npm.cmd run drawio:batch
python -m unittest tests.test_drawio_compiler tests.test_drawio_mcp
python scripts/security_check.py
```

The packaged `drawio:demo`, `drawio:validate`, and `drawio:export` commands are write/export entrypoints. Review the planned output first, then add `-- --confirm-write` only for an ignored safe output root.

## Tool Routing

| Need | Tool | Boundary |
| --- | --- | --- |
| Check local support | `drawio.probe` | Read-only; does not launch Draw.io |
| Discover typed features | `drawio.capabilities` | Static read-only metadata |
| Compile text/spec/recipe | `drawio.plan` | In-memory only |
| Create native deliverables | `drawio.create` | `confirm_write=true`; safe root only |
| Inspect structure and hashes | `drawio.inspect` | One explicit safe-root file |
| Modify one region | `drawio.patch` | Stable ID, transaction, unrelated-hash gate |
| Check quality | `drawio.validate` | XML, references, geometry, text, contrast |
| Export | `drawio.export` | SVG headless; PDF requires Draw.io Desktop |
| Plan a cross-app handoff | `drawio.handoff.plan` | Read-only, path-redacted, downstream confirmation required |
| Prepare a batch | `drawio.batch` | Plan-only, deterministic resume IDs |

## Workflow

1. Call `drawio.capabilities` and `drawio.plan`.
2. Validate the in-memory structure and confirm the intended output base.
3. Call `drawio.create` with explicit confirmation.
4. Reopen with `drawio.inspect` and run `drawio.validate`.
5. For edits, use returned stable element IDs and `drawio.patch`; never rebuild the whole document for a local change.
6. Accept the patch only when `unrelated_region_hashes_stable=true`.
7. Export SVG; use PDF only when `drawio.probe` reports Draw.io Desktop available.

## Upstream Boundary

The official `jgraph/drawio-mcp` is Apache-2.0 and `lgazo/drawio-mcp-server` is MIT at the commits recorded in the repository audit. DiagramForge is an independent typed implementation. Repositories without a license are design references only; do not copy their code.

## Acceptance

Do not claim a live editor connection from headless compilation. Report these truth states separately:

- `headless_compiler`
- `drawio_desktop_available`
- `live_mcp_adapter`
- `validated_after_reopen`
- `unrelated_region_hashes_stable`

A complete headless delivery requires a native `.drawio`, editable `.drawio.svg`, manifest, structural validation, and successful reopen validation.
