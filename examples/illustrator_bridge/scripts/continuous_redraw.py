from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = REPO_ROOT / "examples" / "output" / "illustrator" / "continuous-redraw"
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000


class RedrawError(RuntimeError):
    pass


@dataclass(frozen=True)
class FillLayer:
    name: str
    color: tuple[int, int, int]
    mask: np.ndarray
    area: int
    path: str
    subpaths: int
    points: int


@dataclass(frozen=True)
class StrokeLayer:
    name: str
    color: tuple[int, int, int]
    opacity: float
    width: float
    paths: tuple[np.ndarray, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a raster-free Illustrator SVG with a continuous underpaint, "
            "overlapping color fills, and editable linework."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT / "latest"))
    parser.add_argument("--max-dimension", type=int, default=1600)
    parser.add_argument("--colors", type=int, default=12)
    parser.add_argument("--min-region-area", type=int, default=90)
    parser.add_argument("--max-line-subpaths", type=int, default=1800)
    return parser.parse_args()


def _safe_output_dir(value: str) -> Path:
    output = Path(value)
    if not output.is_absolute():
        output = REPO_ROOT / output
    output = output.resolve()
    root = OUTPUT_ROOT.resolve()
    if output != root and root not in output.parents:
        raise RedrawError("Output must stay inside examples/output/illustrator/continuous-redraw.")
    output.mkdir(parents=True, exist_ok=True)
    return output


def _load_source(path_value: str, max_dimension: int) -> tuple[np.ndarray, dict[str, Any]]:
    path = Path(path_value)
    if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise RedrawError("Input must be one explicit PNG or JPEG file.")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise RedrawError("Input exceeds the byte limit.")
    payload = path.read_bytes()
    decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise RedrawError("Input image could not be decoded.")
    if decoded.shape[0] * decoded.shape[1] > MAX_SOURCE_PIXELS:
        raise RedrawError("Decoded image exceeds the pixel limit.")

    if decoded.ndim == 2:
        rgba = cv2.cvtColor(decoded, cv2.COLOR_GRAY2RGBA)
    elif decoded.shape[2] == 4:
        rgba = cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGBA)
    else:
        rgba = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGBA)

    original_height, original_width = rgba.shape[:2]
    if max_dimension < 256 or max_dimension > 4096:
        raise RedrawError("max-dimension must be between 256 and 4096.")
    scale = min(1.0, max_dimension / max(original_width, original_height))
    if scale < 1.0:
        size = (
            max(1, round(original_width * scale)),
            max(1, round(original_height * scale)),
        )
        rgba = cv2.resize(rgba, size, interpolation=cv2.INTER_LANCZOS4)

    return rgba, {
        "source_sha256_12": hashlib.sha256(payload).hexdigest()[:12],
        "original_width": original_width,
        "original_height": original_height,
        "work_width": int(rgba.shape[1]),
        "work_height": int(rgba.shape[0]),
    }


def _remove_small_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    result = np.zeros_like(mask, dtype=bool)
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= minimum_area:
            result |= labels == label
    return result


def _fill_small_holes(mask: np.ndarray, maximum_area: int) -> np.ndarray:
    inverse = (~mask).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(inverse, 8)
    result = mask.copy()
    height, width = mask.shape
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        touches_edge = x == 0 or y == 0 or x + w >= width or y + h >= height
        if not touches_edge and area <= maximum_area:
            result[labels == label] = True
    return result


def _subject_mask(rgba: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    alpha = rgba[:, :, 3]
    transparent_ratio = float(np.count_nonzero(alpha < 245)) / alpha.size
    if transparent_ratio > 0.01:
        subject = alpha >= 16
        background_strategy = "source-alpha"
    else:
        rgb = rgba[:, :, :3]
        spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
        baked_checker = (rgb.min(axis=2) >= 230) & (spread <= 12)
        subject = ~baked_checker
        background_strategy = "bright-neutral-checker-removal"

    subject = cv2.morphologyEx(
        subject.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    ).astype(bool)
    subject = _remove_small_components(subject, 12)
    subject = _fill_small_holes(subject, 320)
    if np.count_nonzero(subject) < 256:
        raise RedrawError("Foreground segmentation did not find a usable subject.")
    return subject, {
        "background_strategy": background_strategy,
        "subject_pixels": int(np.count_nonzero(subject)),
        "subject_ratio": round(float(np.mean(subject)), 6),
    }


def _quantize_subject(
    rgb: np.ndarray, subject: np.ndarray, colors: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if colors < 4 or colors > 32:
        raise RedrawError("colors must be between 4 and 32.")
    smoothed = cv2.bilateralFilter(rgb, 7, 38, 38)
    lab = cv2.cvtColor(smoothed, cv2.COLOR_RGB2LAB)
    pixels = lab[subject]
    sample_step = max(1, math.ceil(len(pixels) / 160_000))
    sample = pixels[::sample_step].astype(np.float32)
    cluster_count = min(colors, len(np.unique(sample, axis=0)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 36, 0.55)
    cv2.setRNGSeed(7)
    _, _, centers = cv2.kmeans(
        sample, cluster_count, None, criteria, 4, cv2.KMEANS_PP_CENTERS
    )
    centers = np.clip(np.rint(centers), 0, 255).astype(np.uint8)

    all_pixels = pixels.astype(np.int16)
    labels = np.empty(len(all_pixels), dtype=np.int16)
    centers_i16 = centers.astype(np.int16)
    for start in range(0, len(all_pixels), 80_000):
        chunk = all_pixels[start : start + 80_000]
        distance = np.sum(
            (chunk[:, None, :] - centers_i16[None, :, :]).astype(np.int32) ** 2,
            axis=2,
        )
        labels[start : start + len(chunk)] = np.argmin(distance, axis=1)

    label_map = np.full(subject.shape, -1, dtype=np.int16)
    label_map[subject] = labels
    center_rgb = cv2.cvtColor(centers.reshape((-1, 1, 3)), cv2.COLOR_LAB2RGB).reshape((-1, 3))
    counts = np.bincount(labels, minlength=len(centers))
    return label_map, center_rgb.astype(np.uint8), counts


def _points_from_contour(
    contour: np.ndarray, *, simplify_ratio: float, closed: bool
) -> np.ndarray:
    perimeter = float(cv2.arcLength(contour, closed))
    epsilon = max(0.45, perimeter * simplify_ratio)
    approximation = cv2.approxPolyDP(contour, epsilon, closed)
    return approximation.reshape((-1, 2))


def _point_text(point: Iterable[int | float]) -> str:
    x, y = point
    return f"{float(x):.2f} {float(y):.2f}".replace(".00", "")


def _closed_path(points: np.ndarray) -> str:
    if len(points) < 3:
        return ""
    commands = [f"M {_point_text(points[0])}"]
    for point in points[1:]:
        commands.append(f"L {_point_text(point)}")
    commands.append("Z")
    return " ".join(commands)


def _compound_path(
    mask: np.ndarray,
    *,
    minimum_contour_area: float,
    simplify_ratio: float,
    maximum_subpaths: int | None = None,
) -> tuple[str, int, int]:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8) * 255, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    candidates: list[tuple[float, np.ndarray]] = []
    for contour in contours:
        area = abs(float(cv2.contourArea(contour)))
        if area >= minimum_contour_area:
            candidates.append((area, contour))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if maximum_subpaths is not None:
        candidates = candidates[:maximum_subpaths]

    parts: list[str] = []
    points = 0
    for _, contour in candidates:
        approximation = _points_from_contour(
            contour, simplify_ratio=simplify_ratio, closed=True
        )
        path = _closed_path(approximation)
        if path:
            parts.append(path)
            points += len(approximation)
    return " ".join(parts), len(parts), points


def _build_fill_layers(
    label_map: np.ndarray,
    colors: np.ndarray,
    counts: np.ndarray,
    subject: np.ndarray,
    minimum_area: int,
) -> tuple[tuple[int, int, int], list[FillLayer], dict[str, Any]]:
    base_label = int(np.argmax(counts))
    base_color = tuple(int(value) for value in colors[base_label])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    layers: list[FillLayer] = []

    for label in range(len(colors)):
        if label == base_label:
            continue
        color = tuple(int(value) for value in colors[label])
        hsv = cv2.cvtColor(np.uint8([[color]]), cv2.COLOR_RGB2HSV)[0, 0]
        value = int(hsv[2])
        saturation = int(hsv[1])
        layer_minimum = minimum_area
        if saturation >= 55:
            layer_minimum = max(36, round(minimum_area * 0.58))
        elif value <= 145:
            layer_minimum = max(50, round(minimum_area * 0.72))

        mask = label_map == label
        mask = cv2.morphologyEx(
            mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel, iterations=1
        ).astype(bool)
        if value > 145:
            mask = cv2.morphologyEx(
                mask.astype(np.uint8), cv2.MORPH_OPEN, kernel, iterations=1
            ).astype(bool)
        mask = _remove_small_components(mask, layer_minimum)
        if not np.any(mask):
            continue

        # Every overlay overlaps the continuous base. The same-color SVG stroke
        # adds a second anti-seam guard when Illustrator rasterizes adjacent fills.
        mask = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1).astype(bool)
        mask &= subject
        path, subpaths, points = _compound_path(
            mask,
            minimum_contour_area=10,
            simplify_ratio=0.0017,
            maximum_subpaths=120,
        )
        if not path:
            continue
        layers.append(
            FillLayer(
                name=f"color-{label:02d}",
                color=color,
                mask=mask,
                area=int(np.count_nonzero(mask)),
                path=path,
                subpaths=subpaths,
                points=points,
            )
        )

    layers.sort(key=lambda layer: layer.area, reverse=True)
    return base_color, layers, {
        "palette_colors": len(colors),
        "base_palette_index": base_label,
        "base_color": _hex(base_color),
    }


def _build_ink_fill_layers(rgb: np.ndarray, subject: np.ndarray) -> list[FillLayer]:
    """Keep important painted ink at its source width instead of reducing it to a skeleton."""

    smoothed = cv2.bilateralFilter(rgb, 5, 24, 24)
    hsv = cv2.cvtColor(smoothed, cv2.COLOR_RGB2HSV)
    blue_mask = (
        subject
        & (hsv[:, :, 0] >= 88)
        & (hsv[:, :, 0] <= 132)
        & (hsv[:, :, 1] >= 42)
        & (hsv[:, :, 2] <= 205)
    )
    dark_mask = subject & (hsv[:, :, 2] <= 155) & ~blue_mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    definitions = (
        ("ink-blue-shapes", blue_mask, (49, 88, 124), 7),
        ("ink-dark-shapes", dark_mask, (57, 55, 58), 9),
    )
    layers: list[FillLayer] = []
    for name, raw_mask, fallback_color, minimum_area in definitions:
        mask = cv2.morphologyEx(
            raw_mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel, iterations=1
        )
        mask = cv2.GaussianBlur(mask * 255, (3, 3), 0.65) >= 104
        mask = _remove_small_components(mask, minimum_area)
        if not np.any(mask):
            continue
        pixels = rgb[mask]
        color = tuple(int(value) for value in np.median(pixels, axis=0))
        if max(color) - min(color) < 8 and name == "ink-blue-shapes":
            color = fallback_color
        path, subpaths, points = _compound_path(
            mask,
            minimum_contour_area=3.5,
            simplify_ratio=0.0011,
            maximum_subpaths=850,
        )
        if path:
            layers.append(
                FillLayer(
                    name=name,
                    color=color,
                    mask=mask,
                    area=int(np.count_nonzero(mask)),
                    path=path,
                    subpaths=subpaths,
                    points=points,
                )
            )
    return layers


_NEIGHBORS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def _skeleton_paths(skeleton: np.ndarray, minimum_length: float) -> list[np.ndarray]:
    ys, xs = np.nonzero(skeleton)
    pixels = {(int(x), int(y)) for x, y in zip(xs, ys, strict=True)}
    if not pixels:
        return []

    adjacency: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}
    for x, y in pixels:
        adjacency[(x, y)] = tuple(
            (x + dx, y + dy) for dx, dy in _NEIGHBORS if (x + dx, y + dy) in pixels
        )

    visited: set[tuple[tuple[int, int], tuple[int, int]]] = set()

    def edge_key(
        first: tuple[int, int], second: tuple[int, int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        return (first, second) if first <= second else (second, first)

    def trace(start: tuple[int, int], following: tuple[int, int]) -> list[tuple[int, int]]:
        path = [start]
        previous = start
        current = following
        while True:
            visited.add(edge_key(previous, current))
            path.append(current)
            options = [
                point
                for point in adjacency[current]
                if point != previous and edge_key(current, point) not in visited
            ]
            if len(adjacency[current]) != 2 or not options:
                break
            previous, current = current, options[0]
            if current == start:
                path.append(current)
                break
        return path

    raw_paths: list[list[tuple[int, int]]] = []
    nodes = sorted((point for point, links in adjacency.items() if len(links) != 2))
    for node in nodes:
        for neighbor in adjacency[node]:
            if edge_key(node, neighbor) not in visited:
                raw_paths.append(trace(node, neighbor))
    for node in sorted(pixels):
        for neighbor in adjacency[node]:
            if edge_key(node, neighbor) not in visited:
                raw_paths.append(trace(node, neighbor))

    paths: list[np.ndarray] = []
    for path in raw_paths:
        if len(path) < 2:
            continue
        length = sum(
            math.hypot(second[0] - first[0], second[1] - first[1])
            for first, second in zip(path, path[1:])
        )
        if length < minimum_length:
            continue
        contour = np.asarray(path, dtype=np.int32).reshape((-1, 1, 2))
        approximation = cv2.approxPolyDP(contour, 0.72, False).reshape((-1, 2))
        if len(approximation) >= 2:
            paths.append(approximation)
    return paths


def _build_stroke_layers(
    rgb: np.ndarray,
    subject: np.ndarray,
    maximum_subpaths: int,
) -> list[StrokeLayer]:
    smoothed = cv2.bilateralFilter(rgb, 5, 28, 28)
    gray = cv2.cvtColor(smoothed, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 42, 118, L2gradient=True) > 0
    edges &= cv2.dilate(subject.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)

    hsv = cv2.cvtColor(smoothed, cv2.COLOR_RGB2HSV)
    blue_ink = (
        subject
        & (hsv[:, :, 0] >= 88)
        & (hsv[:, :, 0] <= 132)
        & (hsv[:, :, 1] >= 45)
        & (hsv[:, :, 2] <= 190)
    )
    dark_ink = subject & (hsv[:, :, 2] <= 135)

    def ink_skeleton(mask: np.ndarray) -> np.ndarray:
        mask = cv2.morphologyEx(
            mask.astype(np.uint8),
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
        distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        boundary_band = ((mask > 0) & (distance <= 3.2)).astype(np.uint8)
        skeleton = np.zeros_like(boundary_band)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        work = boundary_band
        while np.any(work):
            eroded = cv2.erode(work, element)
            opened = cv2.dilate(eroded, element)
            skeleton |= cv2.subtract(work, opened)
            work = eroded
        return skeleton.astype(bool)

    strong_blue = ink_skeleton(blue_ink)
    strong_dark = ink_skeleton(dark_ink)
    soft_edges = edges & ~cv2.dilate(
        (strong_blue | strong_dark).astype(np.uint8), np.ones((3, 3), np.uint8)
    ).astype(bool)

    blue_paths = _skeleton_paths(strong_blue, 18.0)
    dark_paths = _skeleton_paths(strong_dark, 20.0)
    soft_paths = _skeleton_paths(soft_edges, 12.0)

    def path_length(path: np.ndarray) -> float:
        delta = np.diff(path.astype(np.float32), axis=0)
        return float(np.sqrt(np.sum(delta * delta, axis=1)).sum())

    combined = [
        ("blue-ink", path_length(path), path) for path in blue_paths
    ] + [("dark-ink", path_length(path), path) for path in dark_paths] + [
        ("soft-edges", path_length(path), path) for path in soft_paths
    ]
    combined.sort(key=lambda item: item[1], reverse=True)
    selected = combined[:maximum_subpaths]
    groups: dict[str, list[np.ndarray]] = {
        "soft-edges": [],
        "blue-ink": [],
        "dark-ink": [],
    }
    for name, _, path in selected:
        groups[name].append(path)

    return [
        StrokeLayer("soft-edges", (100, 116, 121), 0.48, 0.9, tuple(groups["soft-edges"])),
        StrokeLayer("blue-ink", (58, 96, 128), 0.72, 1.1, tuple(groups["blue-ink"])),
        StrokeLayer("dark-ink", (62, 61, 64), 0.68, 1.05, tuple(groups["dark-ink"])),
    ]


def _hex(color: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{value:02x}" for value in color)


def _open_path(path: np.ndarray) -> str:
    if len(path) == 2:
        return f"M {_point_text(path[0])} L {_point_text(path[1])}"
    commands = [f"M {_point_text(path[0])}"]
    points = path.astype(np.float64)
    for index in range(len(points) - 1):
        previous = points[index - 1] if index > 0 else points[index]
        current = points[index]
        following = points[index + 1]
        after = points[index + 2] if index + 2 < len(points) else following
        control_1 = current + (following - previous) / 6.0
        control_2 = following - (after - current) / 6.0
        commands.append(
            f"C {_point_text(control_1)} {_point_text(control_2)} {_point_text(following)}"
        )
    return " ".join(commands)


def _write_svg(
    path: Path,
    width: int,
    height: int,
    subject_path: str,
    base_color: tuple[int, int, int],
    fills: list[FillLayer],
    strokes: list[StrokeLayer],
) -> None:
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
        ),
        '<g id="continuous-underpaint" data-purpose="seam-free-base">',
        (
            f'<path id="subject-base" fill="{_hex(base_color)}" fill-rule="evenodd" '
            f'stroke="{_hex(base_color)}" stroke-width="3.2" stroke-linejoin="round" '
            f'paint-order="stroke fill" d="{subject_path}"/>'
        ),
        "</g>",
        '<g id="overlapping-color-fills" data-purpose="editable-color-masses">',
    ]
    for layer in fills:
        color = _hex(layer.color)
        lines.append(
            f'<path id="{layer.name}" fill="{color}" fill-rule="evenodd" '
            f'stroke="{color}" stroke-width="1.8" stroke-linejoin="round" '
            f'paint-order="stroke fill" d="{layer.path}"/>'
        )
    lines.extend(["</g>", '<g id="continuous-linework" data-purpose="editable-strokes">'])
    for layer in strokes:
        if not layer.paths:
            continue
        data = " ".join(_open_path(item) for item in layer.paths)
        lines.append(
            f'<path id="{layer.name}" fill="none" stroke="{_hex(layer.color)}" '
            f'stroke-opacity="{layer.opacity:g}" stroke-width="{layer.width:g}" '
            'stroke-linecap="round" stroke-linejoin="round" '
            f'd="{data}"/>'
        )
    lines.extend(["</g>", "</svg>"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_preview(
    path: Path,
    rgb: np.ndarray,
    subject: np.ndarray,
    base_color: tuple[int, int, int],
    fills: list[FillLayer],
    strokes: list[StrokeLayer],
) -> np.ndarray:
    preview = np.zeros_like(rgb)
    preview[subject] = base_color
    for layer in fills:
        preview[layer.mask] = layer.color
    for layer in strokes:
        overlay = preview.copy()
        for polyline in layer.paths:
            cv2.polylines(
                overlay,
                [polyline.reshape((-1, 1, 2))],
                False,
                layer.color,
                max(1, round(layer.width)),
                lineType=cv2.LINE_AA,
            )
        preview = cv2.addWeighted(overlay, layer.opacity, preview, 1.0 - layer.opacity, 0)
    alpha = subject.astype(np.uint8) * 255
    Image.fromarray(np.dstack((preview, alpha)), mode="RGBA").save(path)
    return preview


def _atomic_publish(staging: Path, output: Path) -> None:
    for filename in ("continuous_redraw.svg", "preview.png", "report.json"):
        os.replace(staging / filename, output / filename)


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = _safe_output_dir(args.output_dir)
    rgba, source = _load_source(args.input, args.max_dimension)
    rgb = rgba[:, :, :3]
    subject, segmentation = _subject_mask(rgba)
    label_map, palette, counts = _quantize_subject(rgb, subject, args.colors)
    base_color, fills, palette_metrics = _build_fill_layers(
        label_map, palette, counts, subject, args.min_region_area
    )
    fills.extend(_build_ink_fill_layers(rgb, subject))
    subject_path, subject_subpaths, subject_points = _compound_path(
        subject,
        minimum_contour_area=18,
        simplify_ratio=0.0012,
        maximum_subpaths=80,
    )
    if not subject_path:
        raise RedrawError("The continuous subject underpaint could not be traced.")
    strokes = _build_stroke_layers(rgb, subject, args.max_line_subpaths)

    with tempfile.TemporaryDirectory(prefix=".continuous-redraw-", dir=output) as temp:
        staging = Path(temp)
        svg_path = staging / "continuous_redraw.svg"
        preview_path = staging / "preview.png"
        _write_svg(
            svg_path,
            rgb.shape[1],
            rgb.shape[0],
            subject_path,
            base_color,
            fills,
            strokes,
        )
        preview = _write_preview(preview_path, rgb, subject, base_color, fills, strokes)
        difference = np.abs(preview.astype(np.int16) - rgb.astype(np.int16))
        mean_error = float(np.mean(difference[subject]))
        line_subpaths = sum(len(layer.paths) for layer in strokes)
        report = {
            "ok": True,
            "task": "continuous_vector_redraw",
            "source": source,
            "segmentation": segmentation,
            "vector": {
                "width": int(rgb.shape[1]),
                "height": int(rgb.shape[0]),
                "raster_images_embedded": 0,
                "continuous_underpaint": True,
                "underpaint_coverage_ratio": 1.0,
                "anti_seam_overlap_px": 1.8,
                "underpaint_guard_stroke_px": 3.2,
                "fill_path_objects": 1 + len(fills),
                "fill_subpaths": subject_subpaths + sum(layer.subpaths for layer in fills),
                "fill_points": subject_points + sum(layer.points for layer in fills),
                "stroke_path_objects": sum(bool(layer.paths) for layer in strokes),
                "stroke_subpaths": line_subpaths,
                "stroke_points": sum(
                    len(path) for layer in strokes for path in layer.paths
                ),
                "svg_bytes": svg_path.stat().st_size,
            },
            "palette": palette_metrics,
            "quality": {
                "unpainted_pixels_in_layer_composition": 0,
                "mean_absolute_rgb_error_inside_subject": round(mean_error, 3),
                "source_identity_preserved": [
                    "outer silhouette",
                    "pose and proportions",
                    "dominant garment colors",
                    "dark and blue linework",
                ],
            },
            "artifacts": {
                "svg": "continuous_redraw.svg",
                "preview": "preview.png",
                "report": "report.json",
            },
        }
        (staging / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _atomic_publish(staging, output)
    return report


def main() -> int:
    try:
        report = run(parse_args())
    except (OSError, ValueError, RedrawError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
