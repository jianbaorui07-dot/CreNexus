from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any

from examples.comfy_bridge.validate_workflow import validate_workflow_payload
from starbridge_mcp.core.job_status import JobStatus
from starbridge_mcp.core.queue_snapshot import _NoRedirectHandler, _validate_loopback_url
from starbridge_mcp.core.security import sanitize

BRIDGE_ID = "comfyui"
DEFAULT_BASE_URL = os.environ.get("STARBRIDGE_COMFYUI_URL") or os.environ.get(
    "COMFY_BASE_URL", "http://127.0.0.1:8188"
)
DEFAULT_CHECKPOINT = os.environ.get("STARBRIDGE_COMFYUI_CHECKPOINT", "__checkpoint_name_required__")
PLACEHOLDER_CHECKPOINT = "__checkpoint_placeholder__"
PLACEHOLDER_UPSCALE_MODEL = "__upscale_model_placeholder__"
PLACEHOLDER_SOURCE_IMAGE = "__source_image_placeholder__"
PLACEHOLDER_MASK_IMAGE = "__mask_image_placeholder__"
DEFAULT_NEGATIVE_PROMPT = "low quality, blurry, distorted, bad anatomy, watermark, text"
SUPPORTED_WORKFLOW_TYPES = {"txt2img", "img2img", "inpaint", "upscale"}
BUILDABLE_WORKFLOW_TYPES = {"txt2img"}
MAX_COMFY_RESPONSE_BYTES = 1_048_576
PROMPT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
ASSET_ID_PATTERN = re.compile(r"asset_[0-9a-f]{16}\Z")
PROVENANCE_TTL_SECONDS = 24 * 60 * 60
MAX_PROVENANCE_RECORDS = 128
DEFAULT_ASSET_LIST_LIMIT = 20
MAX_ASSET_LIST_LIMIT = 100
REGENERATION_OVERRIDE_FIELDS = (
    "cfg",
    "height",
    "negative_prompt",
    "prompt",
    "sampler",
    "scheduler",
    "seed",
    "steps",
    "width",
)
_GENERATION_RECORDS: dict[str, dict[str, Any]] = {}
_ASSET_RECORDS: dict[str, dict[str, Any]] = {}
RECOGNIZED_COMPOSER_MODULES = {
    "checkpoint_loader_placeholder",
    "positive_prompt_encode",
    "negative_prompt_encode",
    "empty_latent_image",
    "load_image_placeholder",
    "vae_encode_placeholder",
    "ksampler",
    "vae_decode",
    "save_image_placeholder",
    "upscale_placeholder",
    "inpaint_mask_placeholder",
}
ASSET_NODE_ROLES = {
    "CheckpointLoaderSimple": ("model_assets", "checkpoint"),
    "LoraLoader": ("model_assets", "lora"),
    "LoraLoaderModelOnly": ("model_assets", "lora"),
    "VAELoader": ("model_assets", "vae"),
    "ControlNetLoader": ("model_assets", "controlnet"),
    "ControlNetLoaderAdvanced": ("model_assets", "controlnet"),
    "UpscaleModelLoader": ("model_assets", "upscale_model"),
    "LoadImage": ("input_assets", "source_image"),
    "LoadImageMask": ("input_assets", "mask_image"),
    "SaveImage": ("output_assets", "generated_image"),
}
MODEL_ASSET_ROLES = ("checkpoint", "lora", "vae", "controlnet", "upscale_model")
INPUT_ASSET_ROLES = ("source_image", "mask_image")
OUTPUT_ASSET_ROLES = ("generated_image",)
TXT2IMG_REQUIRED_NODES = [
    "CheckpointLoaderSimple",
    "CLIPTextEncode_positive",
    "CLIPTextEncode_negative",
    "EmptyLatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
]
TASK_PLAN_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "txt2img": {
        "input_requirements": [
            "positive_prompt or goal",
            "checkpoint placeholder",
            "width",
            "height",
            "sampler settings",
        ],
        "workflow_requirements": TXT2IMG_REQUIRED_NODES,
        "expected_outputs": [
            "API-format workflow JSON",
            "workflow_hash",
            "validation report",
            "no submitted ComfyUI job",
        ],
    },
    "img2img": {
        "input_requirements": [
            "source_image_path supplied by user at run time",
            "positive_prompt or goal",
            "checkpoint placeholder",
            "denoise",
        ],
        "workflow_requirements": [
            "CheckpointLoaderSimple",
            "LoadImage",
            "VAEEncode",
            "CLIPTextEncode_positive",
            "CLIPTextEncode_negative",
            "KSampler",
            "VAEDecode",
            "SaveImage",
        ],
        "expected_outputs": [
            "dry-run execution plan",
            "required node checklist",
            "blocked real queue submission",
        ],
    },
    "inpaint": {
        "input_requirements": [
            "source_image_path supplied by user at run time",
            "mask_image_path supplied by user at run time",
            "positive_prompt or goal",
            "checkpoint placeholder",
        ],
        "workflow_requirements": [
            "CheckpointLoaderSimple",
            "LoadImage",
            "LoadImageMask or mask input",
            "VAEEncodeForInpaint",
            "CLIPTextEncode_positive",
            "CLIPTextEncode_negative",
            "KSampler",
            "VAEDecode",
            "SaveImage",
        ],
        "expected_outputs": [
            "dry-run execution plan",
            "mask requirements",
            "blocked real queue submission",
        ],
    },
    "upscale": {
        "input_requirements": [
            "source_image_path supplied by user at run time",
            "upscale_model placeholder or built-in method",
            "scale factor",
        ],
        "workflow_requirements": [
            "LoadImage",
            "UpscaleModelLoader or ImageScale",
            "ImageUpscaleWithModel or ImageScale",
            "SaveImage",
        ],
        "expected_outputs": [
            "dry-run execution plan",
            "upscale requirement checklist",
            "blocked real queue submission",
        ],
    },
}


def _as_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _as_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _workflow_type(arguments: dict[str, Any]) -> str:
    requested = str(arguments.get("workflow_type") or "txt2img").strip().lower()
    return requested if requested in SUPPORTED_WORKFLOW_TYPES else "txt2img"


def _positive_prompt(arguments: dict[str, Any]) -> str:
    prompt = str(arguments.get("positive_prompt") or arguments.get("prompt") or "").strip()
    if prompt:
        return prompt
    goal = str(arguments.get("goal") or "").strip()
    style = str(arguments.get("style") or "").strip()
    parts = [part for part in [goal, style, "high quality, detailed composition"] if part]
    return ", ".join(parts) if parts else "a high quality concept art scene"


def _negative_prompt(arguments: dict[str, Any]) -> str:
    return str(arguments.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT).strip()


def _checkpoint(arguments: dict[str, Any]) -> str:
    return str(
        arguments.get("checkpoint") or arguments.get("ckpt_name") or DEFAULT_CHECKPOINT
    ).strip()


def _draft_checkpoint(arguments: dict[str, Any]) -> str:
    value = str(
        arguments.get("checkpoint")
        or arguments.get("ckpt_name")
        or arguments.get("model_name")
        or PLACEHOLDER_CHECKPOINT
    ).strip()
    lowered = value.lower()
    if "\\" in value or "/" in value or lowered.endswith((".safetensors", ".ckpt", ".pt", ".pth")):
        return PLACEHOLDER_CHECKPOINT
    return value or PLACEHOLDER_CHECKPOINT


def _draft_task_type(arguments: dict[str, Any]) -> str:
    requested = (
        str(arguments.get("task_type") or arguments.get("workflow_type") or "txt2img")
        .strip()
        .lower()
    )
    return requested if requested in SUPPORTED_WORKFLOW_TYPES else "txt2img"


def _dimensions(arguments: dict[str, Any]) -> tuple[int, int]:
    return (
        _as_int(arguments.get("width"), 1024, minimum=64, maximum=4096),
        _as_int(arguments.get("height"), 1024, minimum=64, maximum=4096),
    )


def _sampler_settings(arguments: dict[str, Any]) -> dict[str, Any]:
    seed = arguments.get("seed")
    if seed is None and arguments.get("_random_seed"):
        seed = random.randint(1, 2**48)
    return {
        "seed": _as_int(seed, 123456789, minimum=0, maximum=2**63 - 1),
        "steps": _as_int(arguments.get("steps"), 20, minimum=1, maximum=150),
        "cfg": _as_float(arguments.get("cfg"), 7.0, minimum=1.0, maximum=30.0),
        "sampler_name": str(arguments.get("sampler_name") or arguments.get("sampler") or "euler"),
        "scheduler": str(arguments.get("scheduler") or "normal"),
        "denoise": _as_float(arguments.get("denoise"), 1.0, minimum=0.0, maximum=1.0),
    }


def _draft_sampler_settings(arguments: dict[str, Any], *, denoise: float) -> dict[str, Any]:
    settings = _sampler_settings(arguments)
    settings["denoise"] = _as_float(arguments.get("denoise"), denoise, minimum=0.0, maximum=1.0)
    return settings


def _draft_metadata(task_type: str) -> dict[str, Any]:
    return {
        "class_type": "CreNexusDraftMetadata",
        "inputs": {
            "task_type": task_type,
            "status": "draft",
            "draft": True,
            "safe_placeholder": True,
            "production_ready": False,
            "queue_submission": "disabled",
            "model_policy": "placeholder_only",
            "asset_policy": "placeholder_only_no_private_files",
            "note": "Generated by CreNexus workflow_draft; review and replace placeholders locally before any real ComfyUI run.",
        },
    }


def _load_image_node(image_name: str) -> dict[str, Any]:
    return {"class_type": "LoadImage", "inputs": {"image": image_name}}


def workflow_hash(workflow: dict[str, Any]) -> str:
    canonical = json.dumps(workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    class_types: dict[str, int] = {}
    links = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "unknown")
        class_types[class_type] = class_types.get(class_type, 0) + 1
        inputs = node.get("inputs", {})
        if isinstance(inputs, dict):
            links += sum(
                1 for value in inputs.values() if isinstance(value, list) and len(value) == 2
            )
    return {
        "node_count": len(workflow),
        "link_count": links,
        "class_types": dict(sorted(class_types.items())),
        "output_nodes": [
            node_id
            for node_id, node in workflow.items()
            if isinstance(node, dict) and node.get("class_type") == "SaveImage"
        ],
    }


def _node_sort_key(node_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(node_id))
    except ValueError:
        return (1, node_id)


def _walk_string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_walk_string_values(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_walk_string_values(item))
        return strings
    return []


def _is_placeholder_reference(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or "placeholder" in lowered or lowered.startswith("__")


def _asset_policy(
    *, role: str, node_ids: list[str], string_inputs: list[str], category: str
) -> str:
    if not node_ids:
        if role == "vae":
            return "not_declared_or_checkpoint_link"
        return "not_declared"
    if category == "output_assets":
        return "basename_only_after_confirmed_run"
    if string_inputs and all(_is_placeholder_reference(value) for value in string_inputs):
        return "placeholder_only"
    return "redacted_reference_requires_review"


def _asset_entry(
    *, role: str, category: str, node_ids: list[str], string_inputs: list[str]
) -> dict[str, Any]:
    return {
        "role": role,
        "count": len(node_ids),
        "node_ids": sorted(node_ids, key=_node_sort_key),
        "reference_policy": _asset_policy(
            role=role, node_ids=node_ids, string_inputs=string_inputs, category=category
        ),
        "values_exposed": False,
    }


def workflow_asset_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {
        "model_assets": {role: {"node_ids": [], "string_inputs": []} for role in MODEL_ASSET_ROLES},
        "input_assets": {role: {"node_ids": [], "string_inputs": []} for role in INPUT_ASSET_ROLES},
        "output_assets": {
            role: {"node_ids": [], "string_inputs": []} for role in OUTPUT_ASSET_ROLES
        },
    }
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        role_info = ASSET_NODE_ROLES.get(str(node.get("class_type") or ""))
        if role_info is None:
            continue
        category, role = role_info
        bucket = grouped[category][role]
        bucket["node_ids"].append(str(node_id))
        bucket["string_inputs"].extend(_walk_string_values(node.get("inputs", {})))

    model_assets = [
        _asset_entry(
            role=role,
            category="model_assets",
            node_ids=grouped["model_assets"][role]["node_ids"],
            string_inputs=grouped["model_assets"][role]["string_inputs"],
        )
        for role in MODEL_ASSET_ROLES
    ]
    input_assets = [
        _asset_entry(
            role=role,
            category="input_assets",
            node_ids=grouped["input_assets"][role]["node_ids"],
            string_inputs=grouped["input_assets"][role]["string_inputs"],
        )
        for role in INPUT_ASSET_ROLES
    ]
    output_assets = [
        _asset_entry(
            role=role,
            category="output_assets",
            node_ids=grouped["output_assets"][role]["node_ids"],
            string_inputs=grouped["output_assets"][role]["string_inputs"],
        )
        for role in OUTPUT_ASSET_ROLES
    ]
    review_required = any(
        item["reference_policy"] == "redacted_reference_requires_review"
        for item in [*model_assets, *input_assets, *output_assets]
    )
    return sanitize(
        {
            "model_assets": model_assets,
            "input_assets": input_assets,
            "output_assets": output_assets,
            "review_required": review_required,
            "privacy_policy": {
                "model_names_exposed": False,
                "input_paths_exposed": False,
                "output_filenames_exposed": False,
                "generated_images_included": False,
            },
        }
    )


def _lifecycle_stage(name: str, state: str, note: str) -> dict[str, str]:
    return {"name": name, "state": state, "note": note}


def _validation_details(validation: dict[str, Any]) -> dict[str, Any]:
    details = validation.get("details")
    return details if isinstance(details, dict) else {}


def workflow_lifecycle_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    source = "composed_placeholder"
    template_id = str(arguments.get("template_id") or "").strip() or None
    workflow = arguments.get("workflow")
    task_type = _draft_task_type(arguments)
    validation: dict[str, Any] | None = None

    if isinstance(workflow, dict):
        source = "provided_workflow"
        workflow = copy.deepcopy(workflow)
        validation = validate_workflow_payload(
            workflow, workflow_name="provided_lifecycle_workflow"
        )
    elif template_id:
        from examples.comfy_bridge.workflow_template_registry import compose_from_template

        source = "template"
        nested_arguments = arguments.get("arguments")
        template_arguments = nested_arguments if isinstance(nested_arguments, dict) else {}
        template_result = compose_from_template(template_id, template_arguments)
        workflow = template_result.get("workflow")
        task_type = str(template_result.get("task_type") or task_type)
        validation = (
            template_result.get("validation_report")
            if isinstance(template_result.get("validation_report"), dict)
            else None
        )
        if not isinstance(workflow, dict):
            return sanitize(
                {
                    "ok": False,
                    "bridge": BRIDGE_ID,
                    "action": "workflow_lifecycle_summary",
                    "mode": "safe_read_only",
                    "source": source,
                    "template_id": template_id,
                    "will_submit": False,
                    "error": template_result.get("error") or "template_workflow_unavailable",
                    "warnings": list(template_result.get("warnings") or []),
                }
            )
    else:
        composed = workflow_compose(arguments)
        workflow = composed.get("workflow")
        validation = (
            composed.get("validation_report")
            if isinstance(composed.get("validation_report"), dict)
            else None
        )
        if not isinstance(workflow, dict):
            return sanitize(
                {
                    "ok": False,
                    "bridge": BRIDGE_ID,
                    "action": "workflow_lifecycle_summary",
                    "mode": "safe_read_only",
                    "source": source,
                    "will_submit": False,
                    "error": "workflow_unavailable",
                }
            )

    if validation is None:
        validation = validate_workflow_payload(workflow, workflow_name="lifecycle_workflow")

    valid = bool(validation.get("ok"))
    confirm_run = bool(arguments.get("confirm_run", False))
    workflow_digest = workflow_hash(workflow)
    node_summary = workflow_summary(workflow)
    asset_summary = workflow_asset_summary(workflow)
    validation_details = _validation_details(validation)

    submit_status = (
        "ready_for_separate_confirmed_submit"
        if confirm_run and valid
        else (
            "blocked_until_workflow_valid" if not valid else "blocked_until_explicit_confirmation"
        )
    )
    job_status = JobStatus(
        job_id=f"comfy_lifecycle_{workflow_digest[:12]}",
        bridge=BRIDGE_ID,
        action="workflow_lifecycle_summary",
        status="queued" if confirm_run and valid else "needs_user",
        progress=5 if confirm_run and valid else 0,
        message=(
            "Workflow is valid and ready for a separate confirmed submit gate."
            if confirm_run and valid
            else "Workflow lifecycle summary is dry-run only; explicit confirmation is required before submit."
        ),
        evidence_manifest={
            "manifest_path": "examples/output/evidence/manifest.latest.json",
            "dry_run": True,
            "write_performed": False,
            "output_policy": "record counts and basenames only after a separate confirmed local run",
        },
        next_steps=[
            "Review validation and asset summary.",
            "Keep placeholders until a separate local run is explicitly confirmed.",
            "Use comfyui.agent_run only after review; this lifecycle summary never submits.",
        ],
    ).to_dict()

    warnings = list(validation.get("warnings") or [])
    if asset_summary["review_required"]:
        warnings.append("One or more asset references were redacted and require review.")
    if not confirm_run:
        warnings.append(
            "Queue submission is blocked until confirm_run=true in a separate run flow."
        )
    if not valid:
        warnings.append("Workflow validation failed; queue submission remains blocked.")

    lifecycle = [
        _lifecycle_stage(
            "workflow_received",
            "completed",
            f"Source is {source}; raw workflow JSON is intentionally omitted from this summary.",
        ),
        _lifecycle_stage(
            "workflow_validated",
            "completed" if valid else "failed",
            "Validation result is summarized without exposing prompts, model names, or paths.",
        ),
        _lifecycle_stage(
            "assets_reviewed",
            "needs_user" if asset_summary["review_required"] else "completed",
            "Model, input, and output assets are counted by role; values stay hidden.",
        ),
        _lifecycle_stage(
            "queue_submit_gate",
            "queued" if confirm_run and valid else "needs_user",
            "This tool does not call /prompt; real submission must happen through a confirmed local run.",
        ),
        _lifecycle_stage(
            "history_poll",
            "queued" if confirm_run and valid else "needs_user",
            "History and outputs are not read by this summary.",
        ),
        _lifecycle_stage(
            "evidence_manifest",
            "queued",
            "Future confirmed runs should record only job status, counts, hashes, and output basenames.",
        ),
    ]

    return sanitize(
        {
            "ok": valid,
            "bridge": BRIDGE_ID,
            "action": "workflow_lifecycle_summary",
            "mode": "safe_read_only",
            "source": source,
            "template_id": template_id,
            "task_type": task_type,
            "workflow_hash": workflow_digest,
            "node_summary": node_summary,
            "asset_summary": asset_summary,
            "validation_summary": {
                "ok": valid,
                "warning_count": len(validation.get("warnings") or []),
                "error_count": len(validation_details.get("errors") or []),
            },
            "job_status": job_status,
            "lifecycle": lifecycle,
            "submit_gate": {
                "required": True,
                "confirmed": confirm_run,
                "status": submit_status,
                "tool_can_submit": False,
                "separate_submit_tool": "comfyui.agent_run",
            },
            "will_submit": False,
            "will_read_history": False,
            "will_read_outputs": False,
            "warnings": warnings,
            "safety_notes": [
                "No model, LoRA, VAE, ControlNet, input image, or generated image values are returned.",
                "No filesystem scan, model discovery, output inspection, network request, or queue submission is performed.",
                "A real ComfyUI queue run remains behind explicit user confirmation and local evidence review.",
            ],
        }
    )


def workflow_build_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow_type = _workflow_type(arguments)
    width, height = _dimensions(arguments)
    task_requirements = TASK_PLAN_REQUIREMENTS[workflow_type]
    blocked_reasons = []
    if workflow_type not in BUILDABLE_WORKFLOW_TYPES:
        blocked_reasons.append(
            f"{workflow_type} is plan-only in this repository; real ComfyUI queue submission is not implemented."
        )
    if workflow_type in {"img2img", "inpaint", "upscale"}:
        blocked_reasons.append(
            "Private input images must be supplied only during an explicit local run and must not be committed."
        )
    if workflow_type == "inpaint":
        blocked_reasons.append(
            "Mask files are private local inputs and are not read by this dry-run planner."
        )
    return sanitize(
        {
            "ok": True,
            "bridge": BRIDGE_ID,
            "action": "workflow_build_plan",
            "mode": "dry_run",
            "workflow_type": workflow_type,
            "task_type": workflow_type,
            "goal": str(arguments.get("goal") or ""),
            "style": str(arguments.get("style") or ""),
            "width": width,
            "height": height,
            "required_nodes": task_requirements["workflow_requirements"],
            "input_requirements": task_requirements["input_requirements"],
            "workflow_requirements": task_requirements["workflow_requirements"],
            "safety_notes": [
                "Dry-run only; this plan does not call /prompt or inspect the local filesystem.",
                "Use placeholders for checkpoints, LoRA, VAE, ControlNet, and input images.",
                "Do not commit generated images, model files, private prompts, or local output paths.",
            ],
            "expected_outputs": task_requirements["expected_outputs"],
            "blocked_reasons": blocked_reasons,
            "will_build": False,
            "will_submit": False,
            "warnings": []
            if workflow_type in BUILDABLE_WORKFLOW_TYPES
            else [f"{workflow_type} is available as dry-run plan only."],
        }
    )


def build_txt2img_workflow(arguments: dict[str, Any]) -> dict[str, Any]:
    width, height = _dimensions(arguments)
    sampler = _sampler_settings(arguments)
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                **sampler,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _checkpoint(arguments)},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": ["4", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _negative_prompt(arguments), "clip": ["4", 1]},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": str(
                    arguments.get("filename_prefix") or "starbridge_agent_txt2img"
                ),
                "images": ["8", 0],
            },
        },
    }


def build_txt2img_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    width, height = _dimensions(arguments)
    sampler = _draft_sampler_settings(arguments, denoise=1.0)
    return {
        "1": _draft_metadata("txt2img"),
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _draft_checkpoint(arguments)},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                **sampler,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "starbridge_txt2img_draft", "images": ["7", 0]},
        },
    }


def build_img2img_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    sampler = _draft_sampler_settings(arguments, denoise=0.55)
    return {
        "1": _draft_metadata("img2img"),
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _draft_checkpoint(arguments)},
        },
        "3": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["3", 0], "vae": ["2", 2]}},
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]},
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                **sampler,
                "model": ["2", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["4", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["2", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "starbridge_img2img_draft", "images": ["8", 0]},
        },
    }


def build_inpaint_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    sampler = _draft_sampler_settings(arguments, denoise=0.8)
    return {
        "1": _draft_metadata("inpaint"),
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _draft_checkpoint(arguments)},
        },
        "3": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "4": {
            "class_type": "LoadImageMask",
            "inputs": {"image": PLACEHOLDER_MASK_IMAGE, "channel": "alpha"},
        },
        "5": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {"pixels": ["3", 0], "vae": ["2", 2], "mask": ["4", 0]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]},
        },
        "8": {
            "class_type": "KSampler",
            "inputs": {
                **sampler,
                "model": ["2", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["2", 2]}},
        "10": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "starbridge_inpaint_draft", "images": ["9", 0]},
        },
    }


def build_upscale_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    scale_by = _as_float(arguments.get("scale_by"), 2.0, minimum=1.0, maximum=8.0)
    return {
        "1": _draft_metadata("upscale"),
        "2": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "3": {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": PLACEHOLDER_UPSCALE_MODEL},
        },
        "4": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]},
        },
        "5": {
            "class_type": "ImageScale",
            "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "scale_by": scale_by},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": ["7", 1]},
        },
        "7": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _draft_checkpoint(arguments)},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "starbridge_upscale_draft", "images": ["5", 0]},
        },
    }


def build_draft_workflow(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = _draft_task_type(arguments)
    builders = {
        "txt2img": build_txt2img_draft,
        "img2img": build_img2img_draft,
        "inpaint": build_inpaint_draft,
        "upscale": build_upscale_draft,
    }
    return builders[task_type](arguments)


def module_checkpoint_loader_placeholder(node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": _draft_checkpoint(arguments)},
        }
    }


def module_positive_prompt_encode(
    node_id: str, checkpoint_node_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _positive_prompt(arguments), "clip": [checkpoint_node_id, 1]},
        }
    }


def module_negative_prompt_encode(
    node_id: str, checkpoint_node_id: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": _negative_prompt(arguments), "clip": [checkpoint_node_id, 1]},
        }
    }


def module_empty_latent_image(node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    width, height = _dimensions(arguments)
    return {
        node_id: {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        }
    }


def module_load_image_placeholder(node_id: str) -> dict[str, Any]:
    return {node_id: _load_image_node(PLACEHOLDER_SOURCE_IMAGE)}


def module_vae_encode_placeholder(
    node_id: str, image_node_id: str, checkpoint_node_id: str, mask_node_id: str | None = None
) -> dict[str, Any]:
    if mask_node_id:
        return {
            node_id: {
                "class_type": "VAEEncodeForInpaint",
                "inputs": {
                    "pixels": [image_node_id, 0],
                    "vae": [checkpoint_node_id, 2],
                    "mask": [mask_node_id, 0],
                },
            }
        }
    return {
        node_id: {
            "class_type": "VAEEncode",
            "inputs": {"pixels": [image_node_id, 0], "vae": [checkpoint_node_id, 2]},
        }
    }


def module_ksampler(
    node_id: str,
    *,
    checkpoint_node_id: str,
    positive_node_id: str,
    negative_node_id: str,
    latent_node_id: str,
    arguments: dict[str, Any],
    denoise: float,
) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "KSampler",
            "inputs": {
                **_draft_sampler_settings(arguments, denoise=denoise),
                "model": [checkpoint_node_id, 0],
                "positive": [positive_node_id, 0],
                "negative": [negative_node_id, 0],
                "latent_image": [latent_node_id, 0],
            },
        }
    }


def module_vae_decode(
    node_id: str, sampler_node_id: str, checkpoint_node_id: str
) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "VAEDecode",
            "inputs": {"samples": [sampler_node_id, 0], "vae": [checkpoint_node_id, 2]},
        }
    }


def module_save_image_placeholder(
    node_id: str, image_node_id: str, filename_prefix: str
) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": [image_node_id, 0]},
        }
    }


def module_upscale_placeholder(
    model_node_id: str,
    upscale_node_id: str,
    scale_node_id: str,
    image_node_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    scale_by = _as_float(
        arguments.get("scale") if "scale" in arguments else arguments.get("scale_by"),
        2.0,
        minimum=1.0,
        maximum=8.0,
    )
    return {
        model_node_id: {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": PLACEHOLDER_UPSCALE_MODEL},
        },
        upscale_node_id: {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": [model_node_id, 0], "image": [image_node_id, 0]},
        },
        scale_node_id: {
            "class_type": "ImageScale",
            "inputs": {
                "image": [upscale_node_id, 0],
                "upscale_method": "lanczos",
                "scale_by": scale_by,
            },
        },
    }


def module_inpaint_mask_placeholder(node_id: str) -> dict[str, Any]:
    return {
        node_id: {
            "class_type": "LoadImageMask",
            "inputs": {"image": PLACEHOLDER_MASK_IMAGE, "channel": "alpha"},
        }
    }


def _composer_metadata(task_type: str) -> dict[str, Any]:
    metadata = _draft_metadata(task_type)
    metadata["inputs"]["composer"] = "workflow_graph_composer"
    metadata["inputs"]["module_graph"] = True
    return metadata


def compose_workflow(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = _draft_task_type(arguments)
    workflow: dict[str, Any] = {"1": _composer_metadata(task_type)}

    if task_type == "txt2img":
        workflow.update(module_checkpoint_loader_placeholder("2", arguments))
        workflow.update(module_positive_prompt_encode("3", "2", arguments))
        workflow.update(module_negative_prompt_encode("4", "2", arguments))
        workflow.update(module_empty_latent_image("5", arguments))
        workflow.update(
            module_ksampler(
                "6",
                checkpoint_node_id="2",
                positive_node_id="3",
                negative_node_id="4",
                latent_node_id="5",
                arguments=arguments,
                denoise=1.0,
            )
        )
        workflow.update(module_vae_decode("7", "6", "2"))
        workflow.update(module_save_image_placeholder("8", "7", "starbridge_txt2img_composed"))
    elif task_type == "img2img":
        workflow.update(module_checkpoint_loader_placeholder("2", arguments))
        workflow.update(module_load_image_placeholder("3"))
        workflow.update(module_vae_encode_placeholder("4", "3", "2"))
        workflow.update(module_positive_prompt_encode("5", "2", arguments))
        workflow.update(module_negative_prompt_encode("6", "2", arguments))
        workflow.update(
            module_ksampler(
                "7",
                checkpoint_node_id="2",
                positive_node_id="5",
                negative_node_id="6",
                latent_node_id="4",
                arguments=arguments,
                denoise=0.55,
            )
        )
        workflow.update(module_vae_decode("8", "7", "2"))
        workflow.update(module_save_image_placeholder("9", "8", "starbridge_img2img_composed"))
    elif task_type == "inpaint":
        workflow.update(module_checkpoint_loader_placeholder("2", arguments))
        workflow.update(module_load_image_placeholder("3"))
        workflow.update(module_inpaint_mask_placeholder("4"))
        workflow.update(module_vae_encode_placeholder("5", "3", "2", mask_node_id="4"))
        workflow.update(module_positive_prompt_encode("6", "2", arguments))
        workflow.update(module_negative_prompt_encode("7", "2", arguments))
        workflow.update(
            module_ksampler(
                "8",
                checkpoint_node_id="2",
                positive_node_id="6",
                negative_node_id="7",
                latent_node_id="5",
                arguments=arguments,
                denoise=0.8,
            )
        )
        workflow.update(module_vae_decode("9", "8", "2"))
        workflow.update(module_save_image_placeholder("10", "9", "starbridge_inpaint_composed"))
    else:
        workflow.update(module_load_image_placeholder("2"))
        workflow.update(module_upscale_placeholder("3", "4", "5", "2", arguments))
        workflow.update(module_save_image_placeholder("6", "5", "starbridge_upscale_composed"))

    return workflow


def workflow_compose(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = _draft_task_type(arguments)
    workflow = compose_workflow(arguments)
    validation = validate_workflow_payload(workflow, workflow_name=f"{task_type}_composed_workflow")
    safety_notes = [
        "Composed workflow is safe placeholder JSON only.",
        "No ComfyUI queue submission is performed.",
        "No filesystem reads, model discovery, output inspection, or network requests are performed.",
        "Replace placeholders only in a separate reviewed local step.",
    ]
    return sanitize(
        {
            "ok": bool(validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_compose",
            "mode": "dry_run",
            "task_type": task_type,
            "valid": bool(validation.get("ok")),
            "workflow": workflow,
            "workflow_hash": workflow_hash(workflow),
            "node_summary": workflow_summary(workflow),
            "validation_report": validation,
            "warnings": list(validation.get("warnings") or []),
            "safety_notes": safety_notes,
            "next_steps": [
                "Review the composed graph and validation report.",
                "Keep placeholder assets until a user explicitly approves a local-only run.",
                "Run workflow_validate again after any manual graph edits.",
            ],
        }
    )


def workflow_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    task_type = _draft_task_type(arguments)
    workflow = build_draft_workflow(arguments)
    validation = validate_workflow_payload(workflow, workflow_name=f"{task_type}_draft_workflow")
    safety_notes = [
        "Draft only; not a final production workflow.",
        "No ComfyUI queue submission is performed.",
        "No filesystem reads, model discovery, output inspection, or network requests are performed.",
        "Model and asset fields use placeholders only.",
    ]
    warnings = list(validation.get("warnings") or [])
    if not validation.get("ok"):
        warnings.append(
            "Draft validation failed; inspect validation_report before using this workflow locally."
        )
    return sanitize(
        {
            "ok": bool(validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_draft",
            "mode": "dry_run",
            "task_type": task_type,
            "valid": bool(validation.get("ok")),
            "workflow": workflow,
            "workflow_hash": workflow_hash(workflow),
            "node_summary": workflow_summary(workflow),
            "validation_report": validation,
            "warnings": warnings,
            "safety_notes": safety_notes,
            "next_steps": [
                "Review the draft JSON and validation report.",
                "Replace placeholders locally only after explicit user confirmation.",
                "Run workflow_validate again before any separate real ComfyUI submission step.",
            ],
        }
    )


def workflow_build(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow_type = _workflow_type(arguments)
    if workflow_type not in BUILDABLE_WORKFLOW_TYPES:
        plan = workflow_build_plan(arguments)
        return sanitize(
            {
                "ok": False,
                "bridge": BRIDGE_ID,
                "action": "workflow_build",
                "mode": "dry_run",
                "workflow_type": workflow_type,
                "task_type": workflow_type,
                "build_plan": plan,
                "workflow": None,
                "workflow_hash": None,
                "will_submit": False,
                "warnings": [
                    f"{workflow_type} workflow build is not implemented; only dry-run planning is supported."
                ],
                "next_steps": [
                    "Use comfyui.workflow_build_plan for this task type until a reviewed safe workflow template exists."
                ],
            }
        )
    workflow = build_txt2img_workflow(arguments)
    validation = validate_workflow_payload(workflow, workflow_name="agent_generated_txt2img")
    return sanitize(
        {
            "ok": bool(validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_build",
            "mode": "dry_run",
            "workflow_type": workflow_type,
            "workflow": workflow,
            "workflow_hash": workflow_hash(workflow),
            "node_summary": workflow_summary(workflow),
            "validation": validation,
            "will_submit": False,
            "warnings": [] if validation.get("ok") else validation.get("warnings", []),
            "next_steps": [
                "Review the workflow, then call comfyui.agent_run with confirm_run=true to submit."
            ],
        }
    )


def _find_nodes(workflow: dict[str, Any], class_type: str) -> list[str]:
    return [
        node_id
        for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == class_type
    ]


def workflow_repair(arguments: dict[str, Any]) -> dict[str, Any]:
    source = arguments.get("workflow")
    base_arguments = {key: value for key, value in arguments.items() if key != "workflow"}
    repaired = build_txt2img_workflow(base_arguments)
    changes: list[str] = []

    if isinstance(source, dict):
        candidate = copy.deepcopy(source)
        for node_id, fallback_node in repaired.items():
            node = candidate.get(node_id)
            if not isinstance(node, dict) or node.get("class_type") != fallback_node["class_type"]:
                candidate[node_id] = copy.deepcopy(fallback_node)
                changes.append(f"recreated node {node_id}:{fallback_node['class_type']}")
            else:
                inputs = node.setdefault("inputs", {})
                if not isinstance(inputs, dict):
                    node["inputs"] = {}
                    inputs = node["inputs"]
                    changes.append(f"recreated inputs for node {node_id}")
                for input_name, fallback_value in fallback_node["inputs"].items():
                    if input_name not in inputs or inputs[input_name] in (None, ""):
                        inputs[input_name] = copy.deepcopy(fallback_value)
                        changes.append(f"filled {node_id}.{input_name}")
        repaired = candidate
    else:
        changes.append("created workflow from scratch")

    repaired["3"]["inputs"].update(_sampler_settings(repaired["3"].get("inputs", {})))
    repaired["5"]["inputs"]["width"], repaired["5"]["inputs"]["height"] = _dimensions(
        repaired["5"].get("inputs", {})
    )
    if not str(repaired["6"]["inputs"].get("text") or "").strip():
        repaired["6"]["inputs"]["text"] = _positive_prompt(base_arguments)
        changes.append("filled positive prompt")
    if not str(repaired["7"]["inputs"].get("text") or "").strip():
        repaired["7"]["inputs"]["text"] = _negative_prompt(base_arguments)
        changes.append("filled negative prompt")

    required_links = {
        ("3", "model"): ["4", 0],
        ("3", "positive"): ["6", 0],
        ("3", "negative"): ["7", 0],
        ("3", "latent_image"): ["5", 0],
        ("6", "clip"): ["4", 1],
        ("7", "clip"): ["4", 1],
        ("8", "samples"): ["3", 0],
        ("8", "vae"): ["4", 2],
        ("9", "images"): ["8", 0],
    }
    for (node_id, input_name), expected in required_links.items():
        inputs = repaired[node_id].setdefault("inputs", {})
        if inputs.get(input_name) != expected:
            inputs[input_name] = copy.deepcopy(expected)
            changes.append(f"repaired link {node_id}.{input_name}")

    validation = validate_workflow_payload(repaired, workflow_name="agent_repaired_txt2img")
    return sanitize(
        {
            "ok": bool(validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_repair",
            "mode": "dry_run",
            "workflow_type": "txt2img",
            "workflow": repaired,
            "workflow_hash": workflow_hash(repaired),
            "node_summary": workflow_summary(repaired),
            "repairs": changes,
            "validation": validation,
            "will_submit": False,
        }
    )


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def get_json(base_url: str, path: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(base_url, path),
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_COMFY_RESPONSE_BYTES + 1)
    if len(raw) > MAX_COMFY_RESPONSE_BYTES:
        raise ValueError("ComfyUI response exceeds the safe limit")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ComfyUI response must be a JSON object")
    return payload


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(base_url, path),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_COMFY_RESPONSE_BYTES + 1)
    if len(raw) > MAX_COMFY_RESPONSE_BYTES:
        raise ValueError("ComfyUI response exceeds the safe limit")
    response_payload = json.loads(raw.decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise ValueError("ComfyUI response must be a JSON object")
    return response_payload


def _output_basename(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/")
    return normalized.rsplit("/", 1)[-1]


def _logical_asset_id(
    *,
    prompt_id: str,
    node_id: str,
    filename: Any,
    subfolder: Any,
    output_type: Any,
    position: int,
) -> str:
    canonical = json.dumps(
        {
            "prompt_id": prompt_id,
            "node_id": node_id,
            "filename": str(filename or ""),
            "subfolder": str(subfolder or ""),
            "type": str(output_type or "output"),
            "position": position,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"asset_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _prune_provenance(*, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    for records in (_GENERATION_RECORDS, _ASSET_RECORDS):
        expired = [
            key
            for key, record in records.items()
            if current - float(record.get("created_at", 0.0)) > PROVENANCE_TTL_SECONDS
        ]
        for key in expired:
            records.pop(key, None)
        while len(records) > MAX_PROVENANCE_RECORDS:
            oldest = min(records, key=lambda key: float(records[key].get("created_at", 0.0)))
            records.pop(oldest, None)


def _remember_generation(prompt_id: str, workflow: dict[str, Any]) -> None:
    _prune_provenance()
    _GENERATION_RECORDS[prompt_id] = {
        "created_at": time.monotonic(),
        "workflow": copy.deepcopy(workflow),
    }
    _prune_provenance()


def _remember_manifest_assets(prompt_id: str, manifest: dict[str, Any]) -> None:
    _prune_provenance()
    generation = _GENERATION_RECORDS.get(prompt_id)
    if not isinstance(generation, dict) or not isinstance(generation.get("workflow"), dict):
        return
    images = manifest.get("images")
    if not isinstance(images, list):
        return
    for image in images:
        if not isinstance(image, dict):
            continue
        asset_id = image.get("asset_id")
        if not isinstance(asset_id, str) or ASSET_ID_PATTERN.fullmatch(asset_id) is None:
            continue
        _ASSET_RECORDS[asset_id] = {
            "created_at": time.monotonic(),
            "workflow": copy.deepcopy(generation["workflow"]),
        }
    _prune_provenance()


def _asset_workflow(asset_id: str) -> dict[str, Any] | None:
    _prune_provenance()
    record = _ASSET_RECORDS.get(asset_id)
    workflow = record.get("workflow") if isinstance(record, dict) else None
    return copy.deepcopy(workflow) if isinstance(workflow, dict) else None


def output_manifest_from_history(prompt_id: str, history: dict[str, Any]) -> dict[str, Any]:
    prompt_history = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    if not isinstance(prompt_history, dict):
        prompt_history = {}
    node_outputs = prompt_history.get("outputs", {})
    if not isinstance(node_outputs, dict):
        node_outputs = {}
    outputs = []
    for node_id, node_output in node_outputs.items():
        if not isinstance(node_output, dict):
            continue
        images = node_output.get("images", [])
        if not isinstance(images, list):
            continue
        for position, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            raw_filename = image.get("filename")
            raw_subfolder = image.get("subfolder")
            output_type = image.get("type") or "output"
            outputs.append(
                {
                    "asset_id": _logical_asset_id(
                        prompt_id=prompt_id,
                        node_id=str(node_id),
                        filename=raw_filename,
                        subfolder=raw_subfolder,
                        output_type=output_type,
                        position=position,
                    ),
                    "node_id": str(node_id),
                    "filename": _output_basename(raw_filename),
                    "subfolder": _output_basename(raw_subfolder),
                    "type": str(output_type),
                }
            )
    return sanitize({"prompt_id": prompt_id, "image_count": len(outputs), "images": outputs})


def _history_terminal_state(prompt_history: Any) -> tuple[str, str | None]:
    if not isinstance(prompt_history, dict):
        return "status_unavailable", None

    status = prompt_history.get("status", {})
    if not isinstance(status, dict):
        return "status_unavailable", None

    terminal_events = set()
    messages = status.get("messages", [])
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, (list, tuple)) or not message:
                continue
            event = message[0]
            if isinstance(event, str) and event in {
                "execution_success",
                "execution_error",
                "execution_interrupted",
            }:
                terminal_events.add(event)

    status_str = str(status.get("status_str") or "").strip().lower()
    if status_str in {"success", "completed"}:
        terminal_event = "execution_success" if "execution_success" in terminal_events else None
        return "completed", terminal_event
    if status_str in {"error", "failed", "failure"}:
        if "execution_interrupted" in terminal_events:
            return "cancelled", "execution_interrupted"
        terminal_event = "execution_error" if "execution_error" in terminal_events else None
        return "failed", terminal_event
    if status_str in {"cancelled", "canceled", "interrupted"}:
        terminal_event = (
            "execution_interrupted" if "execution_interrupted" in terminal_events else None
        )
        return "cancelled", terminal_event

    if status.get("completed") is True:
        terminal_event = "execution_success" if "execution_success" in terminal_events else None
        return "completed", terminal_event
    if status.get("completed") is False:
        if "execution_interrupted" in terminal_events:
            return "cancelled", "execution_interrupted"
        terminal_event = "execution_error" if "execution_error" in terminal_events else None
        return "failed", terminal_event

    for terminal_event, state in (
        ("execution_interrupted", "cancelled"),
        ("execution_error", "failed"),
        ("execution_success", "completed"),
    ):
        if terminal_event in terminal_events:
            return state, terminal_event

    # History presence alone is not proof that generation completed successfully.
    return "status_unavailable", None


def query_job_status(base_url: str, prompt_id: str, timeout: int) -> dict[str, Any]:
    history = get_json(base_url, f"/history/{prompt_id}", timeout)
    if isinstance(history, dict) and prompt_id in history:
        state, terminal_event = _history_terminal_state(history[prompt_id])
        result = {
            "state": state,
            "history_available": True,
            "output_manifest": output_manifest_from_history(prompt_id, history),
        }
        if terminal_event is not None:
            result["terminal_event"] = terminal_event
        return result
    return {
        "state": "queued_or_running",
        "history_available": False,
        "output_manifest": {"prompt_id": prompt_id, "image_count": 0, "images": []},
    }


def _validate_prompt_id(value: Any) -> str:
    if not isinstance(value, str) or PROMPT_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("prompt_id must be a bounded URL-safe identifier")
    return value


def _validate_asset_id(value: Any) -> str:
    if not isinstance(value, str) or ASSET_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("asset_id must be a canonical CreNexus asset identifier")
    return value


def _logical_generation_id(prompt_id: str) -> str:
    return f"generation_{hashlib.sha256(prompt_id.encode('utf-8')).hexdigest()[:12]}"


def generation_result(arguments: dict[str, Any]) -> dict[str, Any]:
    prompt_id = _validate_prompt_id(arguments.get("prompt_id"))
    base_url = _validate_loopback_url(str(arguments.get("comfy_url") or DEFAULT_BASE_URL))
    timeout = _as_int(arguments.get("timeout"), 8, minimum=1, maximum=15)
    wait_seconds = _as_int(arguments.get("wait_seconds"), 0, minimum=0, maximum=60)
    poll_interval = _as_float(arguments.get("poll_interval"), 1.0, minimum=0.2, maximum=5.0)
    logical_job_id = _logical_generation_id(prompt_id)
    history: dict[str, Any] = {}
    deadline = time.monotonic() + wait_seconds

    try:
        while True:
            history = get_json(base_url, f"/history/{prompt_id}", timeout)
            if prompt_id in history or time.monotonic() >= deadline:
                break
            time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return sanitize(
            {
                "ok": False,
                "bridge": BRIDGE_ID,
                "action": "generation_result",
                "mode": "live_read_only",
                "logical_job_id": logical_job_id,
                "state": "unavailable",
                "terminal": False,
                "result_ready": False,
                "output_manifest": {"image_count": 0, "images": []},
                "retryable": True,
                "warnings": ["comfyui_generation_history_unavailable"],
                "next_steps": ["Confirm local ComfyUI is running, then retry this result read."],
            }
        )

    prompt_history = history.get(prompt_id)
    if not isinstance(prompt_history, dict):
        state = "queued_or_running"
        manifest = {"image_count": 0, "images": []}
    else:
        state, _terminal_event = _history_terminal_state(prompt_history)
        raw_manifest = output_manifest_from_history(prompt_id, history)
        manifest = {
            "image_count": raw_manifest["image_count"],
            "images": raw_manifest["images"],
        }
        if state == "completed" and manifest["image_count"] == 0:
            state = "completed_no_outputs"
        _remember_manifest_assets(prompt_id, manifest)

    terminal = state in {"completed", "completed_no_outputs", "failed", "cancelled"}
    result_ready = state == "completed" and manifest["image_count"] > 0
    next_steps = {
        "queued_or_running": ["Call comfyui.generation_result again after a short delay."],
        "completed": ["Review the generated images locally; keep image bytes outside Git."],
        "completed_no_outputs": ["Inspect the reviewed workflow output nodes before regenerating."],
        "failed": ["Inspect ComfyUI locally, adjust reviewed inputs, then explicitly regenerate."],
        "cancelled": ["Confirm the interruption was expected before explicitly regenerating."],
        "status_unavailable": [
            "Retry this history read with the same prompt_id before deciding whether to regenerate."
        ],
    }[state]
    return sanitize(
        {
            "ok": state not in {"failed", "cancelled", "status_unavailable"},
            "bridge": BRIDGE_ID,
            "action": "generation_result",
            "mode": "live_read_only",
            "logical_job_id": logical_job_id,
            "state": state,
            "terminal": terminal,
            "result_ready": result_ready,
            "output_manifest": manifest,
            "retryable": state
            in {"queued_or_running", "failed", "cancelled", "status_unavailable"},
            "warnings": (
                []
                if state not in {"failed", "cancelled", "status_unavailable"}
                else [f"generation_{state}"]
            ),
            "next_steps": next_steps,
        }
    )


def asset_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
    asset_id = _validate_asset_id(arguments.get("asset_id"))
    now = time.monotonic()
    _prune_provenance(now=now)
    record = _ASSET_RECORDS.get(asset_id)
    workflow = record.get("workflow") if isinstance(record, dict) else None
    base_result = {
        "bridge": BRIDGE_ID,
        "action": "asset_metadata",
        "mode": "session_read_only",
        "asset_id": asset_id,
        "supported_overrides": list(REGENERATION_OVERRIDE_FIELDS),
    }
    if not isinstance(record, dict) or not isinstance(workflow, dict):
        return sanitize(
            {
                **base_result,
                "ok": False,
                "available": False,
                "can_regenerate": False,
                "workflow_hash": None,
                "error_code": "asset_provenance_unavailable",
                "provenance": {
                    "storage": "memory_only",
                    "persisted": False,
                    "ttl_seconds": PROVENANCE_TTL_SECONDS,
                    "expires_in_seconds": 0,
                },
                "warnings": ["asset_provenance_unavailable"],
                "next_steps": [
                    "Generate and resolve the asset in the current MCP server session before regenerating."
                ],
            }
        )

    created_at = float(record.get("created_at", now))
    age_seconds = max(0.0, now - created_at)
    expires_in_seconds = max(0, int(PROVENANCE_TTL_SECONDS - age_seconds))
    return sanitize(
        {
            **base_result,
            "ok": True,
            "available": True,
            "can_regenerate": True,
            "workflow_hash": workflow_hash(workflow),
            "error_code": None,
            "provenance": {
                "storage": "memory_only",
                "persisted": False,
                "ttl_seconds": PROVENANCE_TTL_SECONDS,
                "expires_in_seconds": expires_in_seconds,
            },
            "warnings": [],
            "next_steps": [
                "Review a comfyui.regenerate dry-run before explicitly confirming a new submission."
            ],
        }
    )


def asset_list(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = _as_int(
        arguments.get("limit"),
        DEFAULT_ASSET_LIST_LIMIT,
        minimum=1,
        maximum=MAX_ASSET_LIST_LIMIT,
    )
    now = time.monotonic()
    _prune_provenance(now=now)
    available_records = [
        (asset_id, record)
        for asset_id, record in _ASSET_RECORDS.items()
        if ASSET_ID_PATTERN.fullmatch(asset_id) is not None
        and isinstance(record, dict)
        and isinstance(record.get("workflow"), dict)
    ]
    available_records.sort(key=lambda item: (-float(item[1].get("created_at", 0.0)), item[0]))
    selected_records = available_records[:limit]
    assets = []
    for asset_id, record in selected_records:
        created_at = float(record.get("created_at", now))
        age_seconds = max(0.0, now - created_at)
        assets.append(
            {
                "asset_id": asset_id,
                "can_regenerate": True,
                "workflow_hash": workflow_hash(record["workflow"]),
                "expires_in_seconds": max(0, int(PROVENANCE_TTL_SECONDS - age_seconds)),
            }
        )

    total_available = len(available_records)
    return sanitize(
        {
            "ok": True,
            "bridge": BRIDGE_ID,
            "action": "asset_list",
            "mode": "session_read_only",
            "limit": limit,
            "asset_count": len(assets),
            "total_available": total_available,
            "truncated": total_available > len(assets),
            "assets": assets,
            "provenance": {
                "storage": "memory_only",
                "persisted": False,
                "ttl_seconds": PROVENANCE_TTL_SECONDS,
                "max_records": MAX_PROVENANCE_RECORDS,
            },
            "warnings": [],
            "next_steps": (
                ["Select an asset_id and call comfyui.asset_metadata before regeneration."]
                if assets
                else [
                    "Generate and resolve an asset in the current MCP server session before listing again."
                ]
            ),
        }
    )


def _regeneration_workflow(
    workflow: dict[str, Any], arguments: dict[str, Any], *, randomize_seed: bool
) -> tuple[dict[str, Any], list[str]]:
    candidate = copy.deepcopy(workflow)
    applied: list[str] = []
    sampler = candidate.get("3")
    latent = candidate.get("5")
    positive = candidate.get("6")
    negative = candidate.get("7")
    sampler_inputs = sampler.get("inputs") if isinstance(sampler, dict) else None
    latent_inputs = latent.get("inputs") if isinstance(latent, dict) else None
    positive_inputs = positive.get("inputs") if isinstance(positive, dict) else None
    negative_inputs = negative.get("inputs") if isinstance(negative, dict) else None

    if not all(
        isinstance(item, dict)
        for item in (sampler_inputs, latent_inputs, positive_inputs, negative_inputs)
    ):
        return candidate, applied

    if "prompt" in arguments:
        positive_inputs["text"] = str(arguments.get("prompt") or "")
        applied.append("prompt")
    if "negative_prompt" in arguments:
        negative_inputs["text"] = str(arguments.get("negative_prompt") or "")
        applied.append("negative_prompt")

    numeric_sampler_fields = {
        "steps": (20, 1, 150),
        "seed": (0, 0, 2**63 - 1),
    }
    for field, (default, minimum, maximum) in numeric_sampler_fields.items():
        if field in arguments and arguments.get(field) is not None:
            sampler_inputs[field] = _as_int(
                arguments.get(field), default, minimum=minimum, maximum=maximum
            )
            applied.append(field)
    if randomize_seed and "seed" not in applied:
        sampler_inputs["seed"] = random.randint(1, 2**48)
        applied.append("seed")
    if "cfg" in arguments and arguments.get("cfg") is not None:
        sampler_inputs["cfg"] = _as_float(arguments.get("cfg"), 7.0, minimum=0.1, maximum=30.0)
        applied.append("cfg")
    for field, input_name in (("sampler", "sampler_name"), ("scheduler", "scheduler")):
        if field in arguments:
            sampler_inputs[input_name] = str(arguments.get(field) or "")
            applied.append(field)
    for field in ("width", "height"):
        if field in arguments and arguments.get(field) is not None:
            latent_inputs[field] = _as_int(arguments.get(field), 1024, minimum=64, maximum=4096)
            applied.append(field)
    return candidate, applied


def regenerate(arguments: dict[str, Any]) -> dict[str, Any]:
    asset_id = _validate_asset_id(arguments.get("asset_id"))
    source_workflow = _asset_workflow(asset_id)
    if source_workflow is None:
        return sanitize(
            {
                "ok": False,
                "bridge": BRIDGE_ID,
                "action": "regenerate",
                "mode": "dry_run",
                "asset_id": asset_id,
                "submitted": False,
                "prompt_id": None,
                "error_code": "asset_provenance_unavailable",
                "warnings": ["asset_provenance_unavailable"],
                "next_steps": [
                    "Generate and resolve the asset in the current MCP server session before retrying."
                ],
            }
        )

    confirm_run = bool(arguments.get("confirm_run", False))
    workflow, applied = _regeneration_workflow(
        source_workflow, arguments, randomize_seed=confirm_run
    )
    validation = validate_workflow_payload(workflow, workflow_name="agent_regenerated_txt2img")
    validation_details = _validation_details(validation)
    base_result = {
        "bridge": BRIDGE_ID,
        "action": "regenerate",
        "asset_id": asset_id,
        "workflow_hash": workflow_hash(workflow),
        "overrides_applied": sorted(set(applied)),
        "validation_summary": {
            "ok": bool(validation.get("ok")),
            "warning_count": len(validation.get("warnings") or []),
            "error_count": len(validation_details.get("errors") or []),
        },
        "provenance": {
            "storage": "memory_only",
            "ttl_seconds": PROVENANCE_TTL_SECONDS,
            "persisted": False,
        },
    }
    if not validation.get("ok"):
        return sanitize(
            {
                **base_result,
                "ok": False,
                "mode": "confirmed" if confirm_run else "dry_run",
                "submitted": False,
                "prompt_id": None,
                "error_code": "regenerated_workflow_invalid",
                "warnings": ["regenerated_workflow_invalid"],
                "next_steps": ["Start a new reviewed generation instead of replaying this asset."],
            }
        )
    if not confirm_run:
        return sanitize(
            {
                **base_result,
                "ok": True,
                "mode": "dry_run",
                "submitted": False,
                "prompt_id": None,
                "job_status": {"state": "not_submitted"},
                "output_manifest": {"image_count": 0, "images": []},
                "warnings": ["Refusing to regenerate without confirm_run=true."],
                "next_steps": ["Review overrides, then call again with confirm_run=true."],
            }
        )

    base_url = _validate_loopback_url(str(arguments.get("comfy_url") or DEFAULT_BASE_URL))
    timeout = _as_int(arguments.get("timeout"), 30, minimum=1, maximum=300)
    wait_seconds = _as_int(arguments.get("wait_seconds"), 10, minimum=0, maximum=600)
    try:
        submission = submit_workflow(
            workflow, base_url=base_url, timeout=timeout, wait_seconds=wait_seconds
        )
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return sanitize(
            {
                **base_result,
                "ok": False,
                "mode": "confirmed",
                "submitted": False,
                "prompt_id": None,
                "error_code": "comfyui_unavailable",
                "job_status": {"state": "comfyui_unavailable"},
                "output_manifest": {"image_count": 0, "images": []},
                "warnings": ["comfyui_regeneration_submit_unavailable"],
                "next_steps": ["Start local ComfyUI and explicitly retry the regeneration."],
            }
        )

    prompt_id = str(submission.get("prompt_id") or "")
    job_status = submission.get("job_status")
    safe_job_status = job_status if isinstance(job_status, dict) else {}
    manifest = safe_job_status.get("output_manifest")
    output_manifest = manifest if isinstance(manifest, dict) else {"image_count": 0, "images": []}
    submission_ok = bool(submission.get("ok"))
    submitted = bool(submission.get("submitted", submission.get("prompt_id")))
    if submitted and prompt_id:
        _remember_generation(prompt_id, workflow)
        _remember_manifest_assets(prompt_id, output_manifest)
    state = str(safe_job_status.get("state") or "submitted")
    if state == "failed":
        warnings = ["comfyui_regeneration_execution_failed"]
        next_steps = [
            "Inspect the failing node locally, then review a new dry-run before explicitly retrying."
        ]
    elif state == "cancelled":
        warnings = ["comfyui_regeneration_execution_cancelled"]
        next_steps = [
            "Confirm the interruption was expected, then review a new dry-run before explicitly retrying."
        ]
    elif state == "status_unavailable":
        warnings = ["comfyui_regeneration_status_unavailable"]
        next_steps = [
            "Recover the same prompt_id with comfyui.generation_result before deciding whether to retry."
        ]
    elif submitted and state in {"submitted", "queued_or_running"}:
        warnings = ["comfyui_regeneration_pending"]
        next_steps = [
            "Call comfyui.generation_result with the same prompt_id; do not resubmit automatically."
        ]
    elif submission_ok:
        warnings = []
        next_steps = ["Review the regenerated output locally."]
    else:
        warnings = ["comfyui_regeneration_submit_failed"]
        next_steps = ["Inspect the local ComfyUI response before explicitly retrying."]
    return sanitize(
        {
            **base_result,
            "ok": submission_ok,
            "mode": "confirmed",
            "submitted": submitted,
            "prompt_id": prompt_id or None,
            "error_code": None if submission_ok else submission.get("error"),
            "job_status": {
                key: value for key, value in safe_job_status.items() if key != "output_manifest"
            },
            "output_manifest": output_manifest,
            "warnings": warnings,
            "next_steps": next_steps,
        }
    )


def submit_workflow(
    workflow: dict[str, Any],
    *,
    base_url: str,
    timeout: int,
    wait_seconds: int,
) -> dict[str, Any]:
    response = post_json(base_url, "/prompt", {"prompt": workflow}, timeout)
    prompt_id = str(response.get("prompt_id") or "")
    if not prompt_id:
        return {
            "ok": False,
            "submitted": False,
            "error": "missing_prompt_id",
            "response": response,
        }

    status = {
        "state": "submitted",
        "history_available": False,
        "output_manifest": {"prompt_id": prompt_id, "image_count": 0, "images": []},
    }
    deadline = time.time() + max(0, wait_seconds)
    while time.time() <= deadline:
        try:
            status = query_job_status(base_url, prompt_id, timeout)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            ValueError,
        ):
            return {
                "ok": False,
                "submitted": True,
                "prompt_id": prompt_id,
                "error": "comfyui_status_unavailable",
                "job_status": {
                    "state": "status_unavailable",
                    "history_available": False,
                    "output_manifest": {
                        "prompt_id": prompt_id,
                        "image_count": 0,
                        "images": [],
                    },
                },
            }
        if status["state"] in {"completed", "failed", "cancelled", "status_unavailable"}:
            break
        if wait_seconds <= 0:
            break
        time.sleep(1)

    state = str(status.get("state") or "")
    error_codes = {
        "failed": "comfyui_execution_failed",
        "cancelled": "comfyui_execution_cancelled",
        "status_unavailable": "comfyui_status_unavailable",
    }
    result = {
        "ok": state == "completed",
        "submitted": True,
        "prompt_id": prompt_id,
        "job_status": status,
    }
    if state in error_codes:
        result["error"] = error_codes[state]
    return result


def agent_run(arguments: dict[str, Any]) -> dict[str, Any]:
    plan = workflow_build_plan(arguments)
    workflow_type = _workflow_type(arguments)
    if workflow_type not in BUILDABLE_WORKFLOW_TYPES:
        return sanitize(
            {
                "ok": True,
                "bridge": BRIDGE_ID,
                "action": "agent_run",
                "mode": "dry_run",
                "workflow_type": workflow_type,
                "task_type": workflow_type,
                "build_plan": plan,
                "submitted": False,
                "prompt_id": None,
                "job_status": {"state": "not_submitted"},
                "output_manifest": {"image_count": 0, "images": []},
                "warnings": [
                    f"{workflow_type} is plan-only; refusing to build or submit a queue job."
                ],
                "next_steps": [
                    "Review the dry-run plan and add a safe public workflow template before enabling real runs."
                ],
            }
        )
    run_arguments = dict(arguments)
    if bool(run_arguments.get("confirm_run", False)) and run_arguments.get("seed") is None:
        run_arguments["_random_seed"] = True
    workflow = build_txt2img_workflow(run_arguments)
    validation = validate_workflow_payload(workflow, workflow_name="agent_generated_txt2img")
    repaired = None
    if not validation.get("ok"):
        repaired_result = workflow_repair({**arguments, "workflow": workflow})
        repaired = {
            "workflow_hash": repaired_result["workflow_hash"],
            "node_summary": repaired_result["node_summary"],
            "repairs": repaired_result["repairs"],
            "validation": repaired_result["validation"],
        }
        workflow = repaired_result["workflow"]
        validation = repaired_result["validation"]

    confirm_run = bool(arguments.get("confirm_run", False))
    if not confirm_run:
        return sanitize(
            {
                "ok": True,
                "bridge": BRIDGE_ID,
                "action": "agent_run",
                "mode": "dry_run",
                "workflow_type": _workflow_type(arguments),
                "build_plan": plan,
                "workflow_hash": workflow_hash(workflow),
                "node_summary": workflow_summary(workflow),
                "validation": validation,
                "repaired": repaired is not None,
                "submitted": False,
                "prompt_id": None,
                "job_status": {"state": "not_submitted"},
                "output_manifest": {"image_count": 0, "images": []},
                "warnings": ["Refusing to submit to ComfyUI without confirm_run=true."],
                "next_steps": [
                    "Call again with confirm_run=true after reviewing the dry-run plan."
                ],
            }
        )

    if not validation.get("ok"):
        return sanitize(
            {
                "ok": False,
                "bridge": BRIDGE_ID,
                "action": "agent_run",
                "mode": "confirmed",
                "workflow_type": _workflow_type(arguments),
                "submitted": False,
                "prompt_id": None,
                "validation": validation,
                "warnings": ["Workflow validation failed after repair; refusing to submit."],
                "next_steps": [
                    "Inspect validation errors and call workflow_repair with explicit parameters."
                ],
            }
        )

    base_url = _validate_loopback_url(str(arguments.get("comfy_url") or DEFAULT_BASE_URL))
    timeout = _as_int(arguments.get("timeout"), 30, minimum=1, maximum=300)
    wait_seconds = _as_int(
        arguments.get("wait_seconds", arguments.get("timeout_seconds")), 10, minimum=0, maximum=600
    )
    try:
        submission = submit_workflow(
            workflow, base_url=base_url, timeout=timeout, wait_seconds=wait_seconds
        )
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return sanitize(
            {
                "ok": False,
                "bridge": BRIDGE_ID,
                "action": "agent_run",
                "mode": "confirmed",
                "workflow_type": _workflow_type(arguments),
                "submitted": False,
                "prompt_id": None,
                "workflow_hash": workflow_hash(workflow),
                "job_status": {"state": "comfyui_unavailable"},
                "output_manifest": {"image_count": 0, "images": []},
                "warnings": ["Unable to submit to local ComfyUI."],
                "next_steps": [
                    "Start local ComfyUI, confirm the checkpoint placeholder is valid, then retry."
                ],
            }
        )

    job_status = submission.get("job_status", {})
    submission_ok = bool(submission.get("ok"))
    submitted = bool(submission.get("submitted", submission.get("prompt_id")))
    prompt_id = str(submission.get("prompt_id") or "")
    output_manifest = job_status.get("output_manifest", {"image_count": 0, "images": []})
    if submitted and prompt_id:
        _remember_generation(prompt_id, workflow)
        if isinstance(output_manifest, dict):
            _remember_manifest_assets(prompt_id, output_manifest)
    state = str(job_status.get("state") or "")
    if state == "failed":
        warnings = [
            "ComfyUI accepted the workflow, but execution failed; no successful result is claimed."
        ]
        next_steps = [
            "Inspect the failing node in local ComfyUI, repair the workflow or runtime issue, then review a new dry-run before retrying with confirm_run=true."
        ]
    elif state == "cancelled":
        warnings = [
            "ComfyUI accepted the workflow, but execution was cancelled or interrupted; no successful result is claimed."
        ]
        next_steps = [
            "Confirm the interruption was expected, then review a new dry-run before retrying with confirm_run=true."
        ]
    elif state == "status_unavailable":
        warnings = [
            "ComfyUI accepted the workflow, but the post-submit status check was unavailable; completion is unverified."
        ]
        next_steps = [
            "Recover status with the same prompt_id via comfyui.job_snapshot or local queue/history before deciding whether to retry."
        ]
    elif state in {"submitted", "queued_or_running"}:
        warnings = [
            "ComfyUI accepted the workflow, but it did not reach verified completion within the wait window; no successful result is claimed."
        ]
        next_steps = [
            "Continue monitoring the same prompt_id via comfyui.progress_monitor or comfyui.job_snapshot; do not resubmit automatically."
        ]
    elif submission_ok:
        warnings = []
        next_steps = []
    else:
        warnings = [str(submission.get("error") or "ComfyUI submission failed.")]
        next_steps = ["Inspect the ComfyUI response and local console."]
    return sanitize(
        {
            "ok": submission_ok,
            "bridge": BRIDGE_ID,
            "action": "agent_run",
            "mode": "confirmed",
            "workflow_type": _workflow_type(arguments),
            "submitted": submitted,
            "prompt_id": prompt_id or None,
            "workflow_hash": workflow_hash(workflow),
            "node_summary": workflow_summary(workflow),
            "validation": validation,
            "job_status": {
                key: value for key, value in job_status.items() if key != "output_manifest"
            },
            "output_manifest": output_manifest,
            "warnings": warnings,
            "next_steps": next_steps,
        }
    )
