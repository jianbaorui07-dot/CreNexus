from __future__ import annotations

from typing import Any

ALLOWLIST: dict[str, dict[str, Any]] = {
    "get": {
        "descriptor_id": "get_document_or_layer_info",
        "risk_level": "safe_read_only",
        "requires_confirmation": False,
        "dry_run_only": False,
        "sandbox_only": False,
    },
    "save": {
        "descriptor_id": "export_preview_from_sandbox_copy",
        "risk_level": "guarded_local_write",
        "requires_confirmation": True,
        "dry_run_only": False,
        "sandbox_only": True,
    },
    "make": {
        "descriptor_id": "create_test_adjustment_layer_in_sandbox",
        "risk_level": "guarded_local_write",
        "requires_confirmation": True,
        "dry_run_only": False,
        "sandbox_only": True,
    },
    "set": {
        "descriptor_id": "rename_or_visibility_in_sandbox",
        "risk_level": "guarded_local_write",
        "requires_confirmation": True,
        "dry_run_only": False,
        "sandbox_only": True,
    },
    "move": {
        "descriptor_id": "move_layer_in_sandbox",
        "risk_level": "guarded_local_write",
        "requires_confirmation": True,
        "dry_run_only": False,
        "sandbox_only": True,
    },
}

DENYLIST = {
    "delete",
    "duplicate",
    "mergeLayersNew",
    "flattenImage",
    "rasterizeLayer",
    "placedLayerEditContents",
    "eventSave",
    "save",
    "batchPlay",
    "javascript",
}

PATH_FIELD_NAMES = {
    "file",
    "filepath",
    "fullname",
    "nativepath",
    "path",
    "sourcepath",
    "targetpath",
    "url",
}


def _unsafe_payload_reason(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            reason = _unsafe_payload_reason(item)
            if reason:
                return reason
        return None
    if not isinstance(value, dict):
        return None

    reference = str(value.get("_ref") or "").lower()
    if reference in {"document", "layer"} and any(
        key in value for key in ("_id", "_index", "_name")
    ):
        return f"explicit_target:{reference}"

    for key, item in value.items():
        normalized = str(key).replace("_", "").lower()
        if normalized in PATH_FIELD_NAMES or normalized.endswith("path"):
            return f"path_field:{key}"
        reason = _unsafe_payload_reason(item)
        if reason:
            return reason
    return None


def validate_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    action = str(descriptor.get("_obj") or descriptor.get("method") or "").strip()
    if not action:
        return {
            "allowed": False,
            "action": "",
            "descriptor_id": "missing_action",
            "risk_level": "guarded_local_write",
            "requires_confirmation": True,
            "dry_run_only": True,
            "sandbox_only": True,
            "reason": "Descriptor is missing _obj or method.",
        }

    if action in DENYLIST:
        return {
            "allowed": False,
            "action": action,
            "descriptor_id": f"denied_{action}",
            "risk_level": "guarded_local_write",
            "requires_confirmation": True,
            "dry_run_only": True,
            "sandbox_only": True,
            "reason": f"Descriptor action {action} is explicitly denied.",
        }

    unsafe_reason = _unsafe_payload_reason(descriptor)
    if unsafe_reason:
        return {
            "allowed": False,
            "action": action,
            "descriptor_id": f"unsafe_{action}",
            "risk_level": "guarded_local_write",
            "requires_confirmation": True,
            "dry_run_only": True,
            "sandbox_only": True,
            "reason": unsafe_reason,
        }

    allowed = ALLOWLIST.get(action)
    if allowed is None:
        return {
            "allowed": False,
            "action": action,
            "descriptor_id": f"unknown_{action}",
            "risk_level": "guarded_local_write",
            "requires_confirmation": True,
            "dry_run_only": True,
            "sandbox_only": True,
            "reason": f"Descriptor action {action} is not in the allowlist.",
        }

    return {
        "allowed": True,
        "action": action,
        **allowed,
        "reason": "Descriptor is in the typed allowlist.",
    }
