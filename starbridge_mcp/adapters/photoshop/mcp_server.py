from __future__ import annotations

from pathlib import Path

from .bridge import PhotoshopBridgeAdapter
from .recipe_dsl import build_batch_plan, capability_manifest, compile_recipe, verify_result
from .tools import build_tool_definitions

REPO_ROOT = Path(__file__).resolve().parents[3]
_ADAPTER = PhotoshopBridgeAdapter(REPO_ROOT)

TOOL_DEFINITIONS = build_tool_definitions()
TOOL_HANDLERS = {
    "ps.capabilities": lambda _arguments: capability_manifest(),
    "ps.recipe.compile": lambda arguments: compile_recipe(
        str(arguments.get("recipe_id") or ""),
        arguments.get("parameters") if isinstance(arguments.get("parameters"), dict) else {},
    ),
    "ps.batch.plan": lambda arguments: build_batch_plan(
        list(arguments.get("items") or []),
        completed_item_ids=list(arguments.get("completed_item_ids") or []),
    ),
    "ps.result.verify": verify_result,
    "ps.probe": _ADAPTER.probe,
    "ps.document.info": _ADAPTER.document_info,
    "ps.layers.list": _ADAPTER.layers_list,
    "ps.selection.subject": _ADAPTER.selection_subject,
    "ps.layer.rename": _ADAPTER.layer_rename,
    "ps.layer.move": _ADAPTER.layer_move,
    "ps.layer.visibility": _ADAPTER.layer_visibility,
    "ps.preview.export": _ADAPTER.preview_export,
    "ps.camera_raw.tune": _ADAPTER.camera_raw_tune,
    "ps.evidence.capture": _ADAPTER.evidence_capture,
    "ps.get_preview": _ADAPTER.get_preview,
    "ps.get_state": _ADAPTER.get_state,
    "ps.batchplay.validate": _ADAPTER.batchplay_validate,
    "ps.batchplay.execute_confirmed": _ADAPTER.batchplay_execute_confirmed,
    "ps.script.execute_confirmed": lambda arguments: _ADAPTER.disabled_write(
        "ps.script.execute_confirmed", arguments
    ),
    "ps.history.undo": lambda arguments: _ADAPTER.disabled_write("ps.history.undo", arguments),
    "ps.mask.refine": lambda arguments: _ADAPTER.disabled_write("ps.mask.refine", arguments),
    "ps.smartobject.place": lambda arguments: _ADAPTER.disabled_write(
        "ps.smartobject.place", arguments
    ),
    "ps.adjustment.apply": lambda arguments: _ADAPTER.disabled_write(
        "ps.adjustment.apply", arguments
    ),
    "ps.text.edit": lambda arguments: _ADAPTER.disabled_write("ps.text.edit", arguments),
    "ps.export.psd_copy": lambda arguments: _ADAPTER.disabled_write(
        "ps.export.psd_copy", arguments
    ),
}
