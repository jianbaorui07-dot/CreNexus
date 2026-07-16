# Changelog

## Unreleased / Optimizations

### 2026-07-16 — Artisan Vector iteration 1

* Added a premium `artisan` mode without replacing Smart, Lightweight, Exact, or legacy entry points.
* Added protected-corner anchor classification and mixed absolute `M/L/C/Z` paths with cubic Bézier control handles.
* Added adaptive contour fitting that restores anchors when the measured contour error exceeds the quality tolerance.
* Added separate anchor, control-point, curve-segment, line-segment, anchor-reduction, and contour-error evidence to the verifier and reports.
* Added Artisan mode to the CLI and PySide6 desktop mode cards, with an offscreen end-to-end test.

### 2026-07-16 — Three-mode vector engine and desktop prototype

* Added one verified vectorization core with Smart Vector as the default, Lightweight Vector for low-complexity editing, and Exact Reconstruction for RGBA pixel proof.
* Added deterministic local SVG/PNG/report outputs, path/point/file-size limits, vertically merged exact rectangles, and exact pixel validation.
* Added a PySide6 desktop prototype with image drag-and-drop, three mode cards, parameter controls, background conversion, side-by-side previews, result metrics, and local output-folder access.
* Preserved the previous exact and legacy quantized commands as compatibility entry points; Illustrator remains an optional explicit desktop handoff.

### 2026-07-15 — Exact pixel-vector reconstruction becomes primary

* Added `exact_pixel_vector.py`, which rebuilds one explicit PNG/JPEG RGBA grid as grouped rectangle compound paths, verifies a raster-free SVG, and hands it to Illustrator for Save As AI without Image Trace.
* Switched `illustrator:vectorize:offline` to the exact route. The previous OpenCV quantized workflow remains available as `illustrator:vectorize:legacy-quantized` for compatibility and research.
* Added deterministic RGBA, transparency, privacy, sandbox, complexity-limit, package-command, and SVG verifier coverage.
* Repositioned README and Chinese Illustrator documentation around exact image-to-AI delivery while retaining Adobe protocols, ComfyUI, CAD/AutoCAD, Blender, CapCut/Jianying, MCP stdio, UXP, and local proxy capabilities.
* Documented a sanitized local write with 742,922 rectangle subpaths and a successfully saved desktop AI; no source image, local path, SVG, AI, or report is committed.

### 2026-06-27 — MCP Prompts (complete the 3 primitives)

* **MCP Prompts capability (new).** Added the third MCP primitive alongside tools
  and resources. The stdio server now serves `prompts/list` and `prompts/get`,
  declares the `prompts` capability in `initialize`, and exposes five reusable,
  parameterized safe-by-default prompt templates: `bridge_status_check`,
  `comfyui_safe_workflow`, `cad_dxf_from_spec`, `photoshop_recipe_run`, and
  `safe_write_protocol`. Each template bakes in the validate-first / dry-run /
  explicit-confirmation / sandbox-only protocol. Implemented in
  `starbridge_mcp/core/prompts.py`, covered by `tests/test_mcp_prompts.py`.
* StarBridge now exposes the full MCP surface: Tools (what the client can do),
  Resources (what the client should know), and Prompts (how to do it safely).

### 2026-06-27 — MCP Resources, regression fix, lint gate

* **MCP Resources capability (new).** Following the comparable-project pattern
  "resources describe what the client should know, tools describe what the client
  can do", the stdio server now exposes read-only, sanitized resources via
  `resources/list` and `resources/read`: `starbridge://safety-policy`,
  `starbridge://capabilities`, `starbridge://safe-roots`, and
  `starbridge://bridges`. Implemented in `starbridge_mcp/core/resources.py`.
* `initialize` now declares the `resources` capability and returns an
  `instructions` field that teaches clients the safe-by-default protocol
  (dry-run defaults, confirmation flags, sandbox output boundaries) before any
  tool call. Covered by `tests/test_mcp_resources.py`.
* **Regression fix:** removed a duplicated block in `starbridge_mcp/mcp_server.py`
  that defined `_recipe_output_dir` and the five `photoshop.recipe_*` handlers a
  second time, silently overriding the richer recipe implementations (the
  "fleshed out 5 core recipes" work) with stub versions. The detailed recipe
  plans, steps, tool mappings, and quality gates are now actually served.
* Removed a duplicate `from starbridge_mcp.bridges import autocad_dxf` import.
* **Lint gate:** added a dedicated `lint` job to `.github/workflows/ci.yml`
  running `ruff check` and `ruff format --check`, and brought the whole repo to a
  clean ruff state (import sorting, an unused import, a `SIM103` simplification,
  and format drift across tests). Previously ruff was only wired into
  `pre-commit`, not CI, despite the note below.

### Repo & Packaging
* Added root `LICENSE` (MIT) to match pyproject declaration.
* Added `.github/FUNDING.yml` for sponsorship visibility.
* Enhanced `pyproject.toml`: added classifiers, project.urls (GitHub repo, issues, docs), expanded description and keywords for better discoverability.
* Improved CI workflow: added Windows runner (project is Windows-first), pip/npm caching, modern actions, broader Python matrix.
* Centralized `BRIDGE_PROFILES`, `BRIDGE_NAME_MAP`, `BRIDGE_ALIASES` in `core/tool_registry.py` as single source of truth (previously duplicated in server.py). Updated imports and test. This eliminates metadata duplication while keeping compat.
* Added long-term code quality tooling: ruff (lint + formatter) to dev dependencies and pyproject.toml config. Integrated into CI (both ubuntu and windows jobs) with `ruff check` and `ruff format --check`. Auto-fixed 100+ issues (imports, formatting, outdated guards, etc.). Added npm scripts for lint/format. Removed outdated Python version checks. All checks now enforced for sustainable quality.

### Documentation & Structure
* Polished README: added prominent Getting Started / Quick Install section, License badges and section, better onboarding.
* Central tool capability metadata in `core/tool_registry.py` and bridge profiles in `server.py` — added cross-reference notes to reduce drift.

### Photoshop Enhancements (C + Recipes follow-up)
* Added `ps.get_preview` (base64/path for vision models) and `ps.get_state` (lightweight snapshot) — read-only, cheap, safe for iterative agent use.
* Fleshed out 5 core recipes with concrete steps/tools: remove_background, enhance_portrait, frequency_separation, color_grade, prepare_for_web. Recipes return plans with safety gates.
* Enhanced Action Plan mode in recipe_plan (action_plan=true) for plan-then-execute with repair hints.
* Updated schemas, tools, bridge adapter, mcp handlers, tool_registry, and docs for new preview/state + recipes.
* More recipe details: steps now map to existing ps.* tools (selection, layers, batchplay, preview, evidence).

### Release Process
* Improved install-and-publish.md with clearer PyPI/npm/MCP registry paths, smoke test commands, and productization checklist.
* Added .github/workflows/release.yml for automated GitHub releases on v* tags (with build artifacts, notes).
* Enhanced get_preview to leverage preview_export for better plans; get_state now includes more dynamic info from probes/layers.
* More recipe details: concrete step-by-step for remove_background and enhance_portrait with tool mappings, execution notes, and safety.
* Updated CHANGELOG with unreleased long-term optimizations.
* Added pre-commit config (ruff, mypy) and CI enforcement for consistent releases.
* VERSION and pyproject kept in sync; recommend `scripts/starbridge_preflight.py` + security check before publish.

## [0.1.0] - 2026-05-29

### Added

* StarBridge MCP stdio server
* Safe local bridge status and probes
* ComfyUI workflow validation
* AutoCAD DXF dry-run bridge
* Photoshop sandbox demo bridge
* Illustrator sandbox demo bridge
* Adobe demo docs, smoke test, and output safety rules

### Security

* Local-first design
* No customer assets committed
* Demo outputs ignored by Git
* Guarded write/export operations require explicit confirmation

### Known limitations

* Adobe demos require local authorized desktop apps
* Photoshop and Illustrator automation remain experimental
* Image Trace is not implemented yet
* ComfyUI txt2img closed loop is still next priority if not already merged
