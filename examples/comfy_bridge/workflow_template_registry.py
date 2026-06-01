from __future__ import annotations

import copy
import functools
import getpass
import json
import os
from pathlib import Path
from typing import Any

from examples.comfy_bridge.validate_workflow import validate_workflow_payload
from examples.comfy_bridge.workflow_agent import (
    RECOGNIZED_COMPOSER_MODULES,
    SUPPORTED_WORKFLOW_TYPES,
    workflow_compose,
    workflow_hash,
    workflow_summary,
)
from starbridge_mcp.core.security import sanitize


BRIDGE_ID = "comfyui"
REGISTRY_PATH = Path(__file__).resolve().parent / "templates" / "workflow_template_registry.json"
REQUIRED_TEMPLATE_FIELDS = {
    "template_id",
    "version",
    "task_type",
    "required_modules",
    "optional_modules",
    "required_inputs",
    "safe_placeholder_policy",
    "validation_status",
    "safety_level",
    "notes",
}
VALIDATION_STATUSES = {"draft_validated", "composed_validated", "needs_review"}
SAFE_TEMPLATE_SAFETY_LEVELS = {"safe_read_only", "safe_placeholder_only"}
TASK_REQUIRED_INPUTS: dict[str, set[str]] = {
    "txt2img": {"prompt", "negative_prompt", "width", "height", "seed", "steps", "cfg", "sampler", "scheduler"},
    "img2img": {"prompt", "negative_prompt", "source_image_placeholder", "denoise", "seed", "steps", "cfg"},
    "inpaint": {"prompt", "negative_prompt", "source_image_placeholder", "mask_image_placeholder", "denoise", "seed", "steps", "cfg"},
    "upscale": {"source_image_placeholder", "scale_by", "upscale_model_placeholder"},
    "complex_creative_poster": {"prompt", "negative_prompt", "width", "height", "seed", "steps", "cfg", "sampler", "scheduler"},
}
TEMPLATE_TASK_TO_COMPOSER_TASK = {
    "txt2img": "txt2img",
    "img2img": "img2img",
    "inpaint": "inpaint",
    "upscale": "upscale",
    "complex_creative_poster": "txt2img",
}


def _private_usernames() -> set[str]:
    values = {
        os.environ.get("USERNAME", ""),
        os.environ.get("USER", ""),
        getpass.getuser() if hasattr(getpass, "getuser") else "",
    }
    return {value for value in values if value and value.lower() not in {"user", "runner", "root"}}


def _forbidden_patterns() -> list[tuple[str, str]]:
    return [
        ("windows_user_path", "C:" + "\\Users"),
        ("appdata", "AppData"),
        ("comfyui_models", "ComfyUI" + "\\models"),
        ("comfyui_output", "ComfyUI" + "\\output"),
        ("checkpoint_extension_safetensors", ".safetensors"),
        ("checkpoint_extension_ckpt", ".ckpt"),
        *[("real_username", username) for username in _private_usernames()],
    ]


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_walk_strings(key))
            strings.extend(_walk_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_walk_strings(item))
        return strings
    return []


@functools.lru_cache(maxsize=1)
def _load_registry_payload() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _registry_templates() -> list[dict[str, Any]]:
    payload = _load_registry_payload()
    templates = payload.get("templates", [])
    if not isinstance(templates, list):
        return []
    return [copy.deepcopy(template) for template in templates if isinstance(template, dict)]


def validate_workflow_template(template: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(template, dict):
        return sanitize({"ok": False, "errors": ["template must be a JSON object"], "warnings": []})

    missing_fields = sorted(REQUIRED_TEMPLATE_FIELDS - set(template))
    if missing_fields:
        errors.append(f"missing required template fields: {', '.join(missing_fields)}")

    template_id = str(template.get("template_id") or "").strip()
    task_type = str(template.get("task_type") or "").strip()
    version = str(template.get("version") or "").strip()
    validation_status = str(template.get("validation_status") or "").strip()
    safety_level = str(template.get("safety_level") or "").strip()
    required_modules = template.get("required_modules")
    optional_modules = template.get("optional_modules")
    required_inputs = template.get("required_inputs")

    if not template_id:
        errors.append("template_id is required")
    if not version:
        errors.append("version is required")
    if task_type not in TASK_REQUIRED_INPUTS:
        errors.append(f"unsupported template task_type: {task_type}")
    if validation_status not in VALIDATION_STATUSES:
        errors.append("validation_status must be draft_validated, composed_validated, or needs_review")
    if safety_level not in SAFE_TEMPLATE_SAFETY_LEVELS:
        errors.append("safety_level must be safe_read_only or safe_placeholder_only")

    if not isinstance(required_modules, list) or not required_modules:
        errors.append("required_modules must be a non-empty list")
    else:
        unknown_modules = sorted(set(map(str, required_modules)) - RECOGNIZED_COMPOSER_MODULES)
        if unknown_modules:
            errors.append(f"required_modules are not recognized by composer: {', '.join(unknown_modules)}")

    if not isinstance(optional_modules, list):
        errors.append("optional_modules must be a list")
    else:
        unknown_optional = sorted(set(map(str, optional_modules)) - RECOGNIZED_COMPOSER_MODULES)
        if unknown_optional:
            errors.append(f"optional_modules are not recognized by composer: {', '.join(unknown_optional)}")

    if not isinstance(required_inputs, list) or not required_inputs:
        errors.append("required_inputs must be a non-empty list")
    elif task_type in TASK_REQUIRED_INPUTS:
        missing_inputs = sorted(TASK_REQUIRED_INPUTS[task_type] - set(map(str, required_inputs)))
        if missing_inputs:
            errors.append(f"required_inputs missing expected entries: {', '.join(missing_inputs)}")

    text_values = _walk_strings(template)
    for label, pattern in _forbidden_patterns():
        if pattern and any(pattern.lower() in text.lower() for text in text_values):
            errors.append(f"forbidden pattern detected: {label}")

    policy = template.get("safe_placeholder_policy")
    if not isinstance(policy, dict):
        errors.append("safe_placeholder_policy must be an object")
    else:
        if policy.get("model_policy") != "placeholder_only":
            errors.append("safe_placeholder_policy.model_policy must be placeholder_only")
        if policy.get("asset_policy") != "placeholder_only_no_private_files":
            errors.append("safe_placeholder_policy.asset_policy must be placeholder_only_no_private_files")
        if policy.get("queue_submission") != "disabled":
            errors.append("safe_placeholder_policy.queue_submission must be disabled")
        if policy.get("network") != "disabled":
            errors.append("safe_placeholder_policy.network must be disabled")
        if policy.get("filesystem") != "no_private_files":
            errors.append("safe_placeholder_policy.filesystem must be no_private_files")

    return sanitize(
        {
            "ok": not errors,
            "template_id": template_id,
            "task_type": task_type,
            "validation_status": validation_status,
            "errors": errors,
            "warnings": warnings,
        }
    )


def validate_workflow_template_registry() -> dict[str, Any]:
    templates = _registry_templates()
    errors: list[str] = []
    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    template_reports = []
    for template in templates:
        template_id = str(template.get("template_id") or "").strip()
        if template_id in seen:
            duplicate_ids.add(template_id)
        seen.add(template_id)
        report = validate_workflow_template(template)
        template_reports.append(report)
        errors.extend(f"{template_id}: {error}" for error in report.get("errors", []))
    if duplicate_ids:
        errors.append(f"duplicate template_id values: {', '.join(sorted(duplicate_ids))}")
    return sanitize(
        {
            "ok": not errors,
            "bridge": BRIDGE_ID,
            "action": "workflow_template_registry_validate",
            "template_count": len(templates),
            "template_ids": [str(template.get("template_id") or "") for template in templates],
            "errors": errors,
            "templates": template_reports,
        }
    )


def list_workflow_templates() -> dict[str, Any]:
    templates = _registry_templates()
    registry_validation = validate_workflow_template_registry()
    return sanitize(
        {
            "ok": bool(registry_validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_template_list",
            "mode": "safe_read_only",
            "template_count": len(templates),
            "templates": [
                {
                    "template_id": template.get("template_id"),
                    "version": template.get("version"),
                    "task_type": template.get("task_type"),
                    "validation_status": template.get("validation_status"),
                    "safety_level": template.get("safety_level"),
                    "notes": template.get("notes"),
                }
                for template in templates
            ],
            "registry_validation": registry_validation,
            "safety_notes": [
                "Registry list reads only the bundled public template registry.",
                "No private filesystem paths, network requests, model discovery, output inspection, or queue submission are performed.",
            ],
        }
    )


def get_workflow_template(template_id: str) -> dict[str, Any]:
    requested_id = str(template_id or "").strip()
    templates = _registry_templates()
    for template in templates:
        if template.get("template_id") == requested_id:
            report = validate_workflow_template(template)
            return sanitize(
                {
                    "ok": bool(report.get("ok")),
                    "bridge": BRIDGE_ID,
                    "action": "workflow_template_get",
                    "mode": "safe_read_only",
                    "template": template,
                    "template_validation": report,
                    "safety_notes": [
                        "Template uses placeholders only.",
                        "No private filesystem paths, network requests, model discovery, output inspection, or queue submission are performed.",
                    ],
                }
            )
    return sanitize(
        {
            "ok": False,
            "bridge": BRIDGE_ID,
            "action": "workflow_template_get",
            "mode": "safe_read_only",
            "template_id": requested_id,
            "error": "template_not_found",
        }
    )


def compose_from_template(template_id: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = dict(arguments or {})
    template_result = get_workflow_template(template_id)
    template = template_result.get("template")
    if not template_result.get("ok") or not isinstance(template, dict):
        return template_result

    task_type = str(template.get("task_type") or "")
    composer_task_type = TEMPLATE_TASK_TO_COMPOSER_TASK.get(task_type, "txt2img")
    compose_arguments = {
        **arguments,
        "task_type": composer_task_type,
    }
    if task_type == "complex_creative_poster":
        compose_arguments.setdefault("prompt", "public creative poster concept, bold central composition, layered typography areas, product-safe placeholder scene")
        compose_arguments.setdefault("negative_prompt", "private logo, real person, customer material, watermark, low quality")
        compose_arguments.setdefault("width", 1024)
        compose_arguments.setdefault("height", 1536)
        compose_arguments.setdefault("seed", 246813579)
        compose_arguments.setdefault("steps", 24)
        compose_arguments.setdefault("cfg", 7.5)

    composed = workflow_compose(compose_arguments)
    workflow = composed.get("workflow")
    validation = validate_workflow_payload(workflow, workflow_name=f"{template_id}_from_template") if isinstance(workflow, dict) else composed.get("validation_report", {})
    return sanitize(
        {
            "ok": bool(composed.get("ok")) and bool(validation.get("ok")),
            "bridge": BRIDGE_ID,
            "action": "workflow_from_template",
            "mode": "safe_read_only",
            "template_id": template.get("template_id"),
            "template_version": template.get("version"),
            "task_type": task_type,
            "composer_task_type": composer_task_type,
            "valid": bool(validation.get("ok")),
            "workflow": workflow,
            "workflow_hash": workflow_hash(workflow) if isinstance(workflow, dict) else None,
            "node_summary": workflow_summary(workflow) if isinstance(workflow, dict) else {},
            "template_validation": template_result.get("template_validation"),
            "validation_report": validation,
            "warnings": list(composed.get("warnings") or []),
            "safety_notes": [
                "Generated from bundled public template metadata and safe placeholder composer modules.",
                "No private filesystem paths, network requests, model discovery, output inspection, or queue submission are performed.",
                "The returned workflow is not production-ready and must remain placeholder-only until a separate explicit local run review.",
            ],
            "next_steps": [
                "Review the workflow and validation report.",
                "Run workflow_validate again after any manual edits.",
                "Do not submit to ComfyUI queue in this registry flow.",
            ],
        }
    )
