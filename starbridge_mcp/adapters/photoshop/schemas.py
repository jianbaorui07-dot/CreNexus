from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ADAPTER_NAME = "codex_photoshop_bridge_v1"
ADAPTER_VERSION = "1.0.0"

RISK_LEVELS = (
    "level_0_read_only",
    "level_1_sandbox_write",
    "level_2_confirmed_write",
    "level_3_destructive_batch",
)

BRIDGE_KINDS = (
    "auto",
    "mock",
    "com",
    "node_proxy",
    "uxp",
)


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        payload["required"] = required
    return payload


def common_properties(
    *,
    risk_level: str,
    requires_confirmation: bool,
    writes_files: bool,
    touches_user_psd: bool,
    default_output_dir: str,
) -> dict[str, Any]:
    return {
        "job_id": {"type": "string", "description": "Optional client supplied job identifier."},
        "risk_level": {"type": "string", "enum": list(RISK_LEVELS), "default": risk_level},
        "requires_confirmation": {"type": "boolean", "default": requires_confirmation},
        "dry_run": {"type": "boolean", "default": True},
        "writes_files": {"type": "boolean", "default": writes_files},
        "touches_user_psd": {"type": "boolean", "default": touches_user_psd},
        "bridge_kind": {"type": "string", "enum": list(BRIDGE_KINDS), "default": "auto"},
        "output_dir": {"type": "string", "default": default_output_dir},
        "evidence_path": {"type": "string", "description": "Optional manifest output path inside sandbox/evidence or output/evidence."},
    }


def probe_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=False,
                default_output_dir="sandbox/evidence",
            ),
            "probe_com": {"type": "boolean", "default": True},
        }
    )


def document_info_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=True,
                default_output_dir="sandbox/evidence",
            ),
            "include_layer_summary": {"type": "boolean", "default": True},
        }
    )


def layers_list_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=True,
                default_output_dir="sandbox/evidence",
            ),
            "max_layers": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
        }
    )


def selection_subject_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_1_sandbox_write",
                requires_confirmation=True,
                writes_files=False,
                touches_user_psd=True,
                default_output_dir="sandbox/evidence",
            ),
            "source_layer_id": {"type": "string", "description": "Optional source layer identifier for future UXP routing."},
        }
    )


def preview_export_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_1_sandbox_write",
                requires_confirmation=True,
                writes_files=True,
                touches_user_psd=True,
                default_output_dir="sandbox",
            ),
            "format": {"type": "string", "enum": ["png"], "default": "png"},
            "max_side": {"type": "integer", "minimum": 64, "maximum": 4096, "default": 1600},
        }
    )


def layer_write_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_1_sandbox_write",
                requires_confirmation=True,
                writes_files=False,
                touches_user_psd=True,
                default_output_dir="sandbox/evidence",
            ),
            "layer_id": {"type": "string"},
            "layer_name": {"type": "string"},
            "target_index": {"type": "integer", "minimum": 0, "default": 0},
            "visible": {"type": "boolean"},
        }
    )


def evidence_capture_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_1_sandbox_write",
                requires_confirmation=True,
                writes_files=True,
                touches_user_psd=False,
                default_output_dir="sandbox/evidence",
            ),
            "notes": {"type": "string", "default": ""},
            "source_files": {"type": "array", "items": {"type": "string"}, "default": []},
        }
    )


def batchplay_validate_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=False,
                default_output_dir="sandbox/evidence",
            ),
            "descriptors": {"type": "array", "items": {"type": "object"}, "default": []},
            "descriptor": {"type": "object"},
        }
    )


def disabled_confirmed_write_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_2_confirmed_write",
                requires_confirmation=True,
                writes_files=True,
                touches_user_psd=True,
                default_output_dir="sandbox",
            ),
            "payload": {"type": "object"},
        }
    )


@dataclass(frozen=True)
class EvidenceManifest:
    job_id: str
    created_at: str
    adapter_name: str
    adapter_version: str
    tool_name: str
    risk_level: str
    requires_confirmation: bool
    dry_run: bool
    input_summary: dict[str, Any]
    output_files: list[str]
    preview_files: list[str]
    source_files: list[str]
    photoshop_available: bool
    bridge_kind: str
    status: str
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "dry_run": self.dry_run,
            "input_summary": self.input_summary,
            "output_files": self.output_files,
            "preview_files": self.preview_files,
            "source_files": self.source_files,
            "photoshop_available": self.photoshop_available,
            "bridge_kind": self.bridge_kind,
            "status": self.status,
            "warnings": self.warnings,
            "errors": self.errors,
        }
