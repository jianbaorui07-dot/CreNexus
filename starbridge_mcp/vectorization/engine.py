from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from .presets import VectorPreset, configured_preset
from .svg_verify import SvgArtifactError, verify_svg_artifact

try:
    import cv2
    import numpy as np
except ImportError:  # Exact mode intentionally works with Pillow alone.
    cv2 = None
    np = None

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "examples" / "output" / "vectorization"
MAX_SOURCE_BYTES = 128 * 1024 * 1024
REFERENCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
SUPPORTED_FORMATS = {"JPEG", "PNG"}

RGBA = tuple[int, int, int, int]


class VectorizationError(RuntimeError):
    """A structured failure that is safe to return without private input paths."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RunConfig:
    input_path: str
    mode: str = "smart"
    reference_id: str = "vector-job"
    output_dir: str = ""
    colors: int | None = None
    max_dimension: int | None = None
    simplify_ratio: float | None = None
    min_region_area: int | None = None
    alpha_threshold: int | None = None
    max_subpaths: int | None = None
    max_points: int | None = None
    max_svg_size_mb: float | None = None


@dataclass(frozen=True)
class Rectangle:
    x: int
    y: int
    width: int
    height: int
    color: RGBA


@dataclass(frozen=True)
class Paint:
    red: int
    green: int
    blue: int
    alpha: int

    @property
    def fill(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return "<REDACTED_PATH>"


def resolve_output_dir(requested: str, reference_id: str, mode: str) -> Path:
    if not REFERENCE_ID.fullmatch(reference_id):
        raise VectorizationError(
            "invalid_reference_id",
            "Reference id must use lowercase letters, digits, underscores, or hyphens.",
        )
    root = OUTPUT_ROOT.resolve()
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
    else:
        candidate = root / reference_id / mode
    resolved = candidate.resolve()
    if resolved == root or root not in resolved.parents:
        raise VectorizationError(
            "output_outside_sandbox",
            "Output must stay below examples/output/vectorization.",
        )
    return resolved


def load_source(path_value: str, max_pixels: int) -> tuple[Image.Image, dict[str, Any]]:
    path = Path(path_value)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
        raise VectorizationError(
            "unsupported_input", "Input must be one explicit PNG or JPEG file."
        )
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise VectorizationError("input_too_large", "Input file exceeds the byte limit.")
    previous_max_pixels = Image.MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            Image.MAX_IMAGE_PIXELS = max_pixels
            with Image.open(path) as opened:
                if opened.format not in SUPPORTED_FORMATS:
                    raise VectorizationError(
                        "unsupported_input_format", "Input content must be PNG or JPEG."
                    )
                source_format = opened.format
                oriented = ImageOps.exif_transpose(opened)
                width, height = oriented.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise VectorizationError(
                        "input_too_large", "Input pixel count exceeds the selected mode limit."
                    )
                rgba = oriented.convert("RGBA")
    except VectorizationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise VectorizationError(
            "input_too_large", "Input pixel count exceeds the selected mode limit."
        ) from exc
    except (OSError, UnidentifiedImageError) as exc:
        raise VectorizationError("input_unreadable", "Input image could not be decoded.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max_pixels
    return rgba, {
        "source_sha256": file_sha256(path),
        "format": source_format,
        "width": width,
        "height": height,
        "pixel_count": width * height,
    }


def _configured(config: RunConfig) -> VectorPreset:
    try:
        return configured_preset(
            config.mode,
            colors=config.colors,
            max_dimension=config.max_dimension,
            simplify_ratio=config.simplify_ratio,
            min_region_area=config.min_region_area,
            alpha_threshold=config.alpha_threshold,
            max_subpaths=config.max_subpaths,
            max_points=config.max_points,
            max_svg_size_mb=config.max_svg_size_mb,
        )
    except ValueError as exc:
        raise VectorizationError("invalid_parameters", str(exc)) from exc


def _opacity(alpha: int) -> str:
    return format(alpha / 255.0, ".15g")


def _merge_exact_rectangles(image: Image.Image, preset: VectorPreset) -> list[Rectangle]:
    width, height = image.size
    pixels = image.load()
    active: dict[tuple[int, int, RGBA], Rectangle] = {}
    completed: list[Rectangle] = []

    for y in range(height):
        row: dict[tuple[int, int, RGBA], Rectangle] = {}
        x = 0
        while x < width:
            color = pixels[x, y]
            start = x
            x += 1
            while x < width and pixels[x, y] == color:
                x += 1
            key = (start, x, color)
            previous = active.get(key)
            row[key] = (
                Rectangle(start, previous.y, x - start, previous.height + 1, color)
                if previous is not None
                else Rectangle(start, y, x - start, 1, color)
            )
        for key, rectangle in active.items():
            if key not in row:
                completed.append(rectangle)
        active = row
        if len(completed) + len(active) > preset.max_subpaths:
            raise VectorizationError(
                "vector_too_complex",
                "Exact reconstruction exceeds the rectangle-subpath safety limit.",
            )

    completed.extend(active.values())
    if len(completed) > preset.max_subpaths or len(completed) * 4 > preset.max_points:
        raise VectorizationError(
            "vector_too_complex", "Exact reconstruction exceeds the configured path limits."
        )
    return completed


def _validate_exact_rectangles(image: Image.Image, rectangles: list[Rectangle]) -> dict[str, Any]:
    width, height = image.size
    rebuilt = bytearray(width * height * 4)
    for rectangle in rectangles:
        row_payload = bytes(rectangle.color) * rectangle.width
        for y in range(rectangle.y, rectangle.y + rectangle.height):
            offset = (y * width + rectangle.x) * 4
            rebuilt[offset : offset + len(row_payload)] = row_payload
    source = image.tobytes()
    if rebuilt == source:
        return {
            "pixel_match": True,
            "different_pixel_count": 0,
            "maximum_channel_difference": 0,
        }
    different_pixels = 0
    maximum_difference = 0
    for offset in range(0, len(source), 4):
        differences = [abs(source[offset + index] - rebuilt[offset + index]) for index in range(4)]
        if any(differences):
            different_pixels += 1
            maximum_difference = max(maximum_difference, *differences)
    return {
        "pixel_match": False,
        "different_pixel_count": different_pixels,
        "maximum_channel_difference": maximum_difference,
    }


def _write_exact_svg(path: Path, image: Image.Image, rectangles: list[Rectangle]) -> dict[str, int]:
    width, height = image.size
    grouped: dict[RGBA, list[Rectangle]] = defaultdict(list)
    for rectangle in rectangles:
        grouped[rectangle.color].append(rectangle)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">\n'
        )
        for red, green, blue, alpha in sorted(grouped):
            opacity = "" if alpha == 255 else f' fill-opacity="{_opacity(alpha)}"'
            stream.write(
                f'<path fill="#{red:02x}{green:02x}{blue:02x}"{opacity} '
                'fill-rule="evenodd" stroke="none" d="'
            )
            separator = ""
            for rectangle in grouped[(red, green, blue, alpha)]:
                x0 = rectangle.x
                y0 = rectangle.y
                x1 = x0 + rectangle.width
                y1 = y0 + rectangle.height
                stream.write(f"{separator}M {x0} {y0} L {x1} {y0} L {x1} {y1} L {x0} {y1} Z")
                separator = " "
            stream.write('"/>\n')
        stream.write("</svg>\n")
    return {
        "path_objects": len(grouped),
        "subpaths": len(rectangles),
        "points": len(rectangles) * 4,
        "colors": len({color[:3] for color in grouped}),
        "paints": len(grouped),
    }


def _require_design_runtime() -> None:
    if cv2 is None or np is None:
        raise VectorizationError(
            "missing_vectorization_dependency",
            'Install the smart-vector runtime: python -m pip install -e ".[vectorization]"',
        )


def _resize_for_design(image: Image.Image, max_dimension: int) -> Image.Image:
    scale = min(1.0, max_dimension / max(image.size))
    if scale >= 1.0:
        return image.copy()
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _prepare_rgb(rgba: Any, preset: VectorPreset) -> Any:
    rgb = rgba[:, :, :3]
    if preset.blur_diameter > 1:
        diameter = preset.blur_diameter if preset.blur_diameter % 2 else preset.blur_diameter + 1
        rgb = cv2.bilateralFilter(rgb, diameter, 55, 55)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    contrast = 1.04 if preset.mode == "smart" else 1.02
    lightness = np.clip((lightness.astype(np.float32) - 128.0) * contrast + 128.0, 0, 255).astype(
        np.uint8
    )
    return cv2.cvtColor(cv2.merge((lightness, channel_a, channel_b)), cv2.COLOR_LAB2RGB)


def _palette_and_labels(pixels: Any, requested_colors: int) -> tuple[Any, Any]:
    if len(pixels) == 0:
        raise VectorizationError("no_visible_pixels", "No pixels remain above the alpha threshold.")
    sample_limit = 200_000
    if len(pixels) > sample_limit:
        sample_indices = np.linspace(0, len(pixels) - 1, sample_limit, dtype=np.int64)
        sample = pixels[sample_indices]
    else:
        sample = pixels
    unique = np.unique(sample, axis=0)
    cluster_count = min(requested_colors, len(unique))
    if cluster_count < 1:
        raise VectorizationError("no_visible_pixels", "No visible colors could be analyzed.")
    if len(unique) <= cluster_count:
        centers = unique.astype(np.uint8)
    else:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.6)
        cv2.setRNGSeed(0)
        _, _, raw_centers = cv2.kmeans(
            sample.astype(np.float32),
            cluster_count,
            None,
            criteria,
            3,
            cv2.KMEANS_PP_CENTERS,
        )
        centers = np.clip(np.rint(raw_centers), 0, 255).astype(np.uint8)
    order = np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))
    centers = centers[order]
    labels = np.empty(len(pixels), dtype=np.int32)
    chunk_size = 100_000
    centers_i32 = centers.astype(np.int32)
    for start in range(0, len(pixels), chunk_size):
        chunk = pixels[start : start + chunk_size].astype(np.int32)
        distances = np.sum((chunk[:, None, :] - centers_i32[None, :, :]) ** 2, axis=2)
        labels[start : start + len(chunk)] = np.argmin(distances, axis=1)
    return centers, labels


def _build_paint_labels(
    rgba: Any, prepared_rgb: Any, preset: VectorPreset
) -> tuple[Any, dict[int, Paint]]:
    alpha = rgba[:, :, 3]
    visible = alpha >= preset.alpha_threshold
    visible_pixels = prepared_rgb[visible]
    centers, color_labels = _palette_and_labels(visible_pixels, preset.colors)
    alpha_values = np.rint(
        np.linspace(255.0 / preset.alpha_levels, 255.0, preset.alpha_levels)
    ).astype(np.uint8)
    visible_alpha = alpha[visible].astype(np.int16)
    alpha_indices = np.argmin(
        np.abs(visible_alpha[:, None] - alpha_values.astype(np.int16)[None, :]), axis=1
    ).astype(np.int32)
    visible_labels = color_labels * preset.alpha_levels + alpha_indices
    labels = np.full(alpha.shape, -1, dtype=np.int32)
    labels[visible] = visible_labels
    paints: dict[int, Paint] = {}
    for label in np.unique(visible_labels):
        color_index = int(label) // preset.alpha_levels
        alpha_index = int(label) % preset.alpha_levels
        red, green, blue = (int(value) for value in centers[color_index])
        paints[int(label)] = Paint(red, green, blue, int(alpha_values[alpha_index]))
    return labels, paints


def _try_artisan_line_art(
    rgba: Any, preset: VectorPreset
) -> tuple[Any, dict[int, Paint], dict[str, int | float | bool]] | None:
    alpha = rgba[:, :, 3]
    visible = alpha >= preset.alpha_threshold
    visible_count = int(np.count_nonzero(visible))
    if visible_count < 256:
        return None
    rgb = rgba[:, :, :3]
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.int16)
    background_lab = np.median(lab[visible], axis=0)
    difference = np.abs(lab - background_lab)
    score = np.clip(
        difference[:, :, 0] * 0.35 + difference[:, :, 1] * 1.8 + difference[:, :, 2],
        0,
        255,
    ).astype(np.uint8)
    threshold, _ = cv2.threshold(
        score[visible].reshape((-1, 1)),
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    threshold = max(10.0, float(threshold))
    ink = visible & (score >= threshold)
    ink_count = int(np.count_nonzero(ink))
    ink_ratio = ink_count / visible_count
    if ink_count < 64 or not 0.003 <= ink_ratio <= 0.32:
        return None

    component_count, components, stats, _ = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    cleaned_ink = np.zeros_like(ink)
    minimum_component_area = max(2, preset.min_region_area // 12)
    for component in range(1, component_count):
        if int(stats[component, cv2.CC_STAT_AREA]) >= minimum_component_area:
            cleaned_ink |= components == component
    ink_count = int(np.count_nonzero(cleaned_ink))
    if ink_count < 64:
        return None

    contours, _ = cv2.findContours(
        cleaned_ink.astype(np.uint8) * 255,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    perimeter = sum(float(cv2.arcLength(contour, True)) for contour in contours)
    estimated_stroke_width = 2.0 * ink_count / perimeter if perimeter > 0 else float("inf")
    background_rgb = np.median(rgb[visible & ~cleaned_ink], axis=0)
    ink_rgb = np.median(rgb[cleaned_ink], axis=0)
    color_separation = float(np.linalg.norm(ink_rgb.astype(float) - background_rgb.astype(float)))
    if estimated_stroke_width > max(9.0, max(rgba.shape[:2]) * 0.007) or color_separation < 16:
        return None

    labels = np.full(alpha.shape, -1, dtype=np.int32)
    labels[visible] = 0
    labels[cleaned_ink] = 1
    background_alpha = int(np.median(alpha[visible & ~cleaned_ink]))
    ink_alpha = int(np.median(alpha[cleaned_ink]))
    paints = {
        0: Paint(*(int(value) for value in background_rgb), background_alpha),
        1: Paint(*(int(value) for value in ink_rgb), ink_alpha),
    }
    return (
        labels,
        paints,
        {
            "line_art_adaptation": True,
            "ink_pixel_ratio": round(ink_count / visible_count, 6),
            "estimated_stroke_width_px": round(estimated_stroke_width, 4),
            "line_art_threshold": round(threshold, 4),
            "line_art_color_separation": round(color_separation, 4),
        },
    )


def _cleanup_small_regions(labels: Any, min_area: int) -> tuple[Any, int]:
    if min_area <= 1:
        return labels, 0
    cleaned = labels.copy()
    changed = 0
    kernel = np.ones((3, 3), dtype=np.uint8)
    for label in [int(value) for value in np.unique(cleaned) if value >= 0]:
        mask = (cleaned == label).astype(np.uint8)
        component_count, components, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=8
        )
        for component in range(1, component_count):
            area = int(stats[component, cv2.CC_STAT_AREA])
            if area >= min_area:
                continue
            x = int(stats[component, cv2.CC_STAT_LEFT])
            y = int(stats[component, cv2.CC_STAT_TOP])
            width = int(stats[component, cv2.CC_STAT_WIDTH])
            height = int(stats[component, cv2.CC_STAT_HEIGHT])
            x0, y0 = max(0, x - 1), max(0, y - 1)
            x1 = min(cleaned.shape[1], x + width + 1)
            y1 = min(cleaned.shape[0], y + height + 1)
            component_patch = components[y0:y1, x0:x1] == component
            ring = cv2.dilate(component_patch.astype(np.uint8), kernel, iterations=1).astype(bool)
            ring &= ~component_patch
            label_patch = cleaned[y0:y1, x0:x1]
            neighbors = label_patch[ring]
            neighbors = neighbors[(neighbors >= 0) & (neighbors != label)]
            replacement = -1
            if len(neighbors):
                values, counts = np.unique(neighbors, return_counts=True)
                replacement = int(values[int(np.argmax(counts))])
            label_patch[component_patch] = replacement
            changed += 1
    return cleaned, changed


def _normalized_points(contour: Any, width: int, height: int) -> list[tuple[int, int]]:
    normalized: list[tuple[int, int]] = []
    for raw_x, raw_y in contour.reshape((-1, 2)):
        x = width if int(raw_x) >= width - 1 else max(0, int(raw_x))
        y = height if int(raw_y) >= height - 1 else max(0, int(raw_y))
        point = (x, y)
        if not normalized or point != normalized[-1]:
            normalized.append(point)
    if len(normalized) > 1 and normalized[0] == normalized[-1]:
        normalized.pop()
    return normalized


def _trace_design_paths(
    labels: Any, paints: dict[int, Paint], preset: VectorPreset
) -> tuple[list[tuple[Paint, list[str]]], dict[str, int]]:
    height, width = labels.shape
    output: list[tuple[Paint, list[str]]] = []
    subpaths = 0
    points = 0
    skipped = 0
    for label in [int(value) for value in np.unique(labels) if value >= 0]:
        mask = (labels == label).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        path_parts: list[str] = []
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            epsilon = max(0.25, perimeter * preset.simplify_ratio)
            approximation = cv2.approxPolyDP(contour, epsilon, True)
            contour_points = _normalized_points(approximation, width, height)
            if len(contour_points) < 3:
                skipped += 1
                continue
            subpaths += 1
            points += len(contour_points)
            if subpaths > preset.max_subpaths or points > preset.max_points:
                raise VectorizationError(
                    "vector_too_complex",
                    "Design vectorization exceeds the configured subpath or point limit.",
                )
            path_parts.append("M " + " L ".join(f"{x} {y}" for x, y in contour_points) + " Z")
        if path_parts:
            output.append((paints[label], path_parts))
    if not output:
        raise VectorizationError(
            "no_vector_paths", "Processing removed every region; lower the cleanup threshold."
        )
    return output, {
        "path_objects": len(output),
        "subpaths": subpaths,
        "points": points,
        "skipped_contours": skipped,
        "colors": len({paint.fill for paint, _ in output}),
        "paints": len(output),
    }


def _write_design_svg(
    path: Path, width: int, height: int, paths: list[tuple[Paint, list[str]]]
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">\n'
        )
        for paint, path_parts in paths:
            opacity = "" if paint.alpha == 255 else f' fill-opacity="{_opacity(paint.alpha)}"'
            stream.write(
                f'<path fill="{paint.fill}"{opacity} fill-rule="evenodd" stroke="none" '
                f'd="{" ".join(path_parts)}"/>\n'
            )
        stream.write("</svg>\n")


def _write_artisan_svg(path: Path, scene: Any, paints: dict[int, Paint]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene.width}" '
            f'height="{scene.height}" viewBox="0 0 {scene.width} {scene.height}">\n'
        )
        for role, shapes in scene.ordered_layers():
            stream.write(f'<g id="layer-{role}" data-role="{role}">\n')
            for shape in shapes:
                paint = paints[shape.label]
                opacity = "" if paint.alpha == 255 else f' fill-opacity="{_opacity(paint.alpha)}"'
                parent = shape.parent_shape_id or "none"
                stream.write(
                    f'<path id="{shape.shape_id}" data-role="{shape.role}" '
                    f'data-depth="{shape.depth}" data-parent="{parent}" '
                    f'fill="{paint.fill}"{opacity} fill-rule="evenodd" stroke="none" '
                    f'd="{" ".join(shape.path_parts)}"/>\n'
                )
            stream.write("</g>\n")
        stream.write("</svg>\n")


def _artisan_structure_manifest(scene: Any, paints: dict[int, Paint]) -> dict[str, Any]:
    from .artisan import ARTISAN_ROLE_LABELS_ZH

    canvas_area = float(scene.width * scene.height)
    shapes = []
    for shape in scene.shapes:
        paint = paints[shape.label]
        error_mean = (
            shape.contour_error_total / shape.contour_error_samples
            if shape.contour_error_samples
            else 0.0
        )
        shapes.append(
            {
                "id": shape.shape_id,
                "kind": shape.kind,
                "role": shape.role,
                "parent_id": shape.parent_shape_id,
                "depth": shape.depth,
                "paint": {
                    "fill": paint.fill,
                    "opacity": round(paint.alpha / 255, 4),
                },
                "area_px": round(shape.area, 2),
                "area_ratio": round(shape.area / canvas_area, 6),
                "bbox": {
                    "x": shape.bbox[0],
                    "y": shape.bbox[1],
                    "width": shape.bbox[2],
                    "height": shape.bbox[3],
                },
                "touches_canvas": shape.touches_canvas,
                "hole_count": shape.hole_count,
                "subpath_count": shape.subpath_count,
                "anchors": shape.anchors,
                "control_points": shape.control_points,
                "curve_segments": shape.curve_segments,
                "line_segments": shape.line_segments,
                "mean_contour_error_px": round(error_mean, 4),
                "maximum_contour_error_px": round(shape.maximum_contour_error, 4),
                "maximum_area_error_ratio": round(shape.maximum_area_error_ratio, 6),
                "compound_area_error_ratio": round(shape.compound_area_error_ratio, 6),
                "quality_fallback_contours": shape.quality_fallback_contours,
            }
        )
    layers = [
        {
            "id": f"layer-{role}",
            "role": role,
            "label_zh": ARTISAN_ROLE_LABELS_ZH[role],
            "draw_order": index,
            "shape_count": len(layer_shapes),
            "shape_ids": [shape.shape_id for shape in layer_shapes],
        }
        for index, (role, layer_shapes) in enumerate(scene.ordered_layers())
    ]
    core = {
        "schema_version": 1,
        "strategy": scene.strategy,
        "canvas": {"width": scene.width, "height": scene.height},
        "layers": layers,
        "shapes": shapes,
    }
    canonical = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    digest = hashlib.sha256(canonical).hexdigest()
    return {
        **core,
        "structure_sha256": digest,
        "structure_ref": f"artisan:{digest[:12]}",
        "interaction_contract": {
            "stable_shape_ids": True,
            "compact_reference": f"artisan:{digest[:12]}",
            "local_analysis_only": True,
            "external_ai_calls": 0,
            "edit_reference_format": "<structure_ref> <shape-id|layer-id> <change>",
        },
    }


def _design_preview(labels: Any, paints: dict[int, Paint]) -> Image.Image:
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    for label in [int(value) for value in np.unique(labels) if value >= 0]:
        paint = paints[label]
        rgba[labels == label] = (paint.red, paint.green, paint.blue, paint.alpha)
    return Image.fromarray(rgba, mode="RGBA")


def _artifact(path: Path, role: str, media_type: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": repo_relative(path),
        "media_type": media_type,
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "verified": True,
    }


def _markdown_report(report: dict[str, Any]) -> str:
    mode = report["mode"]
    source = report["source"]
    vector = report["vector"]
    exact = report.get("exact_validation")
    lines = [
        f"# {mode['label_zh']}报告",
        "",
        f"- 模式：`{mode['key']}`",
        f"- 原始尺寸：{source['width']} × {source['height']}",
        f"- 输出尺寸：{vector['width']} × {vector['height']}",
        f"- 处理后颜色：{vector['color_count']}",
        f"- 复合路径对象：{vector['path_objects']}",
        f"- 子路径：{vector['subpaths']}",
        f"- 节点：{vector['points']}",
        f"- 贝塞尔曲线段：{vector['curve_segments']}",
        f"- SVG 大小：{vector['svg_bytes']} bytes",
        f"- 嵌入位图：{report['validation']['embedded_raster_count']}",
        f"- 外部链接：{report['validation']['external_reference_count']}",
        f"- 转换耗时：{report['elapsed_seconds']} 秒",
    ]
    if exact is not None:
        lines.extend(
            [
                f"- 像素完全一致：{str(exact['pixel_match']).lower()}",
                f"- 不同像素数：{exact['different_pixel_count']}",
                f"- 最大通道差：{exact['maximum_channel_difference']}",
            ]
        )
    if mode["key"] == "artisan":
        lines.extend(
            [
                f"- 基准多边形锚点：{vector['baseline_polygon_anchors']}",
                f"- 锚点减少比例：{vector['anchor_reduction_ratio']:.1%}",
                f"- 平滑锚点：{vector['smooth_anchors']}",
                f"- 角点锚点：{vector['corner_anchors']}",
                f"- 平均轮廓误差：{vector['mean_contour_error_px']:.2f} px",
                f"- 最大轮廓误差：{vector['maximum_contour_error_px']:.2f} px",
                f"- 轮廓误差阈值：{vector['curve_error_tolerance_px']:.2f} px",
                f"- 平均面积误差：{vector['mean_shape_area_error_ratio']:.2%}",
                f"- 最大面积误差：{vector['maximum_shape_area_error_ratio']:.2%}",
                f"- 面积误差阈值：{vector['shape_area_error_tolerance_ratio']:.0%}",
                f"- 最大复合面积误差：{vector['maximum_compound_area_error_ratio']:.2%}",
                f"- 复合面积误差阈值：{vector['compound_area_error_tolerance_ratio']:.0%}",
                f"- 局部高保真回退：{vector['quality_fallback_contours']}",
                f"- 设计图层：{vector['layer_count']}",
                f"- 独立形状：{vector['shape_count']}",
                f"- 镂空形状组：{vector['knockout_shape_count']}",
                f"- 单形状最大子路径：{vector['maximum_subpaths_per_shape']}",
                f"- 嵌套形状：{vector['nested_shape_count']}",
                f"- 最大结构深度：{vector['maximum_structure_depth']}",
                f"- 孔洞：{vector['hole_count']}",
                f"- 结构引用：`{report['artisan_structure']['structure_ref']}`",
                "- 外部 AI 调用：0（本地结构分析）",
            ]
        )
        if vector.get("line_art_adaptation"):
            lines.extend(
                [
                    "- 线稿自适应：true",
                    f"- 墨线像素比例：{vector['ink_pixel_ratio']:.2%}",
                    f"- 估计线宽：{vector['estimated_stroke_width_px']:.2f} px",
                    f"- 省略的背景孔洞：{vector['suppressed_foundation_holes']}",
                    f"- 省略的背景小岛：{vector['suppressed_foundation_islands']}",
                ]
            )
    if report["warnings"]:
        lines.extend(["", "## 说明", "", *[f"- {item}" for item in report["warnings"]]])
    return "\n".join(lines) + "\n"


def _publish(staging: Path, output_dir: Path, filenames: tuple[str, ...]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        os.replace(staging / filename, output_dir / filename)


def run_vectorization(config: RunConfig) -> dict[str, Any]:
    started = time.perf_counter()
    preset = _configured(config)
    output_dir = resolve_output_dir(config.output_dir, config.reference_id, preset.mode)
    source_image, source = load_source(config.input_path, preset.max_source_pixels)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".vector-staging-", dir=output_dir.parent) as temp:
        staging = Path(temp)
        svg_path = staging / "vector.svg"
        preview_path = staging / "preview.png"
        warnings_list: list[str] = []
        exact_validation: dict[str, Any] | None = None
        artisan_structure: dict[str, Any] | None = None

        if preset.mode == "exact":
            rectangles = _merge_exact_rectangles(source_image, preset)
            exact_validation = _validate_exact_rectangles(source_image, rectangles)
            if not exact_validation["pixel_match"]:
                raise VectorizationError(
                    "pixel_validation_failed",
                    "Exact reconstruction did not match the source RGBA pixels.",
                )
            vector_metrics = _write_exact_svg(svg_path, source_image, rectangles)
            source_image.save(preview_path, format="PNG")
            work_image = source_image
            warnings_list.append(
                "精确重建描述的是源像素网格，不会创造新的图像细节，也不等同于轻量商业插画。"
            )
        else:
            _require_design_runtime()
            work_image = _resize_for_design(source_image, preset.max_dimension)
            rgba = np.asarray(work_image, dtype=np.uint8)
            prepared_rgb = _prepare_rgb(rgba, preset)
            line_art_metrics: dict[str, int | float | bool] = {}
            line_art_result = (
                _try_artisan_line_art(rgba, preset) if preset.mode == "artisan" else None
            )
            if line_art_result is not None:
                labels, paints, line_art_metrics = line_art_result
                cleanup_area = max(2, preset.min_region_area // 6)
            else:
                labels, paints = _build_paint_labels(rgba, prepared_rgb, preset)
                cleanup_area = preset.min_region_area
            labels, cleaned_regions = _cleanup_small_regions(labels, cleanup_area)
            if preset.mode == "artisan":
                from .artisan import ArtisanComplexityError, trace_artisan_scene

                try:
                    artisan_scene, vector_metrics = trace_artisan_scene(labels, preset)
                except ArtisanComplexityError as exc:
                    raise VectorizationError("vector_too_complex", str(exc)) from exc
                _write_artisan_svg(svg_path, artisan_scene, paints)
                artisan_structure = _artisan_structure_manifest(artisan_scene, paints)
                (staging / "artisan_structure.json").write_text(
                    json.dumps(artisan_structure, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            else:
                paths, vector_metrics = _trace_design_paths(labels, paints, preset)
                _write_design_svg(svg_path, work_image.width, work_image.height, paths)
            vector_metrics["cleaned_small_regions"] = cleaned_regions
            vector_metrics.update(line_art_metrics)
            _design_preview(labels, paints).save(preview_path, format="PNG")
            if preset.mode == "artisan":
                warnings_list.append(
                    "匠心模式使用少量锚点、贝塞尔曲线和本地构图层级推断；当前角色是几何设计角色，不宣称识别人脸、文字等内容语义。"
                )
                if line_art_metrics:
                    warnings_list.append(
                        "已自动启用本地线稿自适应：纹理背景简化为基础层，墨线作为独立形状组织。"
                    )
            else:
                warnings_list.append(
                    "智能与轻量模式会减色、清理小区域并简化轮廓，输出是可编辑近似结果，不保证逐像素一致。"
                )

        svg_size_limit = round(preset.max_svg_size_mb * 1024 * 1024)
        if svg_path.stat().st_size > svg_size_limit:
            raise VectorizationError(
                "vector_too_complex", "Generated SVG exceeds the configured file-size limit."
            )
        try:
            evidence = verify_svg_artifact(
                svg_path, expected_width=work_image.width, expected_height=work_image.height
            )
        except SvgArtifactError as exc:
            raise VectorizationError(exc.code, str(exc)) from exc
        if preset.mode == "artisan" and (
            evidence["layer_count"] != vector_metrics["layer_count"]
            or evidence["structured_path_count"] != vector_metrics["shape_count"]
            or evidence["nested_path_count"] != vector_metrics["nested_shape_count"]
            or evidence["maximum_structure_depth"] != vector_metrics["maximum_structure_depth"]
            or evidence["semantic_role_counts"] != vector_metrics["design_role_counts"]
        ):
            raise VectorizationError(
                "structure_validation_failed",
                "Artisan SVG structure does not match the generated edit manifest.",
            )

        final_svg = output_dir / "vector.svg"
        final_preview = output_dir / "preview.png"
        parameters_path = staging / "parameters.json"
        parameters_path.write_text(
            json.dumps(preset.public_parameters(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        elapsed = round(time.perf_counter() - started, 4)
        report: dict[str, Any] = {
            "ok": True,
            "task": "starbridge_vectorization",
            "mode": {
                "key": preset.mode,
                "label_zh": preset.label_zh,
                "purpose_zh": preset.purpose_zh,
                "default": preset.mode == "smart",
            },
            "source": source,
            "vector": {
                "width": work_image.width,
                "height": work_image.height,
                "path_objects": evidence["path_count"],
                "subpaths": evidence["subpath_count"],
                "points": evidence["anchor_point_count"],
                "coordinate_points": evidence["point_count"],
                "control_points": evidence["control_point_count"],
                "curve_segments": evidence["curve_segment_count"],
                "line_segments": evidence["line_segment_count"],
                "color_count": evidence["color_count"],
                "paint_count": evidence["paint_count"],
                "svg_bytes": evidence["bytes"],
                **{
                    key: value
                    for key, value in vector_metrics.items()
                    if key
                    in {
                        "cleaned_small_regions",
                        "skipped_contours",
                        "baseline_polygon_anchors",
                        "anchor_reduction_ratio",
                        "corner_anchors",
                        "smooth_anchors",
                        "source_contour_points",
                        "mean_contour_error_px",
                        "maximum_contour_error_px",
                        "curve_error_tolerance_px",
                        "mean_shape_area_error_ratio",
                        "maximum_shape_area_error_ratio",
                        "shape_area_error_tolerance_ratio",
                        "mean_compound_area_error_ratio",
                        "maximum_compound_area_error_ratio",
                        "compound_area_error_tolerance_ratio",
                        "adapted_contours",
                        "quality_fallback_contours",
                        "structure_strategy",
                        "layer_count",
                        "shape_count",
                        "knockout_shape_count",
                        "maximum_subpaths_per_shape",
                        "root_shape_count",
                        "nested_shape_count",
                        "maximum_structure_depth",
                        "hole_count",
                        "design_role_counts",
                        "stable_shape_references",
                        "external_ai_calls",
                        "line_art_adaptation",
                        "ink_pixel_ratio",
                        "estimated_stroke_width_px",
                        "line_art_threshold",
                        "line_art_color_separation",
                        "suppressed_foundation_holes",
                        "suppressed_foundation_islands",
                    }
                },
            },
            "validation": {
                "svg_verified": evidence["verified"],
                "image_trace_used": False,
                "embedded_raster_count": evidence["embedded_raster_count"],
                "external_reference_count": evidence["external_reference_count"],
                "safety_limits_exceeded": False,
            },
            "exact_validation": exact_validation,
            "artisan_structure": (
                {
                    "structure_ref": artisan_structure["structure_ref"],
                    "structure_sha256": artisan_structure["structure_sha256"],
                    "strategy": artisan_structure["strategy"],
                    "stable_shape_ids": True,
                    "external_ai_calls": 0,
                }
                if artisan_structure is not None
                else None
            ),
            "parameters": preset.public_parameters(),
            "output_dir": repo_relative(output_dir),
            "artifacts": [
                {
                    "role": "editable_svg",
                    "path": repo_relative(final_svg),
                    "media_type": "image/svg+xml",
                    "bytes": evidence["bytes"],
                    "sha256": evidence["sha256"],
                    "verified": True,
                },
                {
                    **_artifact(preview_path, "processed_preview", "image/png"),
                    "path": repo_relative(final_preview),
                },
            ],
            "elapsed_seconds": elapsed,
            "warnings": warnings_list,
        }
        publish_filenames = [
            "vector.svg",
            "preview.png",
            "parameters.json",
            "vector_report.json",
            "vector_report.md",
        ]
        if artisan_structure is not None:
            final_structure = output_dir / "artisan_structure.json"
            report["artifacts"].append(
                {
                    **_artifact(
                        staging / "artisan_structure.json",
                        "artisan_edit_structure",
                        "application/json",
                    ),
                    "path": repo_relative(final_structure),
                }
            )
            publish_filenames.append("artisan_structure.json")
        report_json = staging / "vector_report.json"
        report_markdown = staging / "vector_report.md"
        report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report_markdown.write_text(_markdown_report(report), encoding="utf-8")
        _publish(staging, output_dir, tuple(publish_filenames))
    return report
