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
            labels, paints = _build_paint_labels(rgba, prepared_rgb, preset)
            labels, cleaned_regions = _cleanup_small_regions(labels, preset.min_region_area)
            if preset.mode == "artisan":
                from .artisan import ArtisanComplexityError, trace_artisan_paths

                try:
                    artisan_paths, vector_metrics = trace_artisan_paths(labels, preset)
                except ArtisanComplexityError as exc:
                    raise VectorizationError("vector_too_complex", str(exc)) from exc
                paths = [(paints[label], path_parts) for label, path_parts in artisan_paths.items()]
            else:
                paths, vector_metrics = _trace_design_paths(labels, paints, preset)
            vector_metrics["cleaned_small_regions"] = cleaned_regions
            _write_design_svg(svg_path, work_image.width, work_image.height, paths)
            _design_preview(labels, paints).save(preview_path, format="PNG")
            if preset.mode == "artisan":
                warnings_list.append(
                    "匠心模式使用少量锚点和贝塞尔曲线重建轮廓；当前迭代属于几何艺术化重建，尚未使用语义分割模型。"
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
                        "adapted_contours",
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
        report_json = staging / "vector_report.json"
        report_markdown = staging / "vector_report.md"
        report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        report_markdown.write_text(_markdown_report(report), encoding="utf-8")
        _publish(
            staging,
            output_dir,
            (
                "vector.svg",
                "preview.png",
                "parameters.json",
                "vector_report.json",
                "vector_report.md",
            ),
        )
    return report
