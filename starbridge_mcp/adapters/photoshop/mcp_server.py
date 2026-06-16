from __future__ import annotations

from pathlib import Path

from .bridge import PhotoshopBridgeAdapter
from .tools import build_tool_definitions


REPO_ROOT = Path(__file__).resolve().parents[3]
_ADAPTER = PhotoshopBridgeAdapter(REPO_ROOT)

TOOL_DEFINITIONS = build_tool_definitions()
TOOL_HANDLERS = {
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
    "ps.batchplay.validate": _ADAPTER.batchplay_validate,
    "ps.batchplay.execute_confirmed": _ADAPTER.batchplay_execute_confirmed,
    "ps.script.execute_confirmed": lambda arguments: _ADAPTER.disabled_write("ps.script.execute_confirmed", arguments),
    "ps.history.undo": lambda arguments: _ADAPTER.disabled_write("ps.history.undo", arguments),
    "ps.mask.refine": lambda arguments: _ADAPTER.disabled_write("ps.mask.refine", arguments),
    "ps.smartobject.place": lambda arguments: _ADAPTER.disabled_write("ps.smartobject.place", arguments),
    "ps.adjustment.apply": lambda arguments: _ADAPTER.disabled_write("ps.adjustment.apply", arguments),
    "ps.text.edit": lambda arguments: _ADAPTER.disabled_write("ps.text.edit", arguments),
    "ps.export.psd_copy": lambda arguments: _ADAPTER.disabled_write("ps.export.psd_copy", arguments),
}
