from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "starbridge.operation-context.v1"
PHASES = ("planned", "before", "after", "completed", "failed")
BRIDGES = (
    "starbridge",
    "comfyui",
    "blender",
    "autocad",
    "cad_autocad",
    "autocad_dxf",
    "photoshop",
    "illustrator",
    "jianying_capcut",
    "stable_fast_3d",
)

SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_.:-]{1,96}$"
CONTEXT_ID_PATTERN = r"^ctx_[0-9a-f]{12}$"
EVIDENCE_REF_PATTERN = r"^(manifest|job|recipe|transaction)::[A-Za-z0-9_.:-]{1,96}$"

STATE_FIELD_SCHEMAS: dict[str, dict[str, Any]] = {
    "state_revision": {"type": "string", "pattern": SAFE_IDENTIFIER_PATTERN},
    "connected": {"type": "boolean"},
    "document_open": {"type": "boolean"},
    "document_width": {"type": "number", "minimum": 0},
    "document_height": {"type": "number", "minimum": 0},
    "canvas_width": {"type": "number", "minimum": 0},
    "canvas_height": {"type": "number", "minimum": 0},
    "resolution": {"type": "number", "minimum": 0},
    "layer_count": {"type": "integer", "minimum": 0},
    "selection_count": {"type": "integer", "minimum": 0},
    "artboard_count": {"type": "integer", "minimum": 0},
    "object_count": {"type": "integer", "minimum": 0},
    "material_count": {"type": "integer", "minimum": 0},
    "frame_count": {"type": "integer", "minimum": 0},
    "track_count": {"type": "integer", "minimum": 0},
    "queue_pending": {"type": "integer", "minimum": 0},
    "queue_running": {"type": "integer", "minimum": 0},
    "queue_completed": {"type": "integer", "minimum": 0},
    "queue_failed": {"type": "integer", "minimum": 0},
    "progress": {"type": "integer", "minimum": 0, "maximum": 100},
    "duration_ms": {"type": "integer", "minimum": 0},
    "status": {"type": "string", "pattern": SAFE_IDENTIFIER_PATTERN},
    "active_item_type": {"type": "string", "pattern": SAFE_IDENTIFIER_PATTERN},
    "color_mode": {"type": "string", "pattern": SAFE_IDENTIFIER_PATTERN},
}

STATE_SNAPSHOT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": STATE_FIELD_SCHEMAS,
    "additionalProperties": False,
}

OPERATION_CONTEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "bridge": {"type": "string", "enum": list(BRIDGES)},
        "action": {"type": "string", "pattern": SAFE_IDENTIFIER_PATTERN},
        "operation_id": {
            "type": "string",
            "pattern": SAFE_IDENTIFIER_PATTERN,
            "default": "operation_preview",
        },
        "phase": {"type": "string", "enum": list(PHASES), "default": "completed"},
        "dry_run": {"type": "boolean", "default": True},
        "before_state": STATE_SNAPSHOT_SCHEMA,
        "after_state": STATE_SNAPSHOT_SCHEMA,
        "warnings": {
            "type": "array",
            "items": {"type": "string", "maxLength": 256},
            "maxItems": 20,
            "default": [],
        },
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string", "pattern": EVIDENCE_REF_PATTERN},
            "maxItems": 20,
            "default": [],
        },
        "parent_context_id": {
            "type": "string",
            "pattern": CONTEXT_ID_PATTERN,
        },
    },
    "required": ["bridge", "action", "before_state", "after_state"],
    "additionalProperties": False,
}

OPERATION_CONTEXT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "context_id": {"type": "string", "pattern": CONTEXT_ID_PATTERN},
        "parent_context_id": {"type": ["string", "null"]},
        "operation_id": {"type": "string"},
        "bridge": {"type": "string"},
        "action": {"type": "string"},
        "phase": {"type": "string", "enum": list(PHASES)},
        "dry_run": {"type": "boolean"},
        "state": {"type": "object"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "redactions_applied": {"type": "boolean"},
        "safety": {"type": "object"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "ok",
        "schema_version",
        "context_id",
        "parent_context_id",
        "operation_id",
        "bridge",
        "action",
        "phase",
        "dry_run",
        "state",
        "warnings",
        "evidence_refs",
        "redactions_applied",
        "safety",
        "next_steps",
    ],
    "additionalProperties": False,
}
