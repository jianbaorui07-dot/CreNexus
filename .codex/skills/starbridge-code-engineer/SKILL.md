# StarBridge Code Engineer Skill

## Purpose

This skill helps Codex work on the StarBridge Creative Software MCP repository with higher success on complex coding tasks.

Use this skill when the task involves:

* Python MCP server code
* Photoshop / Illustrator / ComfyUI / Blender / AutoCAD / CapCut bridge code
* Tool registry changes
* MCP schema changes
* EvidenceManifest / JobStatus
* Recipe / planner / validator / debugger architecture
* Tests and CI validation
* Security boundary review

## Core Rule

Do not start by editing code.

Always follow this sequence:

1. Understand the repository.
2. Identify existing implementation.
3. Compare reference patterns if needed.
4. Propose the smallest safe change.
5. Modify code.
6. Add or update tests.
7. Run validation commands.
8. Summarize exact files changed.

## Repository Safety Rules

Never commit:

* PSD, AI, DWG, DXF, blend, PNG, JPG, MP4, model files, fonts, brushes, private assets
* tokens, cookies, OAuth cache, API keys
* absolute user paths
* Adobe account data
* Creative Cloud cache
* generated images or real output files

Never add tools that:

* open arbitrary user PSD files
* execute arbitrary JSX
* execute arbitrary PowerShell script paths
* read arbitrary local directories
* auto-login to Adobe
* bypass license, authorization, captcha, or confirmation
* write outside examples/output or output

Write flows must default to dry_run=true.

Real write/export must require:

* confirm_write=true or confirm_export=true
* sandbox output directory
* sanitized JSON result
* evidence manifest

## Task Workflow

For each coding task:

### 1. Inspect first

Read the relevant files before editing.

Common files:

* README.md
* AGENTS.md
* SECURITY.md
* starbridge_mcp/mcp_server.py
* starbridge_mcp/server.py
* starbridge_mcp/core/tool_registry.py
* starbridge_mcp/core/evidence.py
* starbridge_mcp/core/job_status.py
* docs/CAPABILITY_MATRIX.md
* tests/test_mcp_tool_schemas.py
* tests/test_tool_registry.py

For Photoshop work, also read:

* examples/photoshop_bridge/README.md
* examples/photoshop_bridge/scripts/run_local_practice.ps1
* examples/photoshop_bridge/scripts/extract_subject_to_png.ps1
* examples/photoshop_bridge/scripts/com_probe.ps1
* docs/demo-photoshop.md
* docs/photoshop-codex-bridge.md

### 2. State the existing behavior

Before changing anything, write a short note:

* what already exists
* what is missing
* what is unsafe to add
* what the minimal implementation should be

### 3. Prefer recipe layer over raw tools

For difficult Photoshop tasks, do not expose many low-level tools first.

Prefer this architecture:

* recipe_list
* recipe_plan
* recipe_validate
* recipe_run
* recipe_debug

A recipe must contain:

* recipe_id
* goal
* allowed_inputs
* allowed_outputs
* steps
* tools
* validations
* retry_policy
* evidence_requirements
* safety_boundary

### 4. Use quality gates

Every non-trivial task should have quality gates:

* output_path_sandboxed
* no_private_path_leak
* dry_run_safe
* confirm_write_required
* evidence_manifest_valid
* expected_file_list_declared

If files exist locally, optionally check:

* file_exists
* file_size_nonzero
* png_dimensions_readable
* png_alpha_channel_present
* subject_cutout_has_transparency

### 5. Use evidence

Every real sandbox execution should create or update EvidenceManifest.

EvidenceManifest should record:

* bridge
* action
* status
* dry_run
* confirm_write
* input_summary
* output_files
* screenshots
* validation
* warnings
* safety_decision
* redacted_paths
* notes

### 6. Add tests

Every new tool requires tests.

Minimum tests:

* tool appears in MCP tools/list
* tool appears in tool registry
* dry_run=true does not start local software
* dry_run=false without confirmation is refused
* path escaping is refused
* result is sanitized
* no private path leak
* risk metadata is correct

### 7. Run validation

Run these commands after changes:

```powershell
python -m compileall .
python -m unittest discover -s tests
python scripts/security_check.py
python scripts/collect_bridge_status.py --json
python examples/bridge_status.py --json --redact-paths --soft-exit
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.mcp_server --help
```

Do not run real Photoshop in CI.

Only document manual Photoshop validation commands.

### 8. PR summary format

The final summary must include:

* What changed
* Why this design improves hard-task success
* Files changed
* Tests added
* Validation commands run
* Safety boundary
* What is still not supported
