from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "starbridge.image_to_editable_psd.v1"
GROUPS_BOTTOM_TO_TOP = (
    "04_背景",
    "03_装饰",
    "02_主体",
    "01_文字",
    "00_原始参考",
    "99_QA",
)


class ManifestError(ValueError):
    """Raised when a layer manifest cannot be built safely."""


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(payload)
    return payload


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    validate_manifest(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"Unsupported schema_version: {payload.get('schema_version')!r}")
    canvas = payload.get("canvas")
    if not isinstance(canvas, dict):
        raise ManifestError("canvas must be an object")
    for key in ("width", "height", "resolution"):
        if not isinstance(canvas.get(key), int) or canvas[key] <= 0:
            raise ManifestError(f"canvas.{key} must be a positive integer")
    layers = payload.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ManifestError("layers must be a non-empty array")
    seen: set[str] = set()
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise ManifestError(f"layers[{index}] must be an object")
        layer_id = str(layer.get("id") or "").strip()
        if not layer_id or layer_id in seen:
            raise ManifestError(f"layers[{index}].id must be unique and non-empty")
        seen.add(layer_id)
        if layer.get("group") not in GROUPS_BOTTOM_TO_TOP:
            raise ManifestError(f"layers[{index}].group is not allowlisted")
        if layer.get("type") not in {"pixel", "text"}:
            raise ManifestError(f"layers[{index}].type must be pixel or text")
        if layer.get("type") == "pixel" and not str(layer.get("source") or "").strip():
            raise ManifestError(f"layers[{index}].source is required for pixel layers")
        if layer.get("type") == "text" and "content" not in layer:
            raise ManifestError(f"layers[{index}].content is required for text layers")


def resolve_layer_sources(manifest_path: Path, payload: dict[str, Any]) -> list[Path]:
    root = manifest_path.resolve().parent
    sources: list[Path] = []
    for layer in payload["layers"]:
        if layer["type"] != "pixel":
            continue
        source = (root / str(layer["source"])).resolve()
        if not source.is_relative_to(root):
            raise ManifestError(f"Layer source escapes the job directory: {layer['source']}")
        if not source.is_file():
            raise ManifestError(f"Layer source does not exist: {layer['source']}")
        sources.append(source)
    return sources
