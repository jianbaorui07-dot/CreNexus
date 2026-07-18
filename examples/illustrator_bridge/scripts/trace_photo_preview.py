from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # The CLI reports the optional dependency command below.
    cv2 = None
    np = None
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageOps = None

from svg_artifact_verifier import SvgArtifactError, verify_svg_artifact

REPO_ROOT = Path(__file__).resolve().parents[3]
HEADLESS_OUTPUT_PARTS = ("examples", "output", "illustrator", "trace-practice")
DEFAULT_OUTPUT_DIR = REPO_ROOT.joinpath(*HEADLESS_OUTPUT_PARTS)
MAX_WORK_DIMENSION = 1200
MAX_ALLOWED_WORK_DIMENSION = 4096
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
ALLOWED_INPUT_FORMATS = {"JPEG", "PNG"}
SVG_QUALITY_SCHEMA_VERSION = "starbridge.headless-svg-quality.v1"
SVG_RASTER_SIMILARITY_MIN = 0.95
SVG_QUALITY_TARGET_KINDS = {
    "in_memory_quantized_target",
    "explicit_reference_work_rgb",
}
_SVG_PATH_SEGMENT = re.compile(r"M\s+(.+?)\s+Z")
_SVG_POINT = re.compile(r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)")


class TraceRunError(RuntimeError):
    """A safe, structured failure that can be returned without local paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TraceArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise TraceRunError(
            "invalid_arguments", "Required or supplied color trace arguments are invalid."
        )


@dataclass(frozen=True)
class TracePreset:
    name: str
    colors: int
    blur: int
    edge_weight: float
    canny_low: int
    canny_high: int
    min_area: float
    simplify: float
    saturation: float
    contrast: float
    note: str


PRESETS: dict[str, TracePreset] = {
    "flat_8": TracePreset(
        name="flat_8",
        colors=8,
        blur=7,
        edge_weight=0.20,
        canny_low=60,
        canny_high=150,
        min_area=110.0,
        simplify=0.010,
        saturation=1.05,
        contrast=1.04,
        note="large color blocks, low detail, easiest to edit",
    ),
    "flat_16": TracePreset(
        name="flat_16",
        colors=16,
        blur=5,
        edge_weight=0.26,
        canny_low=50,
        canny_high=140,
        min_area=75.0,
        simplify=0.008,
        saturation=1.08,
        contrast=1.06,
        note="balanced flat illustration preset",
    ),
    "line_color_16": TracePreset(
        name="line_color_16",
        colors=16,
        blur=3,
        edge_weight=0.42,
        canny_low=38,
        canny_high=120,
        min_area=45.0,
        simplify=0.006,
        saturation=1.02,
        contrast=1.12,
        note="keeps ink-like line detail over limited colors",
    ),
    "nianhua_24": TracePreset(
        name="nianhua_24",
        colors=24,
        blur=3,
        edge_weight=0.36,
        canny_low=34,
        canny_high=115,
        min_area=32.0,
        simplify=0.005,
        saturation=1.12,
        contrast=1.10,
        note="higher-detail new-year-picture style preview",
    ),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = TraceArgumentParser(
        description="Generate controllable local trace previews for Illustrator practice."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Source image path. This path is not written into the public report.",
    )
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Ignored local output directory."
    )
    parser.add_argument(
        "--presets",
        default="flat_8,flat_16,line_color_16,nianhua_24",
        help="Comma-separated preset names.",
    )
    parser.add_argument(
        "--commit-preset", default="", help="Copy one preset to final_trace.svg/final_preview.png."
    )
    parser.add_argument("--max-dimension", type=int, default=MAX_WORK_DIMENSION)
    return parser.parse_args(argv)


def require_trace_runtime() -> None:
    if any(module is None for module in (cv2, np, Image, ImageDraw, ImageFont, ImageOps)):
        raise TraceRunError(
            "missing_trace_dependency",
            'Install the optional runtime first: python -m pip install -e ".[illustrator-trace]"',
        )


def safe_output_dir(value: str) -> Path:
    target = Path(value)
    if not target.is_absolute():
        target = REPO_ROOT / target
    resolved = target.resolve()
    allowed = REPO_ROOT.joinpath(*HEADLESS_OUTPUT_PARTS).resolve()
    if not resolved.is_relative_to(allowed):
        raise TraceRunError(
            "output_outside_sandbox",
            "Output directory must stay inside examples/output/illustrator/trace-practice.",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def repo_relative_path(path: Path) -> str:
    """Return a stable public path even when Windows exposes 8.3 and long aliases."""

    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError) as exc:
        raise TraceRunError(
            "artifact_outside_repository",
            "Artifact paths must stay inside the resolved repository root.",
        ) from exc


def load_image(path: str, max_dimension: int) -> tuple[np.ndarray, dict[str, Any]]:
    require_trace_runtime()
    if max_dimension <= 0 or max_dimension > MAX_ALLOWED_WORK_DIMENSION:
        raise TraceRunError(
            "invalid_max_dimension",
            f"Maximum dimension must be between 1 and {MAX_ALLOWED_WORK_DIMENSION}.",
        )
    source = Path(path)
    if not source.is_file():
        raise TraceRunError("input_unavailable", "Input image is unavailable or is not a file.")
    previous_max_image_pixels = Image.MAX_IMAGE_PIXELS
    try:
        if source.stat().st_size > MAX_INPUT_BYTES:
            raise TraceRunError("input_too_large", "Input image exceeds the local safety limit.")
        source_payload = source.read_bytes()
        if not source_payload or len(source_payload) > MAX_INPUT_BYTES:
            raise TraceRunError("input_too_large", "Input image exceeds the local safety limit.")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
            with Image.open(io.BytesIO(source_payload)) as source_image:
                if source_image.format not in ALLOWED_INPUT_FORMATS:
                    raise TraceRunError(
                        "unsupported_input_format", "Input must contain a PNG or JPEG image."
                    )
                decoded_size = source_image.size
                if decoded_size[0] * decoded_size[1] > MAX_SOURCE_PIXELS:
                    raise TraceRunError(
                        "input_too_large", "Decoded image exceeds the local pixel safety limit."
                    )
                image = ImageOps.exif_transpose(source_image).convert("RGB")
                original_size = image.size
                scale = min(1.0, max_dimension / max(original_size))
                if scale < 1.0:
                    new_size = (
                        max(1, round(original_size[0] * scale)),
                        max(1, round(original_size[1] * scale)),
                    )
                    image = image.resize(new_size, Image.Resampling.LANCZOS)
                rgb = np.array(image)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise TraceRunError(
            "input_too_large", "Decoded image exceeds the local pixel safety limit."
        ) from exc
    except (OSError, ValueError) as exc:
        raise TraceRunError(
            "input_decode_failed", "Input could not be decoded as an image."
        ) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_image_pixels
    digest = hashlib.sha256(source_payload).hexdigest()[:12]
    return rgb, {
        "source_sha256_12": digest,
        "original_width": original_size[0],
        "original_height": original_size[1],
        "work_width": int(rgb.shape[1]),
        "work_height": int(rgb.shape[0]),
    }


def adjust_color(rgb: np.ndarray, preset: TracePreset) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * preset.saturation, 0, 255)
    rgb2 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    lab = cv2.cvtColor(rgb2, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l = np.clip((l.astype(np.float32) - 128.0) * preset.contrast + 128.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2RGB)


def quantize(rgb: np.ndarray, colors: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pixels = rgb.reshape((-1, 3)).astype(np.float32)
    cluster_count = min(colors, len(pixels))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.8)
    cv2.setRNGSeed(0)
    _, labels, centers = cv2.kmeans(pixels, cluster_count, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8)
    labels = labels.flatten()
    quantized = centers[labels].reshape(rgb.shape)
    return quantized, labels.reshape(rgb.shape[:2]), centers


def edge_overlay(rgb: np.ndarray, preset: TracePreset) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, preset.canny_low, preset.canny_high)
    if preset.edge_weight <= 0:
        return rgb, edges
    dark = np.zeros_like(rgb)
    edge_mask = (edges > 0)[:, :, None].astype(np.float32)
    mixed = rgb.astype(np.float32) * (1.0 - edge_mask * preset.edge_weight) + dark * (
        edge_mask * preset.edge_weight
    )
    return np.clip(mixed, 0, 255).astype(np.uint8), edges


def run_preset(rgb: np.ndarray, preset: TracePreset) -> dict[str, Any]:
    adjusted = adjust_color(rgb, preset)
    if preset.blur > 1:
        blur = preset.blur if preset.blur % 2 == 1 else preset.blur + 1
        adjusted = cv2.bilateralFilter(adjusted, blur, 55, 55)
    quantized, labels, centers = quantize(adjusted, preset.colors)
    preview, edges = edge_overlay(quantized, preset)
    paths, contour_count, skipped_count = build_svg_paths(labels, centers, preset)
    edge_density = float(np.count_nonzero(edges)) / float(edges.size)
    return {
        "preview": preview,
        "quantized_target": quantized,
        "paths": paths,
        "contour_count": contour_count,
        "skipped_count": skipped_count,
        "edge_density": edge_density,
        "palette": [rgb_hex(center) for center in centers],
    }


def rgb_hex(color: np.ndarray) -> str:
    return f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"


def build_svg_paths(
    labels: np.ndarray, centers: np.ndarray, preset: TracePreset
) -> tuple[list[str], int, int]:
    paths: list[str] = []
    contour_count = 0
    skipped_count = 0
    for idx, center in enumerate(centers):
        mask = (labels == idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        fill = rgb_hex(center)
        compound_parts: list[str] = []
        for contour in contours:
            area = abs(cv2.contourArea(contour))
            if area < preset.min_area:
                skipped_count += 1
                continue
            perimeter = cv2.arcLength(contour, True)
            epsilon = max(0.6, perimeter * preset.simplify)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            if len(approx) < 3:
                skipped_count += 1
                continue
            points = approx.reshape((-1, 2))
            compound_parts.append("M " + " L ".join(f"{int(x)} {int(y)}" for x, y in points) + " Z")
            contour_count += 1
        if compound_parts:
            path_data = " ".join(compound_parts)
            paths.append(f'<path d="{path_data}" fill="{fill}" fill-rule="evenodd" stroke="none"/>')
    return paths, contour_count, skipped_count


def write_svg(path: Path, width: int, height: int, paths: list[str]) -> None:
    body = "\n  ".join(paths)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <rect width="{width}" height="{height}" fill="#ffffff"/>\n'
        f"  {body}\n"
        "</svg>\n",
        encoding="utf-8",
    )


def _hex_rgb(value: str) -> tuple[int, int, int]:
    payload = value.removeprefix("#")
    return tuple(bytes.fromhex(payload))


def measure_svg_raster_quality(
    svg_path: Path,
    target_rgb: np.ndarray,
    *,
    target_kind: str,
    similarity_min: float = SVG_RASTER_SIMILARITY_MIN,
) -> dict[str, Any]:
    """Rasterize the verified SVG subset and compare it with an in-memory target."""

    require_trace_runtime()
    if (
        not isinstance(target_rgb, np.ndarray)
        or target_rgb.ndim != 3
        or target_rgb.shape[2] != 3
        or target_rgb.size == 0
    ):
        raise ValueError("target_rgb must be a non-empty RGB array")
    if target_kind not in SVG_QUALITY_TARGET_KINDS:
        raise ValueError("unsupported SVG quality target_kind")
    if not 0.5 <= similarity_min <= 1.0:
        raise ValueError("similarity_min must be between 0.5 and 1.0")

    height, width = target_rgb.shape[:2]
    verify_svg_artifact(svg_path, expected_width=width, expected_height=height)
    root = ET.parse(svg_path).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    background = root.find("svg:rect", namespace)
    background_rgb = (
        _hex_rgb(background.get("fill", "#ffffff")) if background is not None else (255, 255, 255)
    )
    raster = np.full((height, width, 3), background_rgb, dtype=np.uint8)

    for path in root.findall("svg:path", namespace):
        mask = np.zeros((height, width), dtype=np.uint8)
        for segment in _SVG_PATH_SEGMENT.findall(path.get("d", "")):
            points = [
                (int(round(float(x))), int(round(float(y)))) for x, y in _SVG_POINT.findall(segment)
            ]
            contour_mask = np.zeros_like(mask)
            cv2.fillPoly(
                contour_mask,
                [np.asarray(points, dtype=np.int32)],
                255,
            )
            mask = cv2.bitwise_xor(mask, contour_mask)
        raster[mask > 0] = _hex_rgb(path.get("fill", "#000000"))

    target = target_rgb.astype(np.uint8, copy=False)
    difference = np.abs(raster.astype(np.int16) - target.astype(np.int16))
    exact_match_ratio = float(np.mean(np.all(raster == target, axis=2)))
    mean_absolute_error = float(np.mean(difference))
    similarity = max(0.0, 1.0 - mean_absolute_error / 255.0)
    return {
        "schema_version": SVG_QUALITY_SCHEMA_VERSION,
        "target_kind": target_kind,
        "rasterizer": "restricted_svg_rect_path_v1",
        "pixel_count": int(width * height),
        "exact_pixel_match_ratio": round(exact_match_ratio, 6),
        "mean_absolute_error": round(mean_absolute_error, 6),
        "similarity": round(similarity, 6),
        "similarity_min": float(similarity_min),
        "verdict": "pass" if similarity >= similarity_min else "review_required",
        "safety": {
            "source_path_reported": False,
            "image_bytes_returned": False,
            "reads_generated_svg": True,
            "rasterizes_embedded_image": False,
            "visual_review_required": True,
        },
    }


def save_preview(path: Path, rgb: np.ndarray) -> None:
    Image.fromarray(rgb).save(path)


def make_contact_sheet(previews: list[tuple[str, Path, dict[str, Any]]], output_path: Path) -> None:
    thumbs: list[tuple[str, Image.Image, dict[str, Any]]] = []
    for name, preview_path, metrics in previews:
        with Image.open(preview_path) as source_image:
            image = source_image.convert("RGB")
        image.thumbnail((360, 540), Image.Resampling.LANCZOS)
        thumbs.append((name, image.copy(), metrics))
    if not thumbs:
        return
    cols = 2
    rows = math.ceil(len(thumbs) / cols)
    cell_w, cell_h = 430, 650
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#f3f4f6")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, (name, image, metrics) in enumerate(thumbs):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        sheet.paste(image, (x + 35, y + 25))
        lines = [
            name,
            f"paths: {metrics['path_count']}  colors: {metrics['color_count']}",
            f"edge: {metrics['edge_density']:.3f}  score: {metrics['control_score']:.1f}",
        ]
        for line_idx, line in enumerate(lines):
            draw.text((x + 35, y + 580 + line_idx * 18), line, fill="#111827", font=font)
    sheet.save(output_path)


def score_metrics(path_count: int, edge_density: float, colors: int) -> float:
    path_penalty = min(path_count / 2200.0, 1.8)
    edge_bonus = min(edge_density * 4.0, 1.0)
    color_penalty = max(colors - 16, 0) / 32.0
    return max(0.0, 100.0 - path_penalty * 42.0 + edge_bonus * 12.0 - color_penalty * 12.0)


def verify_raster_artifact(path: Path) -> dict[str, Any]:
    require_trace_runtime()
    if not path.is_file():
        raise TraceRunError("artifact_missing", "Raster preview artifact was not created.")
    payload = path.read_bytes()
    if not payload:
        raise TraceRunError("artifact_empty", "Raster preview artifact is empty.")
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            image_format = (image.format or "").upper()
    except (OSError, ValueError) as exc:
        raise TraceRunError(
            "invalid_raster", "Raster preview artifact could not be decoded."
        ) from exc
    if width <= 0 or height <= 0 or image_format != "PNG":
        raise TraceRunError("invalid_raster", "Raster preview must be a non-empty PNG.")
    return {
        "verified": True,
        "media_type": "image/png",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": width,
        "height": height,
    }


def verify_json_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TraceRunError("artifact_missing", "JSON report artifact was not created.")
    payload = path.read_bytes()
    if not payload:
        raise TraceRunError("artifact_empty", "JSON report artifact is empty.")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TraceRunError("invalid_report", "Trace report is not valid UTF-8 JSON.") from exc
    if not isinstance(decoded, dict) or not decoded.get("presets"):
        raise TraceRunError("invalid_report", "Trace report does not contain verified presets.")
    return {
        "verified": True,
        "media_type": "application/json",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def artifact_entry(role: str, public_path: str, verification: dict[str, Any]) -> dict[str, Any]:
    return {"role": role, "path": public_path, **verification}


def publish_verified_artifacts(
    pairs: list[tuple[Path, Path]],
    staging_dir: Path,
    *,
    remove_targets: tuple[Path, ...] = (),
) -> None:
    """Publish a verified batch, preserving recoverable backups across double failures."""

    staging_root = staging_dir.resolve()
    if not staging_root.is_dir():
        raise TraceRunError("invalid_staging", "Artifact staging directory is unavailable.")
    if any(
        not staged_path.is_file() or not staged_path.resolve().is_relative_to(staging_root)
        for staged_path, _ in pairs
    ):
        raise TraceRunError(
            "invalid_staged_artifact", "Artifact publish inputs must be staged regular files."
        )
    final_paths = [final_path for _, final_path in pairs]
    if len(final_paths) != len(set(final_paths)):
        raise TraceRunError("duplicate_artifact", "Artifact publish targets must be unique.")
    if set(final_paths) & set(remove_targets):
        raise TraceRunError("duplicate_artifact", "Publish and removal targets must be disjoint.")
    managed_paths = [*final_paths, *remove_targets]
    if not managed_paths:
        return
    target_root = managed_paths[0].parent.resolve()
    if target_root == staging_root or target_root.is_relative_to(staging_root):
        raise TraceRunError(
            "invalid_artifact_target", "Artifact targets must stay outside temporary staging."
        )
    if any(path.parent.resolve() != target_root for path in managed_paths):
        raise TraceRunError(
            "invalid_artifact_target", "Artifact publish targets must share one output directory."
        )
    if any(
        os.path.lexists(final_path) and not (final_path.is_file() or final_path.is_symlink())
        for final_path in managed_paths
    ):
        raise TraceRunError(
            "invalid_artifact_target", "Artifact publish target must not be a directory."
        )
    try:
        backup_dir = Path(tempfile.mkdtemp(prefix=".trace-recovery-", dir=target_root))
    except OSError as exc:
        raise TraceRunError(
            "artifact_backup_failed", "A durable artifact recovery directory could not be created."
        ) from exc
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for index, (staged_path, final_path) in enumerate(pairs):
            if os.path.lexists(final_path):
                backup_path = backup_dir / f"{index:03d}-{final_path.name}"
                os.replace(final_path, backup_path)
                backups.append((backup_path, final_path))
            os.replace(staged_path, final_path)
            published.append(final_path)
        for offset, remove_target in enumerate(remove_targets, start=len(pairs)):
            if os.path.lexists(remove_target):
                backup_path = backup_dir / f"{offset:03d}-{remove_target.name}"
                os.replace(remove_target, backup_path)
                backups.append((backup_path, remove_target))
    except OSError as exc:
        rollback_failed = False
        for published_path in reversed(published):
            if os.path.lexists(published_path) and (
                published_path.is_file() or published_path.is_symlink()
            ):
                try:
                    published_path.unlink()
                except OSError:
                    rollback_failed = True
        for backup_path, final_path in reversed(backups):
            if os.path.lexists(backup_path):
                try:
                    os.replace(backup_path, final_path)
                except OSError:
                    rollback_failed = True
        if rollback_failed:
            raise TraceRunError(
                "artifact_rollback_failed",
                "Artifact publish and automatic restore failed; recovery data was preserved in the output directory.",
            ) from exc
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise TraceRunError(
            "artifact_publish_failed",
            "Verified artifacts could not be published; previous outputs were restored.",
        ) from exc
    shutil.rmtree(backup_dir, ignore_errors=True)


def run_trace(args: argparse.Namespace) -> dict[str, Any]:
    require_trace_runtime()
    output_dir = safe_output_dir(args.output_dir)
    rgb, source_meta = load_image(args.input, args.max_dimension)
    preset_names = [name.strip() for name in args.presets.split(",") if name.strip()]
    if not preset_names:
        raise TraceRunError("no_presets", "At least one trace preset is required.")
    unknown = [name for name in preset_names if name not in PRESETS]
    if unknown:
        raise TraceRunError("unknown_preset", "One or more trace presets are unsupported.")
    if args.commit_preset and args.commit_preset not in preset_names:
        raise TraceRunError(
            "invalid_commit_preset",
            "--commit-preset must be one of the generated presets.",
        )

    report: dict[str, Any] = {
        "bridge": "illustrator",
        "task": "trace_photo_preview",
        "source": source_meta,
        "output_dir": repo_relative_path(output_dir),
        "presets": [],
        "recommended_preset": None,
        "final": None,
        "artifacts": [],
        "warnings": [
            "This is an experimental local color-vector preview, not production Illustrator Image Trace parity.",
            "Source image paths and filenames are not written to this report.",
            "Complex photos, gradients, transparency, text, and fine topology still require manual review.",
        ],
    }
    width, height = int(rgb.shape[1]), int(rgb.shape[0])
    with tempfile.TemporaryDirectory(prefix=".trace-", dir=output_dir) as temporary_dir:
        staging_dir = Path(temporary_dir)
        contact_inputs: list[tuple[str, Path, dict[str, Any]]] = []
        publish_pairs: list[tuple[Path, Path]] = []
        staged_by_name: dict[str, tuple[Path, Path]] = {}
        preset_metrics_by_name: dict[str, dict[str, Any]] = {}

        for name in preset_names:
            preset = PRESETS[name]
            result = run_preset(rgb, preset)
            staged_preview = staging_dir / f"{name}_preview.png"
            staged_svg = staging_dir / f"{name}.svg"
            final_preview = output_dir / staged_preview.name
            final_svg = output_dir / staged_svg.name
            save_preview(staged_preview, result["preview"])
            write_svg(staged_svg, width, height, result["paths"])

            svg_verification = verify_svg_artifact(
                staged_svg, expected_width=width, expected_height=height
            )
            preview_verification = verify_raster_artifact(staged_preview)
            svg_raster_quality = measure_svg_raster_quality(
                staged_svg,
                result["quantized_target"],
                target_kind="in_memory_quantized_target",
            )
            reference_svg_quality = measure_svg_raster_quality(
                staged_svg,
                rgb,
                target_kind="explicit_reference_work_rgb",
            )
            svg_public_path = repo_relative_path(final_svg)
            preview_public_path = repo_relative_path(final_preview)
            svg_artifact = artifact_entry("editable_svg", svg_public_path, svg_verification)
            preview_artifact = artifact_entry(
                "quantized_preview", preview_public_path, preview_verification
            )
            report["artifacts"].extend((svg_artifact, preview_artifact))

            metrics = {
                "name": name,
                "note": preset.note,
                "requested_color_count": preset.colors,
                "color_count": svg_verification["color_count"],
                "path_count": svg_verification["path_count"],
                "subpath_count": svg_verification["subpath_count"],
                "skipped_small_regions": result["skipped_count"],
                "edge_density": round(result["edge_density"], 5),
                "svg_size_kb": round(svg_verification["bytes"] / 1024.0, 1),
                "preview": preview_public_path,
                "svg": svg_public_path,
                "palette": result["palette"],
                "svg_artifact": svg_artifact,
                "svg_raster_quality": svg_raster_quality,
                "reference_svg_quality": reference_svg_quality,
            }
            metrics["control_score"] = round(
                score_metrics(
                    metrics["subpath_count"],
                    result["edge_density"],
                    metrics["color_count"],
                ),
                1,
            )
            report["presets"].append(metrics)
            contact_inputs.append((name, staged_preview, metrics))
            publish_pairs.extend(((staged_svg, final_svg), (staged_preview, final_preview)))
            staged_by_name[name] = (staged_svg, staged_preview)
            preset_metrics_by_name[name] = metrics

        best = max(report["presets"], key=lambda item: item["control_score"])
        report["recommended_preset"] = best["name"]
        staged_contact_sheet = staging_dir / "trace_contact_sheet.png"
        final_contact_sheet = output_dir / staged_contact_sheet.name
        make_contact_sheet(contact_inputs, staged_contact_sheet)
        contact_verification = verify_raster_artifact(staged_contact_sheet)
        contact_public_path = repo_relative_path(final_contact_sheet)
        report["contact_sheet"] = contact_public_path
        report["artifacts"].append(
            artifact_entry("preset_contact_sheet", contact_public_path, contact_verification)
        )
        publish_pairs.append((staged_contact_sheet, final_contact_sheet))

        if args.commit_preset:
            source_svg, source_preview = staged_by_name[args.commit_preset]
            staged_final_svg = staging_dir / "final_trace.svg"
            staged_final_preview = staging_dir / "final_preview.png"
            final_svg = output_dir / staged_final_svg.name
            final_preview = output_dir / staged_final_preview.name
            shutil.copyfile(source_svg, staged_final_svg)
            shutil.copyfile(source_preview, staged_final_preview)
            final_svg_verification = verify_svg_artifact(
                staged_final_svg, expected_width=width, expected_height=height
            )
            final_preview_verification = verify_raster_artifact(staged_final_preview)
            final_svg_public_path = repo_relative_path(final_svg)
            final_preview_public_path = repo_relative_path(final_preview)
            report["final"] = {
                "preset": args.commit_preset,
                "svg": final_svg_public_path,
                "preview": final_preview_public_path,
                "svg_raster_quality": preset_metrics_by_name[args.commit_preset][
                    "svg_raster_quality"
                ],
                "reference_svg_quality": preset_metrics_by_name[args.commit_preset][
                    "reference_svg_quality"
                ],
            }
            report["artifacts"].extend(
                (
                    artifact_entry(
                        "committed_editable_svg", final_svg_public_path, final_svg_verification
                    ),
                    artifact_entry(
                        "committed_preview",
                        final_preview_public_path,
                        final_preview_verification,
                    ),
                )
            )
            publish_pairs.extend(
                ((staged_final_svg, final_svg), (staged_final_preview, final_preview))
            )

        staged_report = staging_dir / "trace_report.json"
        final_report = output_dir / staged_report.name
        staged_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report_verification = verify_json_artifact(staged_report)
        report_public_path = repo_relative_path(final_report)
        report_artifact = artifact_entry("trace_report", report_public_path, report_verification)
        publish_pairs.append((staged_report, final_report))

        stale_preset_targets = tuple(
            output_dir / filename
            for preset_name in PRESETS
            if preset_name not in preset_names
            for filename in (f"{preset_name}.svg", f"{preset_name}_preview.png")
        )
        stale_final_targets = (
            ()
            if args.commit_preset
            else (output_dir / "final_trace.svg", output_dir / "final_preview.png")
        )
        publish_verified_artifacts(
            publish_pairs,
            staging_dir,
            remove_targets=(*stale_preset_targets, *stale_final_targets),
        )

    return {
        "ok": True,
        "report": report_public_path,
        "recommended_preset": report["recommended_preset"],
        "final": report["final"],
        "artifacts": [*report["artifacts"], report_artifact],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_trace(parse_args(argv))
    except TraceRunError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    except SvgArtifactError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    except Exception:
        result = {
            "ok": False,
            "error": {
                "code": "trace_failed",
                "message": "Color vector trace failed before verified artifacts were published.",
            },
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
