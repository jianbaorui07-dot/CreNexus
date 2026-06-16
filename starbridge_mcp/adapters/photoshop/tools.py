from __future__ import annotations

from typing import Any

from .schemas import (
    batchplay_validate_schema,
    camera_raw_tune_schema,
    disabled_confirmed_write_schema,
    document_info_schema,
    evidence_capture_schema,
    layer_write_schema,
    layers_list_schema,
    preview_export_schema,
    probe_schema,
    selection_subject_schema,
)


def _annotations(*, risk_level: str, safe_default: bool, requires_confirmation: bool, requires_local_software: bool, current_status: str, read_only: bool) -> dict[str, Any]:
    return {
        "readOnlyHint": read_only,
        "destructiveHint": not read_only,
        "openWorldHint": False,
        "riskLevel": risk_level,
        "safeDefault": safe_default,
        "requiresConfirmation": requires_confirmation,
        "requiresLocalSoftware": requires_local_software,
        "currentStatus": current_status,
    }


def _tool(name: str, title: str, description: str, input_schema: dict[str, Any], *, risk_level: str, safe_default: bool, requires_confirmation: bool, requires_local_software: bool, current_status: str, read_only: bool) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": _annotations(
            risk_level=risk_level,
            safe_default=safe_default,
            requires_confirmation=requires_confirmation,
            requires_local_software=requires_local_software,
            current_status=current_status,
            read_only=read_only,
        ),
    }


def build_tool_definitions() -> list[dict[str, Any]]:
    return [
        _tool("ps.probe", "Photoshop Probe", "Probe node_proxy_uxp, COM, and mock Photoshop bridge readiness.", probe_schema(), risk_level="safe_read_only", safe_default=True, requires_confirmation=False, requires_local_software=False, current_status="experimental", read_only=True),
        _tool("ps.document.info", "Photoshop Document Info", "Inspect the active Photoshop document through node_proxy_uxp first, then COM, then mock.", document_info_schema(), risk_level="safe_read_only", safe_default=True, requires_confirmation=False, requires_local_software=False, current_status="experimental", read_only=True),
        _tool("ps.layers.list", "Photoshop Layers List", "List the active Photoshop layer tree through node_proxy_uxp first, then COM, then mock.", layers_list_schema(), risk_level="safe_read_only", safe_default=True, requires_confirmation=False, requires_local_software=False, current_status="experimental", read_only=True),
        _tool("ps.selection.subject", "Photoshop Subject Selection", "Plan subject-selection work on sandbox copies only.", selection_subject_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.layer.rename", "Photoshop Layer Rename", "Plan a layer rename limited to sandbox copies.", layer_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.layer.move", "Photoshop Layer Move", "Plan a layer move limited to sandbox copies.", layer_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.layer.visibility", "Photoshop Layer Visibility", "Plan a layer visibility change limited to sandbox copies.", layer_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.preview.export", "Photoshop Preview Export", "Export a sandbox preview through node_proxy_uxp when available, otherwise fall back safely.", preview_export_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="experimental", read_only=False),
        _tool("ps.camera_raw.tune", "Photoshop Camera Raw Tune", "Plan and validate Camera Raw tuning parameters; confirmed apply is blocked until a verified BatchPlay descriptor fixture exists.", camera_raw_tune_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="experimental", read_only=False),
        _tool("ps.evidence.capture", "Photoshop Evidence Capture", "Capture an EvidenceManifest JSON for a local Photoshop job.", evidence_capture_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=False, current_status="experimental", read_only=False),
        _tool("ps.batchplay.validate", "BatchPlay Validate", "Validate typed BatchPlay descriptors against the Python allowlist.", batchplay_validate_schema(), risk_level="safe_read_only", safe_default=True, requires_confirmation=False, requires_local_software=False, current_status="experimental", read_only=True),
        _tool("ps.batchplay.execute_confirmed", "BatchPlay Execute Confirmed", "Execute an allowlisted typed BatchPlay request on sandbox copies only.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="experimental", read_only=False),
        _tool("ps.script.execute_confirmed", "Photoshop Script Execute Confirmed", "Arbitrary script execution is disabled.", disabled_confirmed_write_schema(), risk_level="guarded_local_process", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.history.undo", "Photoshop History Undo", "History mutation remains disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.mask.refine", "Photoshop Mask Refine", "Mask refinement remains disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.smartobject.place", "Photoshop Smart Object Place", "Smart object placement remains disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.adjustment.apply", "Photoshop Adjustment Apply", "Adjustment application remains disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.text.edit", "Photoshop Text Edit", "Text edits remain disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
        _tool("ps.export.psd_copy", "Photoshop PSD Copy Export", "PSD copy export remains disabled outside the typed sandbox path.", disabled_confirmed_write_schema(), risk_level="guarded_local_write", safe_default=False, requires_confirmation=True, requires_local_software=True, current_status="planned", read_only=False),
    ]
