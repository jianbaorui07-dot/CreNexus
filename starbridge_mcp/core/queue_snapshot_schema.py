from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "starbridge.queue-snapshot.v1"
SNAPSHOT_ID_PATTERN = r"^queue_[0-9a-f]{12}$"
LOGICAL_JOB_ID_PATTERN = r"^job_[0-9a-f]{12}$"
DECISIONS = ("planned", "unavailable", "idle", "busy", "backlog")
MAX_PROGRESS_VALUE = 1_000_000

PROGRESS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "current": {"type": "integer", "minimum": 0, "maximum": MAX_PROGRESS_VALUE},
        "total": {"type": "integer", "minimum": 1, "maximum": MAX_PROGRESS_VALUE},
        "previous": {"type": "integer", "minimum": 0, "maximum": MAX_PROGRESS_VALUE},
    },
    "required": ["current", "total"],
    "additionalProperties": False,
}

QUEUE_SNAPSHOT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "probe": {
            "type": "boolean",
            "default": False,
            "description": "显式允许只读访问 loopback ComfyUI /queue；默认只返回计划。",
        },
        "comfy_url": {
            "type": "string",
            "maxLength": 128,
            "default": "http://127.0.0.1:8188",
            "description": "只允许无账号、query、fragment 或额外路径的 loopback HTTP URL。",
        },
        "timeout": {"type": "integer", "minimum": 1, "maximum": 15, "default": 5},
        "max_items": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        "progress": PROGRESS_INPUT_SCHEMA,
    },
    "additionalProperties": False,
}

JOB_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "logical_job_id": {"type": "string", "pattern": LOGICAL_JOB_ID_PATTERN},
        "status": {"type": "string", "enum": ["running", "pending"]},
        "position": {"type": "integer", "minimum": 0},
    },
    "required": ["logical_job_id", "status", "position"],
    "additionalProperties": False,
}

QUEUE_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "running_count": {"type": "integer", "minimum": 0},
        "pending_count": {"type": "integer", "minimum": 0},
        "depth": {"type": "integer", "minimum": 0},
        "busy": {"type": "boolean"},
        "backlog": {"type": "boolean"},
        "safe_to_enqueue": {"type": "boolean"},
        "truncated": {"type": "boolean"},
        "running_jobs": {"type": "array", "items": JOB_SUMMARY_SCHEMA},
        "pending_jobs": {"type": "array", "items": JOB_SUMMARY_SCHEMA},
    },
    "required": [
        "running_count",
        "pending_count",
        "depth",
        "busy",
        "backlog",
        "safe_to_enqueue",
        "truncated",
        "running_jobs",
        "pending_jobs",
    ],
    "additionalProperties": False,
}

PROGRESS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "available": {"type": "boolean"},
        "source": {"type": "string", "enum": ["not_available", "caller_supplied"]},
        "current": {"type": ["integer", "null"]},
        "total": {"type": ["integer", "null"]},
        "percent": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
        "monotonic": {"type": "boolean"},
    },
    "required": ["available", "source", "current", "total", "percent", "monotonic"],
    "additionalProperties": False,
}

SAFETY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        field: {"type": "boolean"}
        for field in (
            "network_access",
            "loopback_only",
            "redirects_followed",
            "workflow_payloads_returned",
            "prompt_ids_returned",
            "history_read",
            "queue_mutation",
            "local_file_reads",
            "local_file_writes",
            "desktop_software_started",
        )
    },
    "required": [
        "network_access",
        "loopback_only",
        "redirects_followed",
        "workflow_payloads_returned",
        "prompt_ids_returned",
        "history_read",
        "queue_mutation",
        "local_file_reads",
        "local_file_writes",
        "desktop_software_started",
    ],
    "additionalProperties": False,
}

QUEUE_SNAPSHOT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "schema_version": {"type": "string", "const": SCHEMA_VERSION},
        "snapshot_id": {"type": "string", "pattern": SNAPSHOT_ID_PATTERN},
        "bridge": {"type": "string", "const": "comfyui"},
        "action": {"type": "string", "const": "queue_snapshot"},
        "mode": {"type": "string", "enum": ["planned", "live"]},
        "connected": {"type": "boolean"},
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "endpoint": {"type": "string", "const": "/queue"},
        "queue": QUEUE_SUMMARY_SCHEMA,
        "progress": PROGRESS_OUTPUT_SCHEMA,
        "error_code": {
            "type": ["string", "null"],
            "enum": [None, "queue_endpoint_unavailable", "queue_payload_invalid"],
        },
        "warnings": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "live_queue_not_probed",
                    "loopback_queue_unavailable",
                    "queue_payload_rejected",
                ],
            },
        },
        "redactions_applied": {"type": "boolean"},
        "safety": SAFETY_OUTPUT_SCHEMA,
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "ok",
        "schema_version",
        "snapshot_id",
        "bridge",
        "action",
        "mode",
        "connected",
        "decision",
        "endpoint",
        "queue",
        "progress",
        "error_code",
        "warnings",
        "redactions_applied",
        "safety",
        "next_steps",
    ],
    "additionalProperties": False,
}
