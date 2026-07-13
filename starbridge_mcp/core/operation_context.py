from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from starbridge_mcp.core.operation_context_schema import (
    BRIDGES,
    CONTEXT_ID_PATTERN,
    EVIDENCE_REF_PATTERN,
    PHASES,
    SAFE_IDENTIFIER_PATTERN,
    SCHEMA_VERSION,
    STATE_FIELD_SCHEMAS,
)
from starbridge_mcp.core.security import sanitize


def _ensure_identifier(field: str, value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(SAFE_IDENTIFIER_PATTERN, value) is None:
        raise ValueError(f"{field} must be a safe identifier")
    if sanitize(value) != value:
        raise ValueError(f"{field} must be a safe identifier")
    return value


def _normalize_state(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise TypeError("state snapshot must be an object")
    if set(snapshot) - set(STATE_FIELD_SCHEMAS):
        raise ValueError("unknown state fields are not allowed")

    normalized: dict[str, Any] = {}
    for field in sorted(snapshot):
        value = snapshot[field]
        schema = STATE_FIELD_SCHEMAS[field]
        expected = schema["type"]

        if expected == "boolean":
            if type(value) is not bool:
                raise ValueError(f"{field} must be boolean")
        elif expected == "integer":
            if type(value) is not int:
                raise ValueError(f"{field} must be integer")
            if value < int(schema.get("minimum", value)) or value > int(
                schema.get("maximum", value)
            ):
                raise ValueError(f"{field} is outside the allowed range")
        elif expected == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field} must be number")
            if not math.isfinite(float(value)) or value < float(schema.get("minimum", value)):
                raise ValueError(f"{field} is outside the allowed range")
        elif expected == "string":
            value = _ensure_identifier(field, value)
        else:  # pragma: no cover - schema contract guard
            raise ValueError("unsupported state field schema")

        normalized[field] = value
    return normalized


def _normalize_warnings(warnings: Any) -> tuple[list[str], bool]:
    if warnings is None:
        return [], False
    if not isinstance(warnings, list) or len(warnings) > 20:
        raise ValueError("warnings must be a list with at most 20 items")

    normalized: list[str] = []
    redactions_applied = False
    for warning in warnings:
        if not isinstance(warning, str) or len(warning) > 256:
            raise ValueError("warning must be a string with at most 256 characters")
        sanitized = str(sanitize(warning))
        normalized.append(sanitized)
        redactions_applied = redactions_applied or sanitized != warning
    return normalized, redactions_applied


def _normalize_evidence_refs(evidence_refs: Any) -> list[str]:
    if evidence_refs is None:
        return []
    if not isinstance(evidence_refs, list) or len(evidence_refs) > 20:
        raise ValueError("evidence_refs must be a list with at most 20 items")
    normalized: list[str] = []
    for reference in evidence_refs:
        if not isinstance(reference, str) or re.fullmatch(EVIDENCE_REF_PATTERN, reference) is None:
            raise ValueError("evidence_refs must use a logical evidence id")
        normalized.append(reference)
    return normalized


def _state_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    unchanged_fields: list[str] = []

    for field in sorted(set(before) | set(after)):
        if field not in before:
            added.append({"field": field, "value": after[field]})
        elif field not in after:
            removed.append({"field": field, "value": before[field]})
        elif before[field] != after[field]:
            changed.append({"field": field, "before": before[field], "after": after[field]})
        else:
            unchanged_fields.append(field)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_fields": unchanged_fields,
    }


def _context_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"ctx_{hashlib.sha256(canonical).hexdigest()[:12]}"


def operation_context_contract() -> dict[str, Any]:
    return {
        "tool": "starbridge.operation_context",
        "schema_version": SCHEMA_VERSION,
        "capture_points": [
            "before_first_major_action",
            "after_each_major_action",
            "after_failure",
        ],
        "state_fields": sorted(STATE_FIELD_SCHEMAS),
        "evidence_ref_policy": "logical_ids_only",
        "source": "caller_supplied_sanitized_summary",
        "local_reads": False,
        "local_writes": False,
    }


def build_operation_context(
    *,
    bridge: str,
    action: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    operation_id: str = "operation_preview",
    phase: str = "completed",
    dry_run: bool = True,
    warnings: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    parent_context_id: str | None = None,
) -> dict[str, Any]:
    if bridge not in BRIDGES:
        raise ValueError("bridge must be a supported StarBridge bridge")
    action = _ensure_identifier("action", action)
    operation_id = _ensure_identifier("operation_id", operation_id)
    if phase not in PHASES:
        raise ValueError("phase must be a supported operation phase")
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be boolean")
    if (
        parent_context_id is not None
        and re.fullmatch(CONTEXT_ID_PATTERN, parent_context_id) is None
    ):
        raise ValueError("parent_context_id must be a safe context id")

    before = _normalize_state(before_state)
    after = _normalize_state(after_state)
    safe_warnings, redactions_applied = _normalize_warnings(warnings)
    safe_evidence_refs = _normalize_evidence_refs(evidence_refs)
    delta = _state_delta(before, after)
    change_count = len(delta["added"]) + len(delta["removed"]) + len(delta["changed"])

    state = {
        "before": before,
        "after": after,
        "delta": delta,
        "has_changes": change_count > 0,
        "change_count": change_count,
    }
    payload: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "parent_context_id": parent_context_id,
        "operation_id": operation_id,
        "bridge": bridge,
        "action": action,
        "phase": phase,
        "dry_run": dry_run,
        "state": state,
        "warnings": safe_warnings,
        "evidence_refs": safe_evidence_refs,
        "redactions_applied": redactions_applied,
        "safety": {
            "source": "caller_supplied_sanitized_summary",
            "whitelisted_state_fields_only": True,
            "logical_evidence_ids_only": True,
            "local_reads": False,
            "local_writes": False,
            "desktop_software_started": False,
        },
    }

    next_steps: list[str] = []
    if phase == "failed" or safe_warnings:
        next_steps.append("Review warnings and capture a new safe state before retrying.")
    if state["has_changes"]:
        next_steps.append("Attach a logical evidence reference before the next guarded write.")
    else:
        next_steps.append("Confirm the no-op was expected before continuing the recipe.")
    payload["next_steps"] = next_steps
    payload["context_id"] = _context_id(payload)
    return sanitize(payload)
