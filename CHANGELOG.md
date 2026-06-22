# Changelog

## Unreleased / Optimizations

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
