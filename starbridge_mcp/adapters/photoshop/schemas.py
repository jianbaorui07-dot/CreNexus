from __future__ import annotations

from dataclasses import dataclass, field
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
    "node_proxy_uxp",
    "fallback",
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
        "evidence_path": {
            "type": "string",
            "description": "Optional manifest output path inside sandbox/evidence or output/evidence.",
        },
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
            "strict": {
                "type": "boolean",
                "default": False,
                "description": "Fail probe when the resolved bridge_kind is 'mock'; require a real node_proxy_uxp or com link.",
            },
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
            "source_layer_id": {
                "type": "string",
                "description": "Optional source layer identifier for future UXP routing.",
            },
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
                default_output_dir="examples/output/photoshop",
            ),
            "format": {"type": "string", "enum": ["png"], "default": "png"},
            "max_side": {"type": "integer", "minimum": 64, "maximum": 4096, "default": 1600},
            "strict": {
                "type": "boolean",
                "default": False,
                "description": "When true, fail instead of silently writing a placeholder PNG when the UXP bridge is unavailable.",
            },
            "allow_placeholder": {
                "type": "boolean",
                "default": False,
                "description": "When true, allow a marked placeholder PNG for local protocol demos if the UXP bridge is unavailable.",
            },
        }
    )


def camera_raw_tune_schema() -> dict[str, Any]:
    camera_raw_params = object_schema(
        {
            "temperature": {"type": "number", "minimum": 2000, "maximum": 50000, "default": 4800},
            "tint": {"type": "number", "minimum": -150, "maximum": 150, "default": 10},
            "exposure": {"type": "number", "minimum": -5, "maximum": 5, "default": 0.35},
            "contrast": {"type": "number", "minimum": -100, "maximum": 100, "default": 10},
            "highlights": {"type": "number", "minimum": -100, "maximum": 100, "default": -25},
            "shadows": {"type": "number", "minimum": -100, "maximum": 100, "default": 35},
            "whites": {"type": "number", "minimum": -100, "maximum": 100, "default": 12},
            "blacks": {"type": "number", "minimum": -100, "maximum": 100, "default": -12},
            "texture": {"type": "number", "minimum": -100, "maximum": 100, "default": 18},
            "clarity": {"type": "number", "minimum": -100, "maximum": 100, "default": 8},
            "dehaze": {"type": "number", "minimum": -100, "maximum": 100, "default": 3},
            "vibrance": {"type": "number", "minimum": -100, "maximum": 100, "default": 14},
            "saturation": {"type": "number", "minimum": -100, "maximum": 100, "default": -2},
        }
    )
    return object_schema(
        {
            **common_properties(
                risk_level="level_2_confirmed_write",
                requires_confirmation=True,
                writes_files=False,
                touches_user_psd=True,
                default_output_dir="examples/output/photoshop",
            ),
            "protocol_version": {
                "type": "string",
                "enum": ["camera_raw_tune.v1"],
                "default": "camera_raw_tune.v1",
            },
            "method": {
                "type": "string",
                "enum": ["ps.camera_raw.tune"],
                "default": "ps.camera_raw.tune",
            },
            "confirm_apply": {"type": "boolean", "default": False},
            "confirm_export": {"type": "boolean", "default": False},
            "descriptor_fixture_path": {
                "type": "string",
                "description": "Optional local verified Camera Raw BatchPlay descriptor fixture path. Do not commit real local paths.",
            },
            "preset": {
                "type": "string",
                "enum": ["blue_artwork_clean"],
                "default": "blue_artwork_clean",
            },
            "params": camera_raw_params,
            "source": object_schema(
                {
                    "mode": {
                        "type": "string",
                        "enum": ["active_document", "explicit_path"],
                        "default": "active_document",
                    },
                    "path": {
                        "type": "string",
                        "description": "User-explicit local image path; recorded in the plan only and never scanned recursively.",
                    },
                }
            ),
            "output": object_schema(
                {
                    "dir": {"type": "string", "default": "examples/output/photoshop"},
                    "basename": {"type": "string", "default": "camera_raw_tune_preview"},
                    "formats": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["jpg", "png"]},
                        "default": ["jpg"],
                    },
                    "export_after_apply": {"type": "boolean", "default": False},
                }
            ),
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
            "descriptors": {
                "type": "array",
                "maxItems": 32,
                "items": {"type": "object"},
                "default": [],
            },
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


def get_preview_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=False,
                default_output_dir="sandbox/evidence",
            ),
            "max_side": {"type": "integer", "minimum": 64, "maximum": 4096, "default": 1024},
            "format": {"type": "string", "enum": ["png", "jpg"], "default": "jpg"},
            "quality": {"type": "integer", "minimum": 1, "maximum": 100, "default": 80},
            "include_base64": {
                "type": "boolean",
                "default": True,
                "description": "Return base64 data for vision models.",
            },
        }
    )


def get_state_schema() -> dict[str, Any]:
    return object_schema(
        {
            **common_properties(
                risk_level="level_0_read_only",
                requires_confirmation=False,
                writes_files=False,
                touches_user_psd=False,
                default_output_dir="sandbox/evidence",
            ),
            "include_layers": {"type": "boolean", "default": True},
            "include_history": {"type": "boolean", "default": False},
            "lightweight": {
                "type": "boolean",
                "default": True,
                "description": "Cheap snapshot without full pixel data.",
            },
        }
    )


def capabilities_schema() -> dict[str, Any]:
    return object_schema({})


def recipe_compile_schema() -> dict[str, Any]:
    return object_schema(
        {
            "recipe_id": {
                "type": "string",
                "enum": [
                    "simple-tone-export-v1",
                    "production-subject-delivery-v1",
                    "batch-production-delivery-v1",
                    "product-composite-verified-v1",
                    "batch-smart-object-replace-v1",
                ],
            },
            "parameters": {
                "type": "object",
                "description": "Typed recipe parameters using managed opaque asset IDs, never private paths.",
            },
        },
        required=["recipe_id"],
    )


def batch_plan_schema() -> dict[str, Any]:
    return object_schema(
        {
            "items": {"type": "array", "maxItems": 500, "items": {"type": "object"}},
            "completed_item_ids": {"type": "array", "items": {"type": "string"}},
        },
        required=["items"],
    )


def result_verify_schema() -> dict[str, Any]:
    return object_schema(
        {
            "before_state": {"type": "object"},
            "after_state": {"type": "object"},
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "basename": {"type": "string"},
                        "sha256": {"type": "string"},
                        "size_bytes": {"type": "integer", "minimum": 1},
                    },
                    "required": ["basename", "sha256", "size_bytes"],
                    "additionalProperties": False,
                },
            },
            "require_native_reopen": {"type": "boolean", "default": True},
            "repair_round": {"type": "integer", "minimum": 0, "maximum": 3, "default": 0},
        },
        required=["before_state", "after_state", "artifacts"],
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
    node_proxy_status: dict[str, Any]
    uxp_status: dict[str, Any]
    photoshop_host: dict[str, Any]
    layers_snapshot: list[dict[str, Any]]
    history_state: str | None
    descriptor_summary: list[dict[str, Any]]
    validation_result: dict[str, Any]
    status: str
    warnings: list[str]
    errors: list[str]
    output_artifacts: list[dict[str, Any]] = field(default_factory=list)

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
            "node_proxy_status": self.node_proxy_status,
            "uxp_status": self.uxp_status,
            "photoshop_host": self.photoshop_host,
            "layers_snapshot": self.layers_snapshot,
            "history_state": self.history_state,
            "descriptor_summary": self.descriptor_summary,
            "validation_result": self.validation_result,
            "status": self.status,
            "warnings": self.warnings,
            "errors": self.errors,
            "output_artifacts": list(self.output_artifacts),
        }
