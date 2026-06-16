from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CAMERA_RAW_BLOCKED_REASON = "camera_raw_batchplay_descriptor_not_recorded"
CAMERA_RAW_NEXT_STEP = "Record a verified Camera Raw Filter descriptor with Alchemist or Photoshop Action listener and add it as a fixture."
CAMERA_RAW_METHOD = "ps.camera_raw.tune"
CAMERA_RAW_PROTOCOL_VERSION = "camera_raw_tune.v1"
CAMERA_RAW_OUTPUT_DIR = "examples/output/photoshop"
CAMERA_RAW_DESCRIPTOR_ENV = "STARBRIDGE_CAMERA_RAW_DESCRIPTOR_FIXTURE"

CAMERA_RAW_PRESETS: dict[str, dict[str, float]] = {
    "blue_artwork_clean": {
        "temperature": 4800,
        "tint": 10,
        "exposure": 0.35,
        "contrast": 10,
        "highlights": -25,
        "shadows": 35,
        "whites": 12,
        "blacks": -12,
        "texture": 18,
        "clarity": 8,
        "dehaze": 3,
        "vibrance": 14,
        "saturation": -2,
    }
}

CAMERA_RAW_PARAM_RANGES: dict[str, tuple[float, float]] = {
    "temperature": (2000, 50000),
    "tint": (-150, 150),
    "exposure": (-5, 5),
    "contrast": (-100, 100),
    "highlights": (-100, 100),
    "shadows": (-100, 100),
    "whites": (-100, 100),
    "blacks": (-100, 100),
    "texture": (-100, 100),
    "clarity": (-100, 100),
    "dehaze": (-100, 100),
    "vibrance": (-100, 100),
    "saturation": (-100, 100),
}

CAMERA_RAW_XMP_FIELDS = {
    "temperature": "Temperature",
    "tint": "Tint",
    "exposure": "Exposure2012",
    "contrast": "Contrast2012",
    "highlights": "Highlights2012",
    "shadows": "Shadows2012",
    "whites": "Whites2012",
    "blacks": "Blacks2012",
    "texture": "Texture",
    "clarity": "Clarity2012",
    "dehaze": "Dehaze",
    "vibrance": "Vibrance",
    "saturation": "Saturation",
}


def resolve_camera_raw_output_dir(repo_root: Path, requested: str | None) -> Path:
    output_dir = str(requested or CAMERA_RAW_OUTPUT_DIR).replace("\\", "/")
    relative = Path(output_dir)
    if relative.is_absolute():
        raise ValueError(f"output.dir must be relative and stay inside {CAMERA_RAW_OUTPUT_DIR}")
    candidate = (repo_root / relative).resolve()
    allowed_root = (repo_root / CAMERA_RAW_OUTPUT_DIR).resolve()
    if not (candidate == allowed_root or allowed_root in candidate.parents):
        raise ValueError(f"output.dir must stay inside {CAMERA_RAW_OUTPUT_DIR}")
    return candidate


def _source_plan(arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw_source = arguments.get("source") or {"mode": "active_document"}
    if not isinstance(raw_source, dict):
        return {}, ["source must be an object"]
    mode = str(raw_source.get("mode") or "active_document")
    if mode not in {"active_document", "explicit_path"}:
        return {}, ["source.mode must be active_document or explicit_path"]
    source = {"mode": mode}
    if mode == "explicit_path":
        source_path = str(raw_source.get("path") or "").strip()
        if not source_path:
            return {}, ["source.path is required when source.mode is explicit_path"]
        source["path"] = source_path
        source["read_policy"] = "user_explicit_path_only"
    return source, []


def _output_plan(arguments: dict[str, Any], repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    raw_output = arguments.get("output") or {}
    if not isinstance(raw_output, dict):
        return {}, ["output must be an object"]
    output_dir = str(raw_output.get("dir") or arguments.get("output_dir") or CAMERA_RAW_OUTPUT_DIR)
    try:
        resolved = resolve_camera_raw_output_dir(repo_root, output_dir)
    except ValueError as exc:
        return {}, [str(exc)]
    formats = raw_output.get("formats") or ["jpg"]
    if not isinstance(formats, list) or not formats:
        return {}, ["output.formats must be a non-empty list"]
    normalized_formats = [str(item).lower() for item in formats]
    unsupported = [item for item in normalized_formats if item not in {"jpg", "png"}]
    if unsupported:
        return {}, [f"output.formats contains unsupported values: {', '.join(unsupported)}"]
    basename = str(raw_output.get("basename") or "camera_raw_tune_preview").strip()
    if not basename or any(mark in basename for mark in ("/", "\\", ":", "..")):
        return {}, ["output.basename must be a simple file stem"]
    return {
        "dir": resolved.relative_to(repo_root).as_posix(),
        "basename": basename,
        "formats": normalized_formats,
        "export_after_apply": bool(raw_output.get("export_after_apply", False)),
    }, []


def build_camera_raw_tune_protocol(arguments: dict[str, Any], repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    preset = str(arguments.get("preset") or "blue_artwork_clean")
    if preset not in CAMERA_RAW_PRESETS:
        return None, [f"preset must be one of: {', '.join(sorted(CAMERA_RAW_PRESETS))}"]

    provided = arguments.get("params") or {}
    if not isinstance(provided, dict):
        return None, ["params must be an object"]

    params = dict(CAMERA_RAW_PRESETS[preset])
    errors: list[str] = []
    for key, value in provided.items():
        if key not in CAMERA_RAW_PARAM_RANGES:
            errors.append(f"params.{key} is not supported")
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"params.{key} must be numeric")
            continue
        minimum, maximum = CAMERA_RAW_PARAM_RANGES[key]
        numeric = float(value)
        if numeric < minimum or numeric > maximum:
            errors.append(f"params.{key} must be between {minimum:g} and {maximum:g}")
            continue
        params[key] = numeric

    source, source_errors = _source_plan(arguments)
    output, output_errors = _output_plan(arguments, repo_root)
    errors.extend(source_errors)
    errors.extend(output_errors)
    if errors:
        return None, errors

    return {
        "protocol_version": CAMERA_RAW_PROTOCOL_VERSION,
        "method": CAMERA_RAW_METHOD,
        "preset": preset,
        "params": params,
        "xmp_settings": camera_raw_params_to_xmp_settings(params),
        "source": source,
        "output": output,
        "descriptor_status": "missing",
        "execution_path": ["Codex", "StarBridge MCP", "Node Proxy", "UXP Plugin", "Photoshop"],
        "safety": {
            "dry_run_default": True,
            "requires_confirm_apply_for_real_apply": True,
            "requires_confirm_export_for_real_export": True,
            "no_camera_raw_modal_mouse_automation": True,
            "output_dir": CAMERA_RAW_OUTPUT_DIR,
        },
    }, []


def _format_xmp_number(value: Any) -> str:
    numeric = float(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def camera_raw_params_to_xmp_settings(params: dict[str, Any]) -> dict[str, str]:
    settings: dict[str, str] = {}
    for key, field in CAMERA_RAW_XMP_FIELDS.items():
        if key in params:
            settings[field] = _format_xmp_number(params[key])
    return settings


def camera_raw_xmp_document(settings: dict[str, str]) -> str:
    attributes = "\n   ".join(f'crs:{key}="{value}"' for key, value in sorted(settings.items()))
    return f"""<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   {attributes}/>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""


def _resolve_path_value(root: dict[str, Any], dotted_path: str) -> Any:
    current: Any = root
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_path)
        current = current[part]
    return current


def render_descriptor_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [render_descriptor_template(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_descriptor_template(item, context) for key, item in value.items()}
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return _resolve_path_value(context, value[2:-2].strip())
    return value


def load_verified_descriptor_fixture(arguments: dict[str, Any], plan: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    fixture_value = arguments.get("descriptor_fixture_path") or os.environ.get(CAMERA_RAW_DESCRIPTOR_ENV)
    if not fixture_value:
        return None, []
    fixture_path = Path(str(fixture_value)).expanduser()
    if not fixture_path.exists() or not fixture_path.is_file():
        return None, ["descriptor fixture path does not exist or is not a file"]
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"descriptor fixture could not be read: {type(exc).__name__}"]
    errors: list[str] = []
    if fixture.get("protocol_version") != CAMERA_RAW_PROTOCOL_VERSION:
        errors.append("descriptor fixture protocol_version mismatch")
    if fixture.get("method") != CAMERA_RAW_METHOD:
        errors.append("descriptor fixture method mismatch")
    if fixture.get("descriptor_kind") != "camera_raw_filter":
        errors.append("descriptor fixture descriptor_kind must be camera_raw_filter")
    if fixture.get("verified") is not True:
        errors.append("descriptor fixture must set verified=true")
    raw_descriptors = fixture.get("descriptors")
    if not isinstance(raw_descriptors, list) or not raw_descriptors:
        errors.append("descriptor fixture must include a non-empty descriptors list")
    if errors:
        return None, errors
    try:
        descriptors = render_descriptor_template(raw_descriptors, {"plan": plan, "params": plan["params"], "output": plan["output"], "source": plan["source"]})
    except KeyError as exc:
        return None, [f"descriptor fixture template variable is missing: {exc}"]
    return {
        "loaded": True,
        "verified": True,
        "descriptor_kind": "camera_raw_filter",
        "descriptor_count": len(descriptors),
        "descriptors": descriptors,
    }, []
