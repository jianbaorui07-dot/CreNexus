from __future__ import annotations

import re
from typing import Any

from starbridge_mcp.core.color_vectorization import REFERENCE_ID_PATTERN
from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vector-preprocess.v1"
SUPPORTED_MEDIA_TYPES = {"image/png", "image/jpeg"}
OUTPUT_DIR_PATTERN = re.compile(r"^examples/output/photoshop(?:/[a-z0-9][a-z0-9_-]{0,63})*$")


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _optional_dimension(value: Any, *, name: str) -> int | None:
    if value is None:
        return None
    return _integer(value, name=name, minimum=1, maximum=32768)


def _boolean(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _output_dir(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("output_dir") or "examples/output/photoshop").replace("\\", "/")
    if not OUTPUT_DIR_PATTERN.fullmatch(value):
        raise ValueError("output_dir must stay inside examples/output/photoshop")
    return value


def build_color_preprocess_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    """Plan Photoshop preparation without reading an image or starting Photoshop."""

    reference_id = str(arguments.get("reference_id") or "")
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValueError("reference_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")
    if arguments.get("reference_authorized") is not True:
        return sanitize(
            {
                "ok": False,
                "bridge": "photoshop",
                "action": "color_preprocess_plan",
                "schema_version": SCHEMA_VERSION,
                "reference_id": reference_id,
                "reference_authorized": False,
                "verdict": "blocked",
                "error_code": "authorization_required",
                "warnings": ["reference_authorized=true is required before planning image use."],
            }
        )

    media_type = str(arguments.get("source_media_type") or "image/png")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ValueError("source_media_type must be image/png or image/jpeg")

    max_dimension = _integer(
        arguments.get("max_dimension", 4096),
        name="max_dimension",
        minimum=256,
        maximum=8192,
    )
    median_radius = _integer(
        arguments.get("median_radius", 0),
        name="median_radius",
        minimum=0,
        maximum=5,
    )
    normalize_srgb = _boolean(arguments, "normalize_srgb", True)
    output_dir = _output_dir(arguments)

    operations = [
        "copy the explicit source into the Photoshop sandbox before opening it",
        "convert the sandbox copy to RGB while preserving appearance",
        (
            "convert the sandbox copy to sRGB IEC61966-2.1"
            if normalize_srgb
            else "preserve the sandbox copy color profile"
        ),
        "convert the sandbox copy to 8-bit channels for Illustrator compatibility",
        "downscale only when the longest edge exceeds max_dimension",
        (
            f"apply a {median_radius}px median filter to reduce trace fragments"
            if median_radius
            else "preserve source detail without median filtering"
        ),
        "export a new alpha-preserving PNG and a redacted EvidenceManifest",
    ]
    return sanitize(
        {
            "ok": True,
            "bridge": "photoshop",
            "action": "color_preprocess_plan",
            "verdict": "planned",
            "schema_version": SCHEMA_VERSION,
            "reference_id": reference_id,
            "reference_authorized": True,
            "source": {
                "media_type": media_type,
                "width": _optional_dimension(arguments.get("source_width"), name="source_width"),
                "height": _optional_dimension(arguments.get("source_height"), name="source_height"),
                "pixels_read_by_plan": False,
            },
            "settings": {
                "normalize_srgb": normalize_srgb,
                "max_dimension": max_dimension,
                "median_radius": median_radius,
                "output_bit_depth": 8,
                "preserve_alpha": True,
                "no_upscale": True,
            },
            "operations": operations,
            "outputs": {
                "output_dir": output_dir,
                "source_copy": True,
                "prepared_png": True,
                "evidence_manifest": True,
            },
            "safety": {
                "input_policy": "single_explicit_user_file",
                "sandbox_copy_before_photoshop": True,
                "original_modified": False,
                "recursive_scan": False,
                "cloud_upload": False,
                "arbitrary_script": False,
                "photoshop_started_by_plan": False,
                "visual_review_required": True,
            },
            "dry_run": True,
            "confirm_write": False,
            "confirm_export": False,
        }
    )
