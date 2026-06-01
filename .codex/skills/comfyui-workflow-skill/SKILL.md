---
name: comfyui-workflow-skill
description: Work safely with StarBridge ComfyUI workflow validation, dry-run planning, workflow draft generation, and graph composition. Use when building, composing, repairing, validating, or reviewing ComfyUI API workflow JSON, ComfyUI probe output, txt2img dry-run flows, img2img/inpaint/upscale draft workflows, composed workflow graphs, or redacted ComfyUI job lifecycle summaries in this repository.
---

# ComfyUI Workflow

## Trigger

Use this skill when the task mentions ComfyUI workflow JSON, API format validation, workflow draft, workflow graph composer, workflow compose, workflow repair, txt2img planning, img2img draft, inpaint draft, upscale draft, ComfyUI probe, job lifecycle manifest, node validation, or model-safe workflow review.

## Read First

Read only the public ComfyUI files needed for the task:

- `AGENTS.md`
- `SECURITY.md`
- `docs/02-codex-comfyui.md`
- `docs/comfyui-agent-workflow-protocol.md`
- `examples/comfy_bridge/`
- `starbridge_mcp/core/tool_registry.py`
- ComfyUI-related tests under `tests/test_comfy*.py`

## Allowed Commands

```powershell
python examples\comfy_bridge\comfy_probe.py --soft-exit
python examples\comfy_bridge\validate_workflow.py --json
python examples\comfy_bridge\validate_workflow.py --workflow examples\comfy_bridge\workflows\minimal_api_workflow.json --json
python examples\comfy_bridge\validate_workflow.py --workflow examples\comfy_bridge\workflows\txt2img_draft_workflow.example.json --json
python examples\comfy_bridge\validate_workflow.py --workflow examples\comfy_bridge\workflows\txt2img_composed_workflow.example.json --json
python -m unittest tests.test_comfy_workflow_validate tests.test_comfyui_workflow_builder tests.test_comfyui_workflow_repair tests.test_comfy_txt2img
python -m unittest discover -s tests
python scripts\security_check.py
python scripts\starbridge_preflight.py --markdown
npm.cmd run comfy:probe
npm.cmd run comfy:workflow:validate
```

Only run `run_txt2img.py` when the user explicitly asks to contact a running local ComfyUI and supplies safe placeholder inputs. Treat submitted jobs as local-only and do not commit generated outputs.

Do not run real `img2img`, `inpaint`, or `upscale`; draft workflows are JSON scaffolds only until reviewed public workflow templates and explicit run gates exist.

## Forbidden Access

Do not read ComfyUI model directories, checkpoint files, LoRA, VAE, ControlNet, embeddings, generated images, output galleries, private prompts, or user asset folders.

Do not discover real model names by scanning disks. Do not write generated images or manifests into tracked paths. Do not submit jobs in CI.

## Workflow

1. Validate JSON parseability first; distinguish UI workflow JSON from API workflow JSON.
2. Check node id, `class_type`, `inputs`, link references, required text/output nodes, detected model fields, and suspicious fields.
3. Return structured validation details: `valid`, `errors`, `warnings`, `node_count`, `detected_models`, and `missing_or_suspicious_fields`.
4. Use `workflow_build_plan` for planning, `comfy.workflow_draft` for API-like draft JSON, and `comfy.workflow_compose` when the user asks for modular graph composition.
5. Composer modules must stay placeholder-only: checkpoint loader, positive prompt encode, negative prompt encode, empty latent, load image, VAE encode, KSampler, VAE decode, save image, upscale, and inpaint mask.
6. Drafts and composed graphs must include `StarBridgeDraftMetadata`, `draft=true` or `safe_placeholder=true`, and `production_ready=false`.
7. For `txt2img`, `img2img`, `inpaint`, and `upscale`, generate placeholder-only graph nodes and validate them immediately.
8. Keep checkpoint, source image, mask image, model, LoRA, VAE, ControlNet, upscale model, and output fields as placeholders unless the user explicitly confirms a local run in a later task.
9. Redact prompt text in lifecycle summaries when it may reveal private project content; prefer hashes and basenames.
10. Run targeted ComfyUI tests, then preflight and security checks.

## Template Registry

Use `workflow_template_registry` when the task asks for reviewed template selection or template-driven composition.

- Registry file: `examples/comfy_bridge/templates/workflow_template_registry.json`.
- Supported template ids: `txt2img_basic_v1`, `img2img_basic_v1`, `inpaint_basic_v1`, `upscale_basic_v1`, `creative_poster_complex_v1`.
- Public functions: `list_workflow_templates()`, `get_workflow_template(template_id)`, `validate_workflow_template(template)`, `compose_from_template(template_id, arguments)`.
- MCP tools: `comfy.workflow_template_list`, `comfy.workflow_template_get`, `comfy.workflow_from_template`; all must remain `safe_read_only`.
- Template lint must check unique `template_id`, present `version`, recognized composer modules, complete `required_inputs`, validation status in `draft_validated | composed_validated | needs_review`, and forbidden private patterns.
- Template composition must call the safe graph composer only. It must not accept local image paths, scan model/output directories, contact ComfyUI, submit `/prompt`, or read generated files.

## Output Format

Return:

- `Workflow status`: valid, repaired, invalid, or skipped.
- `Files read`: public repo files only.
- `Commands run`: exact commands and outcomes.
- `Graph summary`: task type, node count, validation status, and whether queue submission is disabled.
- `Safety summary`: whether models, generated images, private prompts, source images, masks, and output paths were avoided.
- `Next action`: dry-run repair, draft review, local txt2img submit with confirmation, or no action.
