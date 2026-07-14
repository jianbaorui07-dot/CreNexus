from __future__ import annotations

import re
from typing import Any

from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vectorization.v1"
REFERENCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUPPORTED_MEDIA_TYPES = {"image/png", "image/jpeg"}
SUPPORTED_STRATEGIES = {
    "local_illustrator_trace",
    "semantic_reconstruction",
    "hybrid",
}

DEFAULT_TRACE: dict[str, Any] = {
    "mode": "color",
    "fills": True,
    "strokes": False,
    "max_colors": 64,
    "path_fitting": 1.5,
    "min_area": 2,
    "preprocess_blur": 0.0,
    "ignore_white": False,
    "output_to_swatches": True,
}

DEFAULT_QUALITY_GATES: dict[str, Any] = {
    "aspect_ratio_error_max": 0.02,
    "silhouette_iou_min": 0.96,
    "mean_delta_e_max": 4.0,
    "p95_delta_e_max": 10.0,
    "perceptual_similarity_min": 0.95,
    "max_anchor_count": 200_000,
}

HARD_GATE_NAMES = (
    "reference_authorized",
    "primary_silhouette_present",
    "topology_valid",
    "editable_vector_present",
    "safe_output_scope",
)


def _number(
    value: Any,
    *,
    name: str,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> int | float:
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected):
        kind = "an integer" if integer else "a number"
        raise ValueError(f"{name} must be {kind}")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return int(value) if integer else float(value)


def _optional_dimension(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return int(_number(value, name=name, minimum=1, maximum=32768, integer=True))


def _boolean(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _reference_id(arguments: dict[str, Any]) -> str:
    reference_id = str(arguments.get("reference_id") or "")
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValueError("reference_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")
    return reference_id


def _trace_options(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "color",
        "fills": True,
        "strokes": False,
        "max_colors": _number(
            arguments.get("max_colors", DEFAULT_TRACE["max_colors"]),
            name="max_colors",
            minimum=2,
            maximum=256,
            integer=True,
        ),
        "path_fitting": _number(
            arguments.get("path_fitting", DEFAULT_TRACE["path_fitting"]),
            name="path_fitting",
            minimum=0,
            maximum=10,
        ),
        "min_area": _number(
            arguments.get("min_area", DEFAULT_TRACE["min_area"]),
            name="min_area",
            minimum=1,
            maximum=1000,
            integer=True,
        ),
        "preprocess_blur": _number(
            arguments.get("preprocess_blur", DEFAULT_TRACE["preprocess_blur"]),
            name="preprocess_blur",
            minimum=0,
            maximum=2,
        ),
        "ignore_white": _boolean(arguments, "ignore_white", False),
        "output_to_swatches": _boolean(arguments, "output_to_swatches", True),
    }


def build_color_vectorization_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a local-first plan without opening the input image or Adobe apps."""

    reference_id = _reference_id(arguments)
    authorized = arguments.get("reference_authorized") is True
    if not authorized:
        return sanitize(
            {
                "ok": False,
                "bridge": "illustrator",
                "action": "color_vectorize_plan",
                "schema_version": SCHEMA_VERSION,
                "reference_id": reference_id,
                "reference_authorized": False,
                "verdict": "blocked",
                "warnings": ["reference_authorized=true is required before planning image use."],
            }
        )

    media_type = str(arguments.get("source_media_type") or "image/png")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ValueError("source_media_type must be image/png or image/jpeg")

    strategy = str(arguments.get("strategy") or "hybrid")
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError("unsupported color vectorization strategy")

    photoshop_enabled = _boolean(arguments, "photoshop_preprocess", False)
    preprocess = {
        "enabled": photoshop_enabled,
        "app": "photoshop",
        "normalize_srgb": _boolean(arguments, "normalize_srgb", True),
        "max_dimension": _number(
            arguments.get("max_dimension", 4096),
            name="max_dimension",
            minimum=256,
            maximum=8192,
            integer=True,
        ),
        "median_radius": _number(
            arguments.get("median_radius", 0),
            name="median_radius",
            minimum=0,
            maximum=5,
            integer=True,
        ),
        "output_dir": "examples/output/photoshop",
        "sandbox_copy_before_photoshop": True,
    }
    trace = _trace_options(arguments)
    plan = {
        "ok": True,
        "bridge": "illustrator",
        "action": "color_vectorize_plan",
        "verdict": "planned",
        "schema_version": SCHEMA_VERSION,
        "reference_id": reference_id,
        "reference_authorized": True,
        "source": {
            "media_type": media_type,
            "width": _optional_dimension(arguments.get("source_width"), "source_width"),
            "height": _optional_dimension(arguments.get("source_height"), "source_height"),
            "pixels_read_by_plan": False,
        },
        "strategy": strategy,
        "application_matrix": [
            {
                "app": "starbridge",
                "role": "authorization_and_plan",
                "enabled": True,
                "operations": [
                    "validate explicit single-file authorization",
                    "bind trace settings and quality gates",
                ],
            },
            {
                "app": "photoshop",
                "role": "optional_preprocess_copy",
                "enabled": photoshop_enabled,
                "operations": [
                    "copy the explicit source into the Photoshop sandbox before opening it",
                    "normalize the sandbox copy to sRGB when enabled",
                    "convert the sandbox copy to 8-bit channels",
                    "downscale only when the longest edge exceeds max_dimension",
                    "apply an optional bounded median filter",
                    "export an alpha-preserving sandbox PNG and evidence manifest",
                ],
            },
            {
                "app": "illustrator",
                "role": "color_trace_and_expand",
                "enabled": strategy in {"local_illustrator_trace", "hybrid"},
                "operations": [
                    "place explicit raster in a new RGB document",
                    "trace with fixed color options",
                    "redraw, collect trace metrics, and expand",
                    "export editable vector and PNG preview",
                ],
            },
            {
                "app": "starbridge",
                "role": "quality_gate",
                "enabled": True,
                "operations": [
                    "accept externally measured silhouette and color metrics",
                    "return pass, repair_needed, or blocked",
                ],
            },
        ],
        "preprocess": preprocess,
        "trace": trace,
        "quality_gates": dict(DEFAULT_QUALITY_GATES),
        "outputs": {
            "output_dir": "examples/output/illustrator",
            "svg": True,
            "illustrator_document": True,
            "preview_png": True,
        },
        "safety": {
            "input_policy": "single_explicit_user_file",
            "recursive_scan": False,
            "cloud_upload": False,
            "arbitrary_script": False,
            "visual_review_required": True,
        },
        "dry_run": True,
        "confirm_write": False,
        "confirm_export": False,
    }
    return sanitize(plan)


def _metric(
    metrics: dict[str, Any],
    name: str,
    *,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> int | float:
    if name not in metrics:
        raise ValueError(f"missing metric: {name}")
    return _number(
        metrics[name],
        name=name,
        minimum=minimum,
        maximum=maximum,
        integer=integer,
    )


def validate_color_vectorization_metrics(
    *,
    metrics: dict[str, Any],
    hard_gates: dict[str, Any],
    quality_gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate sanitized caller-provided evidence without reading image files."""

    if not isinstance(metrics, dict) or not isinstance(hard_gates, dict):
        raise ValueError("metrics and hard_gates must be objects")

    gates = dict(DEFAULT_QUALITY_GATES)
    if quality_gates:
        gates.update(quality_gates)
    validated_gates = {
        "aspect_ratio_error_max": _number(
            gates["aspect_ratio_error_max"],
            name="aspect_ratio_error_max",
            minimum=0,
            maximum=1,
        ),
        "silhouette_iou_min": _number(
            gates["silhouette_iou_min"],
            name="silhouette_iou_min",
            minimum=0,
            maximum=1,
        ),
        "mean_delta_e_max": _number(
            gates["mean_delta_e_max"],
            name="mean_delta_e_max",
            minimum=0,
            maximum=100,
        ),
        "p95_delta_e_max": _number(
            gates["p95_delta_e_max"],
            name="p95_delta_e_max",
            minimum=0,
            maximum=100,
        ),
        "perceptual_similarity_min": _number(
            gates["perceptual_similarity_min"],
            name="perceptual_similarity_min",
            minimum=0,
            maximum=1,
        ),
        "max_anchor_count": _number(
            gates["max_anchor_count"],
            name="max_anchor_count",
            minimum=1,
            maximum=1_000_000,
            integer=True,
        ),
    }
    measured = {
        "aspect_ratio_error": _metric(metrics, "aspect_ratio_error", minimum=0, maximum=10),
        "silhouette_iou": _metric(metrics, "silhouette_iou", minimum=0, maximum=1),
        "mean_delta_e": _metric(metrics, "mean_delta_e", minimum=0, maximum=300),
        "p95_delta_e": _metric(metrics, "p95_delta_e", minimum=0, maximum=300),
        "perceptual_similarity": _metric(metrics, "perceptual_similarity", minimum=0, maximum=1),
        "anchor_count": _metric(
            metrics,
            "anchor_count",
            minimum=0,
            maximum=1_000_000,
            integer=True,
        ),
        "used_color_count": _metric(
            metrics,
            "used_color_count",
            minimum=0,
            maximum=256,
            integer=True,
        ),
    }

    failed_hard_gates = [name for name in HARD_GATE_NAMES if hard_gates.get(name) is not True]
    findings: list[dict[str, str]] = []
    for name in failed_hard_gates:
        findings.append(
            {
                "code": f"hard_gate_{name}",
                "severity": "critical",
                "message": f"Hard gate failed: {name}.",
            }
        )

    checks = (
        (
            measured["aspect_ratio_error"] > validated_gates["aspect_ratio_error_max"],
            "aspect_ratio_error_high",
            "Aspect ratio error is above the configured maximum.",
        ),
        (
            measured["silhouette_iou"] < validated_gates["silhouette_iou_min"],
            "silhouette_iou_low",
            "Silhouette overlap is below the configured minimum.",
        ),
        (
            measured["mean_delta_e"] > validated_gates["mean_delta_e_max"],
            "mean_delta_e_high",
            "Mean color difference is above the configured maximum.",
        ),
        (
            measured["p95_delta_e"] > validated_gates["p95_delta_e_max"],
            "p95_delta_e_high",
            "Tail color difference is above the configured maximum.",
        ),
        (
            measured["perceptual_similarity"] < validated_gates["perceptual_similarity_min"],
            "perceptual_similarity_low",
            "Perceptual similarity is below the configured minimum.",
        ),
        (
            measured["anchor_count"] > validated_gates["max_anchor_count"],
            "anchor_count_high",
            "Anchor count exceeds the editability budget.",
        ),
    )
    for failed, code, message in checks:
        if failed:
            findings.append({"code": code, "severity": "warn", "message": message})

    if failed_hard_gates:
        verdict = "blocked"
    elif findings:
        verdict = "repair_needed"
    else:
        verdict = "pass"

    return sanitize(
        {
            "ok": verdict != "blocked",
            "bridge": "illustrator",
            "action": "color_vectorize_validate",
            "verdict": verdict,
            "metrics": measured,
            "quality_gates": validated_gates,
            "hard_gates": {name: hard_gates.get(name) is True for name in HARD_GATE_NAMES},
            "findings": findings,
            "pixels_read": False,
        }
    )
