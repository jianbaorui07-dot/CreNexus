"""Public-safe Jianying/CapCut draft-plan bridge prototype.

This module creates draft plans only. It never writes into a real Jianying or
CapCut draft directory by default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BRIDGE = "jianying"
DRAFT_ENV_VARS = ("JIANYING_DRAFTS_DIR", "CAPCUT_DRAFTS_DIR")
SAFE_OUTPUT_ENV = "STARBRIDGE_JIANYING_SAFE_OUTPUT_DIR"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_safe_output_dir() -> Path:
    return _repo_root() / "examples" / "jianying" / "output"


def _response(
    *,
    ok: bool,
    action: str,
    message: str,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "bridge": BRIDGE,
        "action": action,
        "message": message,
        "details": details or {},
        "warnings": warnings or [],
        "next_steps": next_steps or [],
    }


def _load_json(value: Any, label: str) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            return None, f"Invalid {label} JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, f"{label} JSON must decode to an object/dict."
        return parsed, None
    if isinstance(value, dict):
        return value, None
    return None, f"{label} must be a dict or JSON string."


def status() -> dict[str, Any]:
    """Check draft environment variables without reading or writing drafts."""
    env_status = {}
    configured = False
    existing = False
    for name in DRAFT_ENV_VARS:
        raw = os.environ.get(name, "").strip()
        exists = bool(raw) and Path(raw).exists()
        configured = configured or bool(raw)
        existing = existing or exists
        env_status[name] = {"configured": bool(raw), "exists": exists}

    details = {
        "draft_env": env_status,
        "safe_output_dir": str(_default_safe_output_dir()),
        "safe_output_env": SAFE_OUTPUT_ENV,
    }
    if configured and existing:
        return _response(
            ok=True,
            action="status",
            message="A Jianying/CapCut draft directory environment variable is configured.",
            details=details,
            warnings=["This bridge still writes draft plans only; it will not write into the real draft directory."],
            next_steps=["Use create_draft_plan and export to examples/jianying/output for safe testing."],
        )

    return _response(
        ok=False,
        action="status",
        message="No usable Jianying/CapCut draft directory is configured.",
        details=details,
        warnings=["This is expected on machines without Jianying/CapCut configuration."],
        next_steps=[
            "Set JIANYING_DRAFTS_DIR or CAPCUT_DRAFTS_DIR only when you need read-only local checks.",
            "Do not export generated plans into a real draft directory.",
        ],
    )


def validate_draft_schema(draft_json: Any) -> dict[str, Any]:
    """Validate a StarBridge draft plan structure without writing files."""
    draft, error = _load_json(draft_json, "draft")
    if error:
        return _response(
            ok=False,
            action="validate_draft_schema",
            message="Draft schema validation failed.",
            details={"error": error},
            warnings=["Draft input is not a JSON object."],
            next_steps=["Pass a draft plan dict or JSON string."],
        )

    required = ("draft", "timeline")
    missing = [name for name in required if name not in draft]
    timeline = draft.get("timeline")
    tracks = timeline.get("tracks") if isinstance(timeline, dict) else None
    if missing or not isinstance(tracks, list):
        return _response(
            ok=False,
            action="validate_draft_schema",
            message="Draft schema validation failed.",
            details={"missing": missing, "has_tracks": isinstance(tracks, list)},
            warnings=["Draft plan must include draft metadata and timeline.tracks list."],
            next_steps=["Generate the plan with create_draft_plan or fix the schema."],
        )

    return _response(
        ok=True,
        action="validate_draft_schema",
        message="Draft plan schema looks usable.",
        details={"track_count": len(tracks), "safe_plan": bool(draft.get("safe_plan", False))},
        next_steps=["Export only to examples/jianying/output or another explicit safe test directory."],
    )


def create_draft_plan(timeline_spec: Any) -> dict[str, Any]:
    """Create a safe draft plan from clips/texts/audio/subtitles spec."""
    spec, error = _load_json(timeline_spec, "timeline_spec")
    if error:
        return _response(
            ok=False,
            action="create_draft_plan",
            message="Could not create draft plan.",
            details={"error": error},
            warnings=["Timeline spec is not a JSON object."],
            next_steps=["Pass a dict or JSON string containing clips, texts, audio, or subtitles."],
        )

    tracks = []
    for track_name in ("clips", "texts", "audio", "subtitles"):
        items = spec.get(track_name, [])
        if items is None:
            items = []
        if not isinstance(items, list):
            return _response(
                ok=False,
                action="create_draft_plan",
                message="Could not create draft plan.",
                details={"field": track_name},
                warnings=[f"{track_name} must be a list."],
                next_steps=["Fix the timeline spec and retry."],
            )
        tracks.append({"type": track_name, "items": items})

    plan = {
        "schema_version": "starbridge.draft_plan.v1",
        "safe_plan": True,
        "draft": {
            "name": spec.get("name", "starbridge_safe_draft_plan"),
            "canvas": spec.get("canvas", {"width": 1080, "height": 1920, "fps": 30}),
            "writes_real_draft": False,
        },
        "timeline": {
            "duration_ms": spec.get("duration_ms", 0),
            "tracks": tracks,
        },
        "safety": {
            "real_draft_write_disabled": True,
            "allowed_export_root": "examples/jianying/output",
            "notes": [
                "This is a planning artifact only.",
                "Placeholder media paths must be replaced by the user in a safe local workflow.",
            ],
        },
    }

    return _response(
        ok=True,
        action="create_draft_plan",
        message="Safe Jianying/CapCut draft plan created.",
        details={"plan": plan, "track_count": len(tracks)},
        warnings=["No real Jianying/CapCut draft directory was modified."],
        next_steps=["Validate the plan, then export to examples/jianying/output for inspection."],
    )


def _safe_output_root() -> Path:
    configured = os.environ.get(SAFE_OUTPUT_ENV, "").strip()
    if configured:
        return Path(configured).resolve()
    return _default_safe_output_dir().resolve()


def _is_safe_output_path(output_path: Path, safe_root: Path) -> bool:
    try:
        output_path.resolve().relative_to(safe_root)
        return True
    except ValueError:
        return False


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_repo_root()).as_posix()
    except ValueError:
        return "<safe-output-dir>"


def export_draft_plan(plan: Any, output_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Export a draft plan to a safe test directory only."""
    draft, error = _load_json(plan, "plan")
    if error:
        return _response(
            ok=False,
            action="export_draft_plan",
            message="Draft plan was not exported.",
            details={"error": error},
            warnings=["Plan input is not a JSON object."],
            next_steps=["Create a plan with create_draft_plan first."],
        )

    validation = validate_draft_schema(draft)
    if not validation["ok"]:
        return _response(
            ok=False,
            action="export_draft_plan",
            message="Draft plan was not exported because validation failed.",
            details={"validation": validation["details"]},
            warnings=validation["warnings"],
            next_steps=validation["next_steps"],
        )

    safe_root = _safe_output_root()
    target = Path(output_path)
    if not target.is_absolute():
        target = (_repo_root() / target).resolve()
    else:
        target = target.resolve()

    if not _is_safe_output_path(target, safe_root):
        return _response(
            ok=False,
            action="export_draft_plan",
            message="Refused to export draft plan outside the safe test directory.",
            details={"output_path": _display_path(target), "safe_root": _display_path(safe_root)},
            warnings=["Exporting into a real Jianying/CapCut draft directory is blocked."],
            next_steps=[f"Use a path under {_display_path(safe_root)} or set {SAFE_OUTPUT_ENV} to an explicit safe test directory."],
        )

    safe_root.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _response(
        ok=True,
        action="export_draft_plan",
        message="Draft plan exported to safe test directory.",
        details={"output_path": _display_path(target), "safe_root": _display_path(safe_root)},
        warnings=["This file is a plan only, not a real Jianying/CapCut draft."],
        next_steps=["Inspect the JSON before building any real draft writer."],
    )
