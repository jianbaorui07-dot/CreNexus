from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

CAPABILITY_CATEGORIES: dict[str, dict[str, Any]] = {
    "session": {"status": "implemented", "tools": ["ps.probe", "ps.get_state", "ps.get_preview"]},
    "document": {"status": "implemented", "tools": ["ps.document.info"]},
    "layers": {"status": "implemented", "tools": ["ps.layers.list", "ps.batchplay.validate"]},
    "selection_mask": {
        "status": "planned",
        "tools": ["ps.selection.subject", "ps.mask.refine"],
    },
    "adjustments": {
        "status": "experimental",
        "tools": ["ps.batchplay.execute_confirmed", "ps.camera_raw.tune"],
    },
    "smart_objects": {"status": "planned", "tools": ["ps.smartobject.place"]},
    "text": {"status": "planned", "tools": ["ps.text.edit"]},
    "history": {"status": "planned", "tools": ["ps.history.undo"]},
    "export": {"status": "implemented", "tools": ["ps.preview.export"]},
    "managed_production": {
        "status": "implemented",
        "workflow_id": "photoshop-production-v1",
        "features": [
            "managed_source_hash",
            "duplicate_before_write",
            "canvas_resize",
            "brightness_contrast_saturation",
            "subject_export",
            "png_jpeg_psd_export",
            "staged_output_promotion",
            "artifact_hash_verification",
            "native_psd_reopen_validation",
        ],
    },
    "semantic_layers": {
        "status": "implemented",
        "entrypoint": "python -m starbridge_mcp.adapters.photoshop.semantic_layers.cli",
        "features": ["content_hash_cache", "batch_resume", "review_patch", "psd_builder"],
    },
}


RECIPE_LIBRARY: dict[str, dict[str, Any]] = {
    "simple-tone-export-v1": {
        "title": "Simple tone and export",
        "complexity": "simple",
        "required_parameters": [],
        "steps": [
            ("validate-source", "workflow:photoshop-production-v1", False, "managed_production"),
            ("probe-session", "workflow:photoshop-production-v1", False, "managed_production"),
            ("inspect-session", "workflow:photoshop-production-v1", False, "managed_production"),
            ("execute-production", "workflow:photoshop-production-v1", True, "managed_production"),
            ("verify-output", "workflow:photoshop-production-v1", False, "managed_production"),
        ],
        "quality_gates": [
            "sandbox_copy",
            "preview_readback",
            "artifact_hash",
            "native_reopen_if_psd_requested",
        ],
        "execution_entrypoint": "workflow:photoshop-production-v1",
    },
    "production-subject-delivery-v1": {
        "title": "Managed subject extraction and multi-format delivery",
        "complexity": "advanced",
        "required_parameters": ["source_asset_id"],
        "steps": [
            ("validate-source", "workflow:photoshop-production-v1", False, "managed_production"),
            ("probe-session", "workflow:photoshop-production-v1", False, "managed_production"),
            ("inspect-session", "workflow:photoshop-production-v1", False, "managed_production"),
            ("execute-production", "workflow:photoshop-production-v1", True, "managed_production"),
            ("verify-output", "workflow:photoshop-production-v1", False, "managed_production"),
            ("review-result", "workflow:photoshop-production-v1", True, "managed_production"),
        ],
        "quality_gates": [
            "managed_source_hash",
            "sandbox_copy",
            "subject_artifact",
            "multi_format_artifacts",
            "artifact_hash",
            "user_review",
        ],
        "execution_entrypoint": "workflow:photoshop-production-v1",
        "fixed_parameters": {"export_subject": True},
    },
    "batch-production-delivery-v1": {
        "title": "Resumable managed Photoshop production batch",
        "complexity": "batch",
        "required_parameters": ["source_asset_id"],
        "steps": [
            ("queue-managed-job", "workflow:photoshop-production-v1", False, "managed_production"),
            ("execute-production", "workflow:photoshop-production-v1", True, "managed_production"),
            ("verify-output", "workflow:photoshop-production-v1", False, "managed_production"),
        ],
        "quality_gates": [
            "managed_source_hash",
            "per_item_hash",
            "source_not_overwritten",
            "checkpoint_commit",
        ],
        "execution_entrypoint": "workflow:photoshop-production-v1",
    },
    "product-composite-verified-v1": {
        "title": "Verified product composite",
        "complexity": "advanced",
        "required_parameters": ["template_asset_id", "replacement_asset_id"],
        "steps": [
            ("probe", "ps.probe", False, "session"),
            ("state-before", "ps.get_state", False, "session"),
            ("sandbox-copy", "photoshop.recipe_run", True, "document"),
            ("subject-selection", "ps.selection.subject", True, "selection_mask"),
            ("mask-refine", "ps.mask.refine", True, "selection_mask"),
            ("smart-object-place", "ps.smartobject.place", True, "smart_objects"),
            ("tone-match", "ps.adjustment.apply", True, "adjustments"),
            ("state-after", "ps.get_state", False, "session"),
            ("preview", "ps.get_preview", False, "session"),
            ("save-copy", "photoshop.recipe_run", True, "export"),
            ("verify", "ps.result.verify", False, "export"),
        ],
        "quality_gates": [
            "sandbox_copy",
            "selection_non_empty",
            "smart_object_present",
            "preview_readback",
            "artifact_hash",
            "native_reopen_if_psd_requested",
        ],
    },
    "batch-smart-object-replace-v1": {
        "title": "Resumable smart-object replacement batch",
        "complexity": "batch",
        "required_parameters": ["template_asset_id", "replacement_asset_id"],
        "steps": [
            ("probe", "ps.probe", False, "session"),
            ("state-before", "ps.get_state", False, "session"),
            ("sandbox-copy", "photoshop.recipe_run", True, "document"),
            ("smart-object-place", "ps.smartobject.place", True, "smart_objects"),
            ("text-update", "ps.text.edit", True, "text"),
            ("preview", "ps.get_preview", False, "session"),
            ("save-copy", "photoshop.recipe_run", True, "export"),
            ("verify", "ps.result.verify", False, "export"),
        ],
        "quality_gates": ["sandbox_copy", "per_item_hash", "native_reopen", "checkpoint_commit"],
        "execution_entrypoint": None,
    },
}


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def capability_manifest() -> dict[str, Any]:
    return {
        "ok": True,
        "bridge": "photoshop",
        "action": "capabilities",
        "details": {
            "categories": deepcopy(CAPABILITY_CATEGORIES),
            "recipes": sorted(RECIPE_LIBRARY),
            "execution_channels": ["node_proxy_uxp", "com_read_fallback", "mock_test"],
            "progressive_profiles": {
                "minimal": ["session", "document", "export"],
                "advanced": [
                    "session",
                    "document",
                    "layers",
                    "selection_mask",
                    "adjustments",
                    "smart_objects",
                    "text",
                    "export",
                ],
            },
            "arbitrary_shell": False,
            "arbitrary_jsx": False,
            "arbitrary_batchplay": False,
            "max_repair_rounds": 3,
            "live_connection_verified": False,
            "live_connection_probe_tool": "ps.probe",
        },
    }


def compile_recipe(recipe_id: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    if recipe_id not in RECIPE_LIBRARY:
        return {
            "ok": False,
            "bridge": "photoshop",
            "action": "recipe_compile",
            "error": {
                "code": "unknown_recipe",
                "suggested_next_action": "call ps.capabilities and select a listed recipe",
            },
        }
    definition = RECIPE_LIBRARY[recipe_id]
    missing = [key for key in definition["required_parameters"] if not parameters.get(key)]
    if missing:
        return {
            "ok": False,
            "bridge": "photoshop",
            "action": "recipe_compile",
            "error": {
                "code": "missing_recipe_parameter",
                "fields": missing,
                "suggested_next_action": "supply opaque managed asset IDs, never local private paths",
            },
        }
    steps = []
    unavailable: set[str] = set()
    for index, (step_id, tool, confirmation, category) in enumerate(definition["steps"]):
        status = str(CAPABILITY_CATEGORIES[category]["status"])
        if confirmation and status == "planned":
            unavailable.add(category)
        steps.append(
            {
                "index": index,
                "step_id": step_id,
                "tool": tool,
                "category": category,
                "capability_status": status,
                "requires_confirmation": confirmation,
                "sandbox_only": confirmation,
                "checkpoint_after": confirmation,
                "rollback": "single_history_state" if confirmation else "not_applicable",
            }
        )
    normalized_parameters = {
        key: value
        for key, value in parameters.items()
        if key
        in {
            *definition["required_parameters"],
            "output_formats",
            "canvas",
            "adjustment",
            "export_subject",
            "text_values",
        }
    }
    normalized_parameters.update(definition.get("fixed_parameters") or {})
    plan_id = _hash_payload({"recipe_id": recipe_id, "parameters": normalized_parameters})[:24]
    return {
        "ok": True,
        "bridge": "photoshop",
        "action": "recipe_compile",
        "details": {
            "schema_version": "crenexus.photoshop.recipe.v1",
            "recipe_id": recipe_id,
            "plan_id": plan_id,
            "title": definition["title"],
            "complexity": definition["complexity"],
            "progressive_profile": "minimal"
            if definition["complexity"] == "simple"
            else "advanced",
            "parameters": normalized_parameters,
            "steps": steps,
            "quality_gates": list(definition["quality_gates"]),
            "execution_entrypoint": definition.get("execution_entrypoint"),
            "max_repair_rounds": 3,
            "single_history_state": True,
            "source_overwrite": False,
            "execution_ready": not unavailable,
            "planned_only_categories": sorted(unavailable),
            "suggested_next_action": (
                "run ps.probe and resolve planned-only capabilities before execution"
                if unavailable
                else "run ps.probe, review the plan, then confirm sandbox execution"
            ),
        },
    }


def build_batch_plan(
    items: list[dict[str, Any]], *, completed_item_ids: list[str] | None = None
) -> dict[str, Any]:
    completed = set(completed_item_ids or [])
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        recipe_id = str(item.get("recipe_id") or "batch-production-delivery-v1")
        parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        compiled = compile_recipe(recipe_id, parameters)
        item_id = _hash_payload({"index": index, "recipe_id": recipe_id, "parameters": parameters})[
            :24
        ]
        if not compiled["ok"]:
            errors.append({"item_id": item_id, "error": compiled["error"]})
        execution_ready = bool(compiled.get("details", {}).get("execution_ready"))
        rows.append(
            {
                "item_id": item_id,
                "recipe_id": recipe_id,
                "plan_id": compiled.get("details", {}).get("plan_id"),
                "status": (
                    "completed"
                    if item_id in completed
                    else (
                        "invalid"
                        if not compiled["ok"]
                        else ("queued" if execution_ready else "blocked_planned")
                    )
                ),
                "execution_ready": execution_ready,
                "execution_entrypoint": compiled.get("details", {}).get("execution_entrypoint"),
                "idempotency_key": _hash_payload({"item_id": item_id, "recipe_id": recipe_id}),
            }
        )
    return {
        "ok": not errors,
        "bridge": "photoshop",
        "action": "batch_plan",
        "details": {
            "schema_version": "crenexus.photoshop.batch.v1",
            "items": rows,
            "errors": errors,
            "concurrency_limit": 1,
            "single_host_fifo": True,
            "resume_supported": True,
            "completed_item_ids": sorted(completed),
            "pending_item_ids": [row["item_id"] for row in rows if row["status"] == "queued"],
            "blocked_item_ids": [
                row["item_id"] for row in rows if row["status"] == "blocked_planned"
            ],
            "checkpoint_commit_requires_verified_output": True,
            "writes_files": False,
        },
    }


def verify_result(arguments: dict[str, Any]) -> dict[str, Any]:
    before = (
        arguments.get("before_state") if isinstance(arguments.get("before_state"), dict) else {}
    )
    after = arguments.get("after_state") if isinstance(arguments.get("after_state"), dict) else {}
    artifacts = list(arguments.get("artifacts") or [])
    require_reopen = bool(arguments.get("require_native_reopen", True))
    gates = {
        "sandbox_copy": bool(after.get("sandbox_copy")),
        "source_not_overwritten": after.get("source_overwritten") is False,
        "state_readback": bool(before) and bool(after),
        "artifact_count": len(artifacts) > 0,
        "artifact_hashes": all(
            isinstance(item, dict)
            and bool(item.get("basename"))
            and bool(_SHA256.fullmatch(str(item.get("sha256") or "")))
            and int(item.get("size_bytes") or 0) > 0
            for item in artifacts
        ),
        "native_reopen": bool(after.get("validated_after_reopen")) if require_reopen else True,
    }
    ok = all(gates.values())
    return {
        "ok": ok,
        "bridge": "photoshop",
        "action": "result_verify",
        "details": {
            "quality_gates": gates,
            "verified_artifact_count": len(artifacts) if gates["artifact_hashes"] else 0,
            "repair_allowed": not ok and int(arguments.get("repair_round") or 0) < 3,
            "next_repair_round": min(3, int(arguments.get("repair_round") or 0) + 1),
            "suggested_next_action": (
                "accept verified sandbox delivery"
                if ok
                else "repair only failed gates, then read state and verify again"
            ),
        },
    }
