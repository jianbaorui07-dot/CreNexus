"""Publish sanitized Codex progress into an already-open AutoCAD session."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PHASES = {"queued", "running", "completed", "failed", "cancelled", "needs_user"}
MODES = {"structured", "computer_use"}
BRIDGES = {"photoshop", "illustrator", "autocad"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|file:|/Users/|/home/)", re.I)
_CONTROL_TEXT = re.compile(r"[\x00-\x1f\x7f]")
_UPDATE_FIELDS = {
    "type",
    "protocol_version",
    "session_id",
    "bridge",
    "mode",
    "phase",
    "step",
    "message",
    "progress",
    "at",
}
_STEP_FIELDS = {"id", "label", "index", "total"}


def _safe_identifier(value: Any, field: str) -> str:
    normalized = str(value or "")
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"{field}_must_be_safe_identifier")
    return normalized


def _safe_text(value: Any, field: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > maximum
        or _PRIVATE_PATH.search(normalized)
        or _CONTROL_TEXT.search(normalized)
    ):
        raise ValueError(f"{field}_must_be_safe_display_text")
    return normalized


def _bounded_integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field}_out_of_range")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}_out_of_range") from error
    if normalized != value or not minimum <= normalized <= maximum:
        raise ValueError(f"{field}_out_of_range")
    return normalized


def _iso_datetime(value: Any) -> str:
    if value in (None, ""):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    normalized = str(value)
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("at_must_be_iso_datetime") from error
    return normalized


def normalize_live_update(value: dict[str, Any], expected_bridge: str | None = None) -> dict[str, Any]:
    """Validate and minimize one cross-application Codex progress update."""
    if not isinstance(value, dict):
        raise ValueError("session_update_must_be_object")
    if not set(value).issubset(_UPDATE_FIELDS):
        raise ValueError("unknown_session_field")
    if value.get("type") != "codex_session" or value.get("protocol_version") != 1:
        raise ValueError("unsupported_session_protocol")

    bridge = _safe_identifier(value.get("bridge"), "bridge")
    if bridge not in BRIDGES or (expected_bridge and bridge != expected_bridge):
        raise ValueError("bridge_mismatch")
    phase = _safe_identifier(value.get("phase"), "phase")
    if phase not in PHASES:
        raise ValueError("unsupported_session_phase")
    mode = _safe_identifier(value.get("mode", "structured"), "mode")
    if mode not in MODES:
        raise ValueError("unsupported_session_mode")

    step = value.get("step")
    if not isinstance(step, dict):
        raise ValueError("step_must_be_object")
    if not set(step).issubset(_STEP_FIELDS):
        raise ValueError("unknown_step_field")
    index = _bounded_integer(step.get("index"), "step_index", 1, 1000)
    total = _bounded_integer(step.get("total"), "step_total", 1, 1000)
    if index > total:
        raise ValueError("step_index_exceeds_total")

    return {
        "type": "codex_session",
        "protocol_version": 1,
        "session_id": _safe_identifier(value.get("session_id"), "session_id"),
        "bridge": bridge,
        "mode": mode,
        "phase": phase,
        "step": {
            "id": _safe_identifier(step.get("id"), "step_id"),
            "label": _safe_text(step.get("label"), "step_label", 80),
            "index": index,
            "total": total,
        },
        "message": _safe_text(value.get("message"), "message", 160),
        "progress": _bounded_integer(value.get("progress"), "progress", 0, 100),
        "at": _iso_datetime(value.get("at")),
    }


def format_autocad_prompt(value: dict[str, Any]) -> str:
    """Create the one-line text visible in AutoCAD's command area."""
    update = normalize_live_update(value, expected_bridge="autocad")
    step = update["step"]
    return (
        f"\n[Codex {update['progress']}% · {step['index']}/{step['total']}] "
        f"{update['message']}\n"
    )


class AutoCadVisibleSession:
    """A narrow COM reporter for an already-active AutoCAD document."""

    def __init__(self, application: Any) -> None:
        self.application = application

    @classmethod
    def connect_active(cls) -> AutoCadVisibleSession:
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("pywin32_is_required_for_autocad_live_session") from error
        try:
            application = win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception as error:
            raise RuntimeError("autocad_must_already_be_open") from error
        return cls(application)

    def publish(self, value: dict[str, Any]) -> dict[str, Any]:
        update = normalize_live_update(value, expected_bridge="autocad")
        try:
            document = self.application.ActiveDocument
            self.application.Visible = True
            document.Utility.Prompt(format_autocad_prompt(update))
            document.Regen(1)
        except Exception as error:
            raise RuntimeError("autocad_live_prompt_failed") from error
        return {
            "ok": True,
            "published": True,
            "bridge": "autocad",
            "session_id": update["session_id"],
            "phase": update["phase"],
            "progress": update["progress"],
        }
