from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any

from examples.comfy_bridge.validate_workflow import validate_workflow_payload
from starbridge_mcp.core.security import sanitize


BRIDGE_ID = "comfyui"
DEFAULT_BASE_URL = os.environ.get("STARBRIDGE_COMFYUI_URL") or os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")
DEFAULT_CHECKPOINT = os.environ.get("STARBRIDGE_COMFYUI_CHECKPOINT", "__checkpoint_name_required__")
PLACEHOLDER_CHECKPOINT = "__checkpoint_placeholder__"
PLACEHOLDER_UPSCALE_MODEL = "__upscale_model_placeholder__"
PLACEHOLDER_SOURCE_IMAGE = "__source_image_placeholder__"
PLACEHOLDER_MASK_IMAGE = "__mask_image_placeholder__"
DEFAULT_NEGATIVE_PROMPT = "low quality, blurry, distorted, bad anatomy, watermark, text"
SUPPORTED_WORKFLOW_TYPES = {"txt2img", "img2img", "inpaint", "upscale"}
BUILDABLE_WORKFLOW_TYPES = {"txt2img"}
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
        "input_requirements": ["positive_prompt or goal", "checkpoint placeholder", "width", "height", "sampler settings"],
        "workflow_requirements": TXT2IMG_REQUIRED_NODES,
        "expected_outputs": ["API-format workflow JSON", "workflow_hash", "validation report", "no submitted ComfyUI job"],
    },
    "img2img": {
        "input_requirements": ["source_image_path supplied by user at run time", "positive_prompt or goal", "checkpoint placeholder", "denoise"],
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
        "expected_outputs": ["dry-run execution plan", "required node checklist", "blocked real queue submission"],
    },
    "inpaint": {
        "input_requirements": ["source_image_path supplied by user at run time", "mask_image_path supplied by user at run time", "positive_prompt or goal", "checkpoint placeholder"],
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
        "expected_outputs": ["dry-run execution plan", "mask requirements", "blocked real queue submission"],
    },
    "upscale": {
        "input_requirements": ["source_image_path supplied by user at run time", "upscale_model placeholder or built-in method", "scale factor"],
        "workflow_requirements": ["LoadImage", "UpscaleModelLoader or ImageScale", "ImageUpscaleWithModel or ImageScale", "SaveImage"],
        "expected_outputs": ["dry-run execution plan", "upscale requirement checklist", "blocked real queue submission"],
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
    return str(arguments.get("checkpoint") or arguments.get("ckpt_name") or DEFAULT_CHECKPOINT).strip()


def _draft_checkpoint(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("checkpoint") or arguments.get("ckpt_name") or arguments.get("model_name") or PLACEHOLDER_CHECKPOINT).strip()
    lowered = value.lower()
    if "\\" in value or "/" in value or lowered.endswith((".safetensors", ".ckpt", ".pt", ".pth")):
        return PLACEHOLDER_CHECKPOINT
    return value or PLACEHOLDER_CHECKPOINT


def _draft_task_type(arguments: dict[str, Any]) -> str:
    requested = str(arguments.get("task_type") or arguments.get("workflow_type") or "txt2img").strip().lower()
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
        "class_type": "StarBridgeDraftMetadata",
        "inputs": {
            "task_type": task_type,
            "status": "draft",
            "draft": True,
            "safe_placeholder": True,
            "production_ready": False,
            "queue_submission": "disabled",
            "model_policy": "placeholder_only",
            "asset_policy": "placeholder_only_no_private_files",
            "note": "Generated by StarBridge workflow_draft; review and replace placeholders locally before any real ComfyUI run.",
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
            links += sum(1 for value in inputs.values() if isinstance(value, list) and len(value) == 2)
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


def workflow_build_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow_type = _workflow_type(arguments)
    width, height = _dimensions(arguments)
    task_requirements = TASK_PLAN_REQUIREMENTS[workflow_type]
    blocked_reasons = []
    if workflow_type not in BUILDABLE_WORKFLOW_TYPES:
        blocked_reasons.append(f"{workflow_type} is plan-only in this repository; real ComfyUI queue submission is not implemented.")
    if workflow_type in {"img2img", "inpaint", "upscale"}:
        blocked_reasons.append("Private input images must be supplied only during an explicit local run and must not be committed.")
    if workflow_type == "inpaint":
        blocked_reasons.append("Mask files are private local inputs and are not read by this dry-run planner.")
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
            "warnings": [] if workflow_type in BUILDABLE_WORKFLOW_TYPES else [f"{workflow_type} is available as dry-run plan only."],
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
            "inputs": {"filename_prefix": str(arguments.get("filename_prefix") or "starbridge_agent_txt2img"), "images": ["8", 0]},
        },
    }


def build_txt2img_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    width, height = _dimensions(arguments)
    sampler = _draft_sampler_settings(arguments, denoise=1.0)
    return {
        "1": _draft_metadata("txt2img"),
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _draft_checkpoint(arguments)}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
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
        "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "starbridge_txt2img_draft", "images": ["7", 0]}},
    }


def build_img2img_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    sampler = _draft_sampler_settings(arguments, denoise=0.55)
    return {
        "1": _draft_metadata("img2img"),
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _draft_checkpoint(arguments)}},
        "3": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["3", 0], "vae": ["2", 2]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]}},
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
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "starbridge_img2img_draft", "images": ["8", 0]}},
    }


def build_inpaint_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    sampler = _draft_sampler_settings(arguments, denoise=0.8)
    return {
        "1": _draft_metadata("inpaint"),
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _draft_checkpoint(arguments)}},
        "3": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "4": {"class_type": "LoadImageMask", "inputs": {"image": PLACEHOLDER_MASK_IMAGE, "channel": "alpha"}},
        "5": {"class_type": "VAEEncodeForInpaint", "inputs": {"pixels": ["3", 0], "vae": ["2", 2], "mask": ["4", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": _positive_prompt(arguments), "clip": ["2", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": _negative_prompt(arguments), "clip": ["2", 1]}},
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
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": "starbridge_inpaint_draft", "images": ["9", 0]}},
    }


def build_upscale_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    scale_by = _as_float(arguments.get("scale_by"), 2.0, minimum=1.0, maximum=8.0)
    return {
        "1": _draft_metadata("upscale"),
        "2": _load_image_node(PLACEHOLDER_SOURCE_IMAGE),
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": PLACEHOLDER_UPSCALE_MODEL}},
        "4": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        "5": {"class_type": "ImageScale", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "scale_by": scale_by}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": _positive_prompt(arguments), "clip": ["7", 1]}},
        "7": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _draft_checkpoint(arguments)}},
        "8": {"class_type": "SaveImage", "inputs": {"filename_prefix": "starbridge_upscale_draft", "images": ["5", 0]}},
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
    return {node_id: {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _draft_checkpoint(arguments)}}}


def module_positive_prompt_encode(node_id: str, checkpoint_node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {node_id: {"class_type": "CLIPTextEncode", "inputs": {"text": _positive_prompt(arguments), "clip": [checkpoint_node_id, 1]}}}


def module_negative_prompt_encode(node_id: str, checkpoint_node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {node_id: {"class_type": "CLIPTextEncode", "inputs": {"text": _negative_prompt(arguments), "clip": [checkpoint_node_id, 1]}}}


def module_empty_latent_image(node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    width, height = _dimensions(arguments)
    return {node_id: {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}}


def module_load_image_placeholder(node_id: str) -> dict[str, Any]:
    return {node_id: _load_image_node(PLACEHOLDER_SOURCE_IMAGE)}


def module_vae_encode_placeholder(node_id: str, image_node_id: str, checkpoint_node_id: str, mask_node_id: str | None = None) -> dict[str, Any]:
    if mask_node_id:
        return {
            node_id: {
                "class_type": "VAEEncodeForInpaint",
                "inputs": {"pixels": [image_node_id, 0], "vae": [checkpoint_node_id, 2], "mask": [mask_node_id, 0]},
            }
        }
    return {node_id: {"class_type": "VAEEncode", "inputs": {"pixels": [image_node_id, 0], "vae": [checkpoint_node_id, 2]}}}


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


def module_vae_decode(node_id: str, sampler_node_id: str, checkpoint_node_id: str) -> dict[str, Any]:
    return {node_id: {"class_type": "VAEDecode", "inputs": {"samples": [sampler_node_id, 0], "vae": [checkpoint_node_id, 2]}}}


def module_save_image_placeholder(node_id: str, image_node_id: str, filename_prefix: str) -> dict[str, Any]:
    return {node_id: {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": [image_node_id, 0]}}}


def module_upscale_placeholder(model_node_id: str, upscale_node_id: str, scale_node_id: str, image_node_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    scale_by = _as_float(arguments.get("scale") if "scale" in arguments else arguments.get("scale_by"), 2.0, minimum=1.0, maximum=8.0)
    return {
        model_node_id: {"class_type": "UpscaleModelLoader", "inputs": {"model_name": PLACEHOLDER_UPSCALE_MODEL}},
        upscale_node_id: {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": [model_node_id, 0], "image": [image_node_id, 0]}},
        scale_node_id: {"class_type": "ImageScale", "inputs": {"image": [upscale_node_id, 0], "upscale_method": "lanczos", "scale_by": scale_by}},
    }


def module_inpaint_mask_placeholder(node_id: str) -> dict[str, Any]:
    return {node_id: {"class_type": "LoadImageMask", "inputs": {"image": PLACEHOLDER_MASK_IMAGE, "channel": "alpha"}}}


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
        warnings.append("Draft validation failed; inspect validation_report before using this workflow locally.")
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
                "warnings": [f"{workflow_type} workflow build is not implemented; only dry-run planning is supported."],
                "next_steps": ["Use comfyui.workflow_build_plan for this task type until a reviewed safe workflow template exists."],
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
            "next_steps": ["Review the workflow, then call comfyui.agent_run with confirm_run=true to submit."],
        }
    )


def _find_nodes(workflow: dict[str, Any], class_type: str) -> list[str]:
    return [node_id for node_id, node in workflow.items() if isinstance(node, dict) and node.get("class_type") == class_type]


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
    repaired["5"]["inputs"]["width"], repaired["5"]["inputs"]["height"] = _dimensions(repaired["5"].get("inputs", {}))
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
    with urllib.request.urlopen(_url(base_url, path), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(base_url, path),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def output_manifest_from_history(prompt_id: str, history: dict[str, Any]) -> dict[str, Any]:
    prompt_history = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    outputs = []
    for node_id, node_output in prompt_history.get("outputs", {}).items():
        for image in node_output.get("images", []):
            outputs.append(
                {
                    "node_id": str(node_id),
                    "filename": str(image.get("filename") or ""),
                    "subfolder": str(image.get("subfolder") or ""),
                    "type": str(image.get("type") or "output"),
                }
            )
    return sanitize({"prompt_id": prompt_id, "image_count": len(outputs), "images": outputs})


def query_job_status(base_url: str, prompt_id: str, timeout: int) -> dict[str, Any]:
    history = get_json(base_url, f"/history/{prompt_id}", timeout)
    if prompt_id in history:
        return {
            "state": "completed",
            "history_available": True,
            "output_manifest": output_manifest_from_history(prompt_id, history),
        }
    return {"state": "queued_or_running", "history_available": False, "output_manifest": {"prompt_id": prompt_id, "image_count": 0, "images": []}}


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
        return {"ok": False, "error": "missing_prompt_id", "response": response}

    status = {"state": "submitted", "history_available": False, "output_manifest": {"prompt_id": prompt_id, "image_count": 0, "images": []}}
    deadline = time.time() + max(0, wait_seconds)
    while time.time() <= deadline:
        status = query_job_status(base_url, prompt_id, timeout)
        if status["state"] == "completed":
            break
        if wait_seconds <= 0:
            break
        time.sleep(1)
    return {"ok": True, "prompt_id": prompt_id, "job_status": status}


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
                "warnings": [f"{workflow_type} is plan-only; refusing to build or submit a queue job."],
                "next_steps": ["Review the dry-run plan and add a safe public workflow template before enabling real runs."],
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
                "next_steps": ["Call again with confirm_run=true after reviewing the dry-run plan."],
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
                "next_steps": ["Inspect validation errors and call workflow_repair with explicit parameters."],
            }
        )

    base_url = str(arguments.get("comfy_url") or DEFAULT_BASE_URL)
    timeout = _as_int(arguments.get("timeout"), 30, minimum=1, maximum=300)
    wait_seconds = _as_int(arguments.get("wait_seconds", arguments.get("timeout_seconds")), 10, minimum=0, maximum=600)
    try:
        submission = submit_workflow(workflow, base_url=base_url, timeout=timeout, wait_seconds=wait_seconds)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
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
                "warnings": [f"Unable to submit to ComfyUI: {exc}"],
                "next_steps": ["Start local ComfyUI, confirm the checkpoint placeholder is valid, then retry."],
            }
        )

    job_status = submission.get("job_status", {})
    return sanitize(
        {
            "ok": bool(submission.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "agent_run",
            "mode": "confirmed",
            "workflow_type": _workflow_type(arguments),
            "submitted": bool(submission.get("ok")),
            "prompt_id": submission.get("prompt_id"),
            "workflow_hash": workflow_hash(workflow),
            "node_summary": workflow_summary(workflow),
            "validation": validation,
            "job_status": {key: value for key, value in job_status.items() if key != "output_manifest"},
            "output_manifest": job_status.get("output_manifest", {"image_count": 0, "images": []}),
            "warnings": [] if submission.get("ok") else [str(submission.get("error") or "ComfyUI submission failed.")],
            "next_steps": [] if submission.get("ok") else ["Inspect the ComfyUI response and local console."],
        }
    )
