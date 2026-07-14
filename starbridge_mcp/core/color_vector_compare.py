from __future__ import annotations

import hashlib
import math
import warnings
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Any

from starbridge_mcp.core.color_vectorization import (
    REFERENCE_ID_PATTERN,
    validate_color_vectorization_metrics,
)
from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vector-comparison.v1"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
MAX_SAMPLED_PIXELS = 65_536
REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _explicit_file(
    value: Any,
    *,
    repo_root: Path,
    suffixes: set[str],
    label: str,
    stay_inside: Path | None = None,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must identify one explicit image file")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    path = path.resolve()
    if stay_inside is not None:
        try:
            path.relative_to(stay_inside)
        except ValueError as error:
            raise ValueError(
                "candidate preview must stay inside the Illustrator sandbox"
            ) from error
    if path.suffix.lower() not in suffixes:
        raise ValueError(f"{label} has an unsupported image format")
    if not path.is_file():
        raise ValueError(f"{label} was not found")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"{label} exceeds the 64 MiB safety limit")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trace_evidence(arguments: dict[str, Any]) -> dict[str, int]:
    value = arguments.get("trace_evidence")
    if not isinstance(value, dict):
        raise ValueError("trace_evidence must be an object")
    return {
        "anchor_count": _integer(
            value.get("anchor_count"),
            name="anchor_count",
            minimum=0,
            maximum=1_000_000,
        ),
        "used_color_count": _integer(
            value.get("used_color_count"),
            name="used_color_count",
            minimum=0,
            maximum=256,
        ),
        "open_path_count": _integer(
            value.get("open_path_count"),
            name="open_path_count",
            minimum=0,
            maximum=1_000_000,
        ),
        "embedded_raster_count": _integer(
            value.get("embedded_raster_count"),
            name="embedded_raster_count",
            minimum=0,
            maximum=1_000_000,
        ),
    }


def _load_srgb(path: Path) -> tuple[Any, str]:
    try:
        from PIL import Image, ImageCms, ImageOps
    except ImportError as error:
        raise RuntimeError(
            'Pillow is required; install the Adobe extra with python -m pip install -e ".[adobe]"'
        ) from error

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as opened:
            opened.load()
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValueError("image exceeds the decoded pixel safety limit")
            image = ImageOps.exif_transpose(opened)
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            rgb = image.convert("RGB")
            icc_profile = opened.info.get("icc_profile")

    icc_status = "absent"
    if icc_profile:
        try:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            target_profile = ImageCms.createProfile("sRGB")
            rgb = ImageCms.profileToProfile(
                rgb,
                source_profile,
                target_profile,
                outputMode="RGB",
            )
            icc_status = "applied"
        except (OSError, ValueError, TypeError):
            icc_status = "fallback"

    if alpha is None:
        return rgb, icc_status
    rgba = rgb.copy()
    rgba.putalpha(alpha)
    return rgba, icc_status


def _normalized_size(width: int, height: int, max_dimension: int) -> tuple[int, int]:
    scale = min(1.0, max_dimension / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _resized(image: Any, size: tuple[int, int]) -> Any:
    from PIL import Image

    if image.size == size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)


def _rgb_and_mask(image: Any, threshold: int) -> tuple[list[tuple[int, int, int]], list[bool], str]:
    from PIL import Image

    rgba = image.convert("RGBA")
    alpha = list(rgba.getchannel("A").tobytes())
    rgb_image = Image.new("RGB", rgba.size, "white")
    rgb_image.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
    rgb_bytes = rgb_image.tobytes()
    rgb = list(zip(rgb_bytes[0::3], rgb_bytes[1::3], rgb_bytes[2::3], strict=True))

    if alpha and min(alpha) < 250:
        return rgb, [value > 16 for value in alpha], "alpha"

    width, height = rgb_image.size
    corners = (
        rgb[0],
        rgb[width - 1],
        rgb[(height - 1) * width],
        rgb[-1],
    )
    background = tuple(round(sum(pixel[channel] for pixel in corners) / 4) for channel in range(3))
    threshold_squared = threshold * threshold
    mask = [
        sum((pixel[channel] - background[channel]) ** 2 for channel in range(3)) > threshold_squared
        for pixel in rgb
    ]
    if sum(mask) < max(1, round(len(mask) * 0.005)):
        mask = [True] * len(mask)
    return rgb, mask, "corner_background"


def _silhouette_metrics(reference: list[bool], candidate: list[bool]) -> tuple[float, float, float]:
    union = sum(left or right for left, right in zip(reference, candidate, strict=True))
    intersection = sum(left and right for left, right in zip(reference, candidate, strict=True))
    total = max(1, len(reference))
    iou = intersection / union if union else 0.0
    return iou, sum(reference) / total, sum(candidate) / total


def _srgb_channel(value: int) -> float:
    normalized = value / 255.0
    if normalized <= 0.04045:
        return normalized / 12.92
    return ((normalized + 0.055) / 1.055) ** 2.4


def _lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = (_srgb_channel(channel) for channel in rgb)
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / 0.95047
    y = 0.2126729 * red + 0.7151522 * green + 0.0721750 * blue
    z = (0.0193339 * red + 0.1191920 * green + 0.9503041 * blue) / 1.08883

    delta = 6 / 29

    def f(value: float) -> float:
        if value > delta**3:
            return value ** (1 / 3)
        return value / (3 * delta**2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _color_delta_metrics(
    reference: list[tuple[int, int, int]], candidate: list[tuple[int, int, int]]
) -> tuple[float, float, int]:
    total = len(reference)
    stride = max(1, math.ceil(total / MAX_SAMPLED_PIXELS))
    deltas: list[float] = []
    for index in range(0, total, stride):
        left = _lab(reference[index])
        right = _lab(candidate[index])
        deltas.append(math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True))))
    return sum(deltas) / len(deltas), _percentile(deltas, 0.95), len(deltas)


def _luminance(pixel: tuple[int, int, int]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def _blocks(width: int, height: int, block_size: int = 8) -> Iterable[list[int]]:
    for top in range(0, height, block_size):
        for left in range(0, width, block_size):
            yield [
                row * width + column
                for row in range(top, min(top + block_size, height))
                for column in range(left, min(left + block_size, width))
            ]


def _block_ssim(
    reference: list[tuple[int, int, int]],
    candidate: list[tuple[int, int, int]],
    width: int,
    height: int,
) -> float:
    left_luma = [_luminance(pixel) for pixel in reference]
    right_luma = [_luminance(pixel) for pixel in candidate]
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    scores: list[float] = []
    for indices in _blocks(width, height):
        left = [left_luma[index] for index in indices]
        right = [right_luma[index] for index in indices]
        count = len(indices)
        left_mean = sum(left) / count
        right_mean = sum(right) / count
        denominator = max(1, count - 1)
        left_variance = sum((value - left_mean) ** 2 for value in left) / denominator
        right_variance = sum((value - right_mean) ** 2 for value in right) / denominator
        covariance = (
            sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
            / denominator
        )
        numerator = (2 * left_mean * right_mean + c1) * (2 * covariance + c2)
        divisor = (left_mean**2 + right_mean**2 + c1) * (left_variance + right_variance + c2)
        scores.append(numerator / divisor if divisor else 1.0)
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def compare_color_vectorization_files(
    arguments: dict[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    """Compare one authorized image with one sandbox Illustrator PNG preview."""

    reference_id = str(arguments.get("reference_id") or "")
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValueError("reference_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")
    if arguments.get("reference_authorized") is not True:
        return sanitize(
            {
                "ok": False,
                "bridge": "illustrator",
                "action": "color_vectorize_compare",
                "schema_version": SCHEMA_VERSION,
                "reference_id": reference_id,
                "reference_authorized": False,
                "verdict": "blocked",
                "error_code": "authorization_required",
                "warnings": ["reference_authorized=true is required before reading image files."],
                "safety": {
                    "paths_returned": False,
                    "pixels_retained": False,
                    "metadata_returned": False,
                    "recursive_scan": False,
                },
            }
        )

    root = repo_root.resolve()
    candidate_sandbox = (root / "examples" / "output" / "illustrator").resolve()
    reference = _explicit_file(
        arguments.get("reference_path"),
        repo_root=root,
        suffixes=REFERENCE_SUFFIXES,
        label="reference image",
    )
    candidate = _explicit_file(
        arguments.get("candidate_preview_path"),
        repo_root=root,
        suffixes={".png"},
        label="candidate preview",
        stay_inside=candidate_sandbox,
    )

    trace = _trace_evidence(arguments)
    max_dimension = _integer(
        arguments.get("max_dimension", 512),
        name="max_dimension",
        minimum=64,
        maximum=1024,
    )
    background_threshold = _integer(
        arguments.get("background_threshold", 24),
        name="background_threshold",
        minimum=1,
        maximum=128,
    )

    reference_hash = _sha256(reference)
    candidate_hash = _sha256(candidate)
    candidate_distinct = reference_hash != candidate_hash

    reference_image, reference_icc = _load_srgb(reference)
    candidate_image, candidate_icc = _load_srgb(candidate)
    reference_width, reference_height = reference_image.size
    candidate_width, candidate_height = candidate_image.size
    aspect_ratio_error = abs(
        (reference_width / reference_height) / (candidate_width / candidate_height) - 1
    )
    normalized_size = _normalized_size(reference_width, reference_height, max_dimension)
    reference_normalized = _resized(reference_image, normalized_size)
    candidate_normalized = _resized(candidate_image, normalized_size)

    reference_rgb, reference_mask, reference_mask_method = _rgb_and_mask(
        reference_normalized, background_threshold
    )
    candidate_rgb, candidate_mask, candidate_mask_method = _rgb_and_mask(
        candidate_normalized, background_threshold
    )
    silhouette_iou, reference_foreground_ratio, candidate_foreground_ratio = _silhouette_metrics(
        reference_mask, candidate_mask
    )
    mean_delta_e, p95_delta_e, sampled_pixels = _color_delta_metrics(reference_rgb, candidate_rgb)
    perceptual_similarity = _block_ssim(
        reference_rgb,
        candidate_rgb,
        normalized_size[0],
        normalized_size[1],
    )

    metrics = {
        "aspect_ratio_error": round(aspect_ratio_error, 6),
        "silhouette_iou": round(silhouette_iou, 6),
        "mean_delta_e": round(mean_delta_e, 6),
        "p95_delta_e": round(p95_delta_e, 6),
        "perceptual_similarity": round(perceptual_similarity, 6),
        "anchor_count": trace["anchor_count"],
        "used_color_count": trace["used_color_count"],
        "sampled_pixels": sampled_pixels,
        "reference_foreground_ratio": round(reference_foreground_ratio, 6),
        "candidate_foreground_ratio": round(candidate_foreground_ratio, 6),
    }
    hard_gates = {
        "reference_authorized": True,
        "primary_silhouette_present": (
            reference_foreground_ratio >= 0.005 and candidate_foreground_ratio >= 0.005
        ),
        "topology_valid": trace["open_path_count"] == 0,
        "editable_vector_present": (
            trace["anchor_count"] > 0 and trace["embedded_raster_count"] == 0
        ),
        "safe_output_scope": True,
    }
    validation = validate_color_vectorization_metrics(
        metrics=metrics,
        hard_gates=hard_gates,
    )
    findings = list(validation["findings"])
    verdict = str(validation["verdict"])
    ok = bool(validation["ok"])
    if not candidate_distinct:
        findings.insert(
            0,
            {
                "code": "candidate_matches_reference_bytes",
                "severity": "critical",
                "message": "Candidate bytes match the reference; independent vector output is not proven.",
            },
        )
        verdict = "blocked"
        ok = False
    if reference_icc == "fallback" or candidate_icc == "fallback":
        findings.append(
            {
                "code": "icc_profile_fallback",
                "severity": "info",
                "message": "An embedded ICC profile could not be applied; sRGB fallback was used.",
            }
        )

    silhouette_method = (
        reference_mask_method if reference_mask_method == candidate_mask_method else "mixed"
    )
    return sanitize(
        {
            "ok": ok,
            "bridge": "illustrator",
            "action": "color_vectorize_compare",
            "schema_version": SCHEMA_VERSION,
            "reference_id": reference_id,
            "reference_authorized": True,
            "verdict": verdict,
            "artifacts": {
                "reference_sha256": reference_hash,
                "candidate_sha256": candidate_hash,
                "candidate_distinct": candidate_distinct,
            },
            "dimensions": {
                "reference": {"width": reference_width, "height": reference_height},
                "candidate": {"width": candidate_width, "height": candidate_height},
                "normalized": {
                    "width": normalized_size[0],
                    "height": normalized_size[1],
                },
                "aspect_ratio_error": round(aspect_ratio_error, 6),
            },
            "color_management": {
                "working_space": "srgb_d65",
                "reference_icc": reference_icc,
                "candidate_icc": candidate_icc,
            },
            "methods": {
                "alignment": "bounded_resize_to_reference",
                "silhouette": silhouette_method,
                "color_delta": "cie76_d65",
                "perceptual": "block_ssim_8x8",
            },
            "metrics": metrics,
            "trace_evidence": trace,
            "hard_gates": validation["hard_gates"],
            "quality_gates": validation["quality_gates"],
            "findings": findings,
            "safety": {
                "reference_explicit": True,
                "candidate_sandboxed": True,
                "recursive_scan": False,
                "paths_returned": False,
                "pixels_retained": False,
                "metadata_returned": False,
            },
        }
    )
