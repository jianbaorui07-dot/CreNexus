from __future__ import annotations

from typing import Any

from .schemas import (
    batchplay_validate_schema,
    disabled_confirmed_write_schema,
    document_info_schema,
    evidence_capture_schema,
    layer_write_schema,
    layers_list_schema,
    preview_export_schema,
    probe_schema,
    selection_subject_schema,
)


def _tool(name: str, title: str, description: str, input_schema: dict[str, Any], read_only: bool) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "openWorldHint": False,
        },
    }


def build_tool_definitions() -> list[dict[str, Any]]:
    return [
        _tool("ps.probe", "Photoshop Probe", "Probe local Photoshop bridge readiness with COM fallback and mock support.", probe_schema(), True),
        _tool("ps.document.info", "Photoshop Document Info", "Inspect the active Photoshop document without opening files from MCP.", document_info_schema(), True),
        _tool("ps.layers.list", "Photoshop Layers List", "List the active Photoshop layer tree for local review.", layers_list_schema(), True),
        _tool("ps.selection.subject", "Photoshop Subject Selection", "Stage subject-selection work in a dry-run or mock-safe path.", selection_subject_schema(), False),
        _tool("ps.layer.rename", "Photoshop Layer Rename", "Plan or mock a layer rename without touching a real PSD by default.", layer_write_schema(), False),
        _tool("ps.layer.move", "Photoshop Layer Move", "Plan or mock a layer move without touching a real PSD by default.", layer_write_schema(), False),
        _tool("ps.layer.visibility", "Photoshop Layer Visibility", "Plan or mock a layer visibility change without touching a real PSD by default.", layer_write_schema(), False),
        _tool("ps.preview.export", "Photoshop Preview Export", "Stage a sandbox preview export. Defaults to dry_run and requires_confirmation for writes.", preview_export_schema(), False),
        _tool("ps.evidence.capture", "Photoshop Evidence Capture", "Capture an EvidenceManifest JSON for a local Photoshop job.", evidence_capture_schema(), False),
        _tool("ps.batchplay.validate", "BatchPlay Validate", "Validate BatchPlay descriptors without executing them.", batchplay_validate_schema(), True),
        _tool("ps.batchplay.execute_confirmed", "BatchPlay Execute Confirmed", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.script.execute_confirmed", "Photoshop Script Execute Confirmed", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.history.undo", "Photoshop History Undo", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.mask.refine", "Photoshop Mask Refine", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.smartobject.place", "Photoshop Smart Object Place", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.adjustment.apply", "Photoshop Adjustment Apply", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.text.edit", "Photoshop Text Edit", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
        _tool("ps.export.psd_copy", "Photoshop PSD Copy Export", "Reserved and disabled in v1.", disabled_confirmed_write_schema(), False),
    ]
