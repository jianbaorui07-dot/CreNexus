from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .artisan import ArtisanComplexityError, ArtisanScene, _scene_metrics, trace_artisan_scene
from .presets import VectorPreset
from .svg_render import RENDERER_VERSION, SvgRenderError, render_verified_svg
from .svg_verify import SvgArtifactError, verify_svg_artifact


class AdaptiveOptimizationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QualityThresholds:
    key: str
    maximum_difference_percent: float
    maximum_normalized_mae: float
    minimum_edge_dice: float
    simplify_factors: tuple[float, ...]


QUALITY_PRESETS: dict[str, QualityThresholds] = {
    "high-fidelity": QualityThresholds("high-fidelity", 15.0, 0.06, 0.92, (1.8, 1.45, 1.2)),
    "balanced": QualityThresholds("balanced", 20.0, 0.08, 0.88, (2.2, 1.7, 1.3)),
    "minimal": QualityThresholds("minimal", 25.0, 0.10, 0.84, (3.0, 2.2, 1.5)),
}


@dataclass(frozen=True)
class AdaptiveOptions:
    quality_preset: str = "high-fidelity"
    target_difference: float | None = None
    anchor_budget: str | int = "auto"
    resource_budget: str = "auto"
    detail_protection: float = 0.75
    auto_minimize_anchors: bool = True


@dataclass(frozen=True)
class AdaptiveOptimizationResult:
    scene: ArtisanScene
    vector_metrics: dict[str, Any]
    svg_path: Path
    render_path: Path
    report: dict[str, Any]


def validated_options(options: AdaptiveOptions) -> tuple[AdaptiveOptions, QualityThresholds]:
    if options.quality_preset not in QUALITY_PRESETS:
        raise AdaptiveOptimizationError(
            "invalid_quality_preset",
            "Quality preset must be high-fidelity, balanced, or minimal.",
        )
    thresholds = QUALITY_PRESETS[options.quality_preset]
    if options.target_difference is not None:
        if not 5.0 <= options.target_difference <= 30.0:
            raise AdaptiveOptimizationError(
                "invalid_target_difference",
                "Target difference must be between 5 and 30 percent.",
            )
        thresholds = replace(
            thresholds,
            maximum_difference_percent=float(options.target_difference),
        )
    anchor_budget: str | int = options.anchor_budget
    if isinstance(anchor_budget, str):
        value = anchor_budget.strip().lower()
        if value != "auto":
            try:
                anchor_budget = int(value)
            except ValueError as exc:
                raise AdaptiveOptimizationError(
                    "invalid_anchor_budget", "Anchor budget must be auto or an integer."
                ) from exc
    if isinstance(anchor_budget, int) and not 1_000 <= anchor_budget <= 120_000:
        raise AdaptiveOptimizationError(
            "invalid_anchor_budget",
            "Manual anchor budget must be between 1,000 and 120,000.",
        )
    if options.resource_budget not in {"low", "auto", "high"}:
        raise AdaptiveOptimizationError(
            "invalid_resource_budget", "Resource budget must be low, auto, or high."
        )
    if not 0.0 <= options.detail_protection <= 1.0:
        raise AdaptiveOptimizationError(
            "invalid_detail_protection", "Detail protection must be between 0 and 1."
        )
    return replace(options, anchor_budget=anchor_budget), thresholds


def available_memory_bytes() -> int:
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
        except (AttributeError, OSError):
            pass
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * available_pages
    except (AttributeError, OSError, ValueError):
        return 512 * 1024 * 1024


def resource_limit_bytes(level: str, available: int | None = None) -> int:
    available = available if available is not None else available_memory_bytes()
    if level == "low":
        return min(round(available * 0.125), 512 * 1024 * 1024)
    if level == "high":
        return min(round(available * 0.5), 3 * 1024 * 1024 * 1024)
    return min(round(available * 0.25), round(1.5 * 1024 * 1024 * 1024))


def estimated_render_memory_bytes(width: int, height: int, supersample: int = 2) -> int:
    # Float RGBA canvas, fill/stroke masks, source buffer, comparison arrays and heat map.
    return width * height * (18 + 20 * supersample * supersample)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _composite_white(image: Image.Image) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = rgba[:, :, 3:4] / 255.0
    rgb = rgba[:, :, :3] * alpha + 255.0 * (1.0 - alpha)
    return rgb, rgba[:, :, 3]


def structural_similarity(first: np.ndarray[Any, Any], second: np.ndarray[Any, Any]) -> float:
    if first.shape != second.shape:
        raise AdaptiveOptimizationError(
            "render_size_mismatch", "Final render and reference dimensions do not match."
        )
    first = first.astype(np.float32)
    second = second.astype(np.float32)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    if min(first.shape[:2]) < 11:
        axes = (0, 1)
        mu_first = np.mean(first, axis=axes, keepdims=True)
        mu_second = np.mean(second, axis=axes, keepdims=True)
        var_first = np.mean((first - mu_first) ** 2, axis=axes, keepdims=True)
        var_second = np.mean((second - mu_second) ** 2, axis=axes, keepdims=True)
        covariance = np.mean((first - mu_first) * (second - mu_second), axis=axes, keepdims=True)
    else:
        mu_first = cv2.GaussianBlur(first, (11, 11), 1.5)
        mu_second = cv2.GaussianBlur(second, (11, 11), 1.5)
        var_first = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mu_first * mu_first
        var_second = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mu_second * mu_second
        covariance = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mu_first * mu_second
    numerator = (2 * mu_first * mu_second + c1) * (2 * covariance + c2)
    denominator = (mu_first * mu_first + mu_second * mu_second + c1) * (var_first + var_second + c2)
    score = float(np.mean(numerator / np.maximum(denominator, 1e-12)))
    return min(1.0, max(-1.0, score))


def _edge_mask(rgb: np.ndarray[Any, Any], detail_protection: float) -> np.ndarray[Any, Any]:
    gray = cv2.cvtColor(np.clip(rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    lower = round(72 - detail_protection * 36)
    upper = round(168 - detail_protection * 48)
    return cv2.Canny(gray, max(12, lower), max(36, upper)) > 0


def _edge_dice(
    first: np.ndarray[Any, Any], second: np.ndarray[Any, Any], detail_protection: float
) -> float:
    first_edge = _edge_mask(first, detail_protection)
    second_edge = _edge_mask(second, detail_protection)
    first_count = int(np.count_nonzero(first_edge))
    second_count = int(np.count_nonzero(second_edge))
    if first_count + second_count == 0:
        return 1.0
    kernel = np.ones((3, 3), dtype=np.uint8)
    first_near = cv2.dilate(first_edge.astype(np.uint8), kernel) > 0
    second_near = cv2.dilate(second_edge.astype(np.uint8), kernel) > 0
    first_matches = int(np.count_nonzero(first_edge & second_near))
    second_matches = int(np.count_nonzero(second_edge & first_near))
    return (first_matches + second_matches) / (first_count + second_count)


def _resize_for_planning(image: np.ndarray[Any, Any], maximum: int = 256) -> np.ndarray[Any, Any]:
    height, width = image.shape[:2]
    if max(width, height) <= maximum:
        return image
    ratio = maximum / max(width, height)
    return cv2.resize(
        image,
        (max(1, round(width * ratio)), max(1, round(height * ratio))),
        interpolation=cv2.INTER_AREA,
    )


def _quality_metrics(
    reference_rgb: np.ndarray[Any, Any],
    rendered_rgb: np.ndarray[Any, Any],
    reference_alpha: np.ndarray[Any, Any],
    rendered_alpha: np.ndarray[Any, Any],
    detail_protection: float,
) -> dict[str, float]:
    ssim = structural_similarity(reference_rgb, rendered_rgb)
    return {
        "ssim": round(ssim, 6),
        "difference_percent": round(max(0.0, (1.0 - ssim) * 100.0), 4),
        "normalized_mae": round(float(np.mean(np.abs(reference_rgb - rendered_rgb)) / 255.0), 6),
        "alpha_mae": round(float(np.mean(np.abs(reference_alpha - rendered_alpha)) / 255.0), 6),
        "edge_dice": round(_edge_dice(reference_rgb, rendered_rgb, detail_protection), 6),
    }


def _reference_analysis(
    *,
    reference_rgb: np.ndarray[Any, Any],
    reference_alpha: np.ndarray[Any, Any],
    source_sha256: str,
    cache_dir: Path,
    detail_protection: float,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], bool]:
    key = _digest(
        {
            "source": source_sha256,
            "shape": list(reference_rgb.shape),
            "detail_protection": detail_protection,
            "analysis": "pyramid-edge-distance-colors-v1",
        }
    )
    entry = cache_dir / "reference" / key[:2]
    cache_path = entry / f"{key}.npz"
    if cache_path.is_file():
        try:
            with np.load(cache_path, allow_pickle=False) as cached:
                low_rgb = cached["pyramid_rgb"].astype(np.float32)
                low_alpha = cached["pyramid_alpha"].astype(np.float32)
                # Load every required cached analysis so corrupt partial entries are rejected.
                cached["edges"]
                cached["distance_field"]
                cached["color_groups"]
            return low_rgb, low_alpha, True
        except (OSError, ValueError, KeyError):
            pass
    low_rgb = _resize_for_planning(reference_rgb)
    low_alpha = _resize_for_planning(reference_alpha)
    edges = _edge_mask(low_rgb, detail_protection).astype(np.uint8)
    distance = cv2.distanceTransform(1 - edges, cv2.DIST_L2, 3).astype(np.float32)
    quantized = (np.clip(low_rgb, 0, 255).astype(np.uint8) // 32).reshape((-1, 3))
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    order = np.argsort(-counts, kind="stable")[:64]
    color_groups = np.column_stack((colors[order], counts[order])).astype(np.int32)
    entry.mkdir(parents=True, exist_ok=True)
    temporary = entry / f".{key}.tmp.npz"
    np.savez_compressed(
        temporary,
        pyramid_rgb=low_rgb.astype(np.float32),
        pyramid_alpha=low_alpha.astype(np.float32),
        edges=edges,
        distance_field=distance,
        color_groups=color_groups,
    )
    os.replace(temporary, cache_path)
    return low_rgb, low_alpha, False


def _hotspots(
    reference_rgb: np.ndarray[Any, Any],
    rendered_rgb: np.ndarray[Any, Any],
    *,
    output_width: int,
    output_height: int,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], np.ndarray[Any, Any]]:
    residual = np.mean(np.abs(reference_rgb - rendered_rgb), axis=2) / 255.0
    planning = _resize_for_planning(residual, 256)
    height, width = planning.shape
    rows = min(8, max(2, height // 24))
    columns = min(8, max(2, width // 24))
    ranked: list[tuple[float, int, int, int, int]] = []
    for row in range(rows):
        y0 = row * height // rows
        y1 = (row + 1) * height // rows
        for column in range(columns):
            x0 = column * width // columns
            x1 = (column + 1) * width // columns
            tile = planning[y0:y1, x0:x1]
            score = float(np.mean(tile)) if tile.size else 0.0
            ranked.append((score, x0, y0, x1, y1))
    ranked.sort(key=lambda item: (-item[0], item[2], item[1]))
    result = []
    for rank, (score, x0, y0, x1, y1) in enumerate(ranked[:limit], start=1):
        result.append(
            {
                "rank": rank,
                "bbox": [
                    round(x0 / width * output_width),
                    round(y0 / height * output_height),
                    max(1, round((x1 - x0) / width * output_width)),
                    max(1, round((y1 - y0) / height * output_height)),
                ],
                "residual": round(score, 6),
            }
        )
    heatmap = np.clip(residual * 255.0 * 3.0, 0, 255).astype(np.uint8)
    return result, heatmap


def evaluate_svg_candidate(
    *,
    candidate_id: str,
    reference: Image.Image,
    source_sha256: str,
    svg_path: Path,
    render_path: Path,
    cache_dir: Path,
    thresholds: QualityThresholds,
    detail_protection: float,
    resource_limit: int,
    expected_svg_width: int,
    expected_svg_height: int,
) -> dict[str, Any]:
    estimated = estimated_render_memory_bytes(reference.width, reference.height)
    if estimated > resource_limit:
        raise AdaptiveOptimizationError(
            "resource_limit",
            "Final-resolution SVG validation exceeds the selected local resource budget.",
        )
    try:
        evidence = verify_svg_artifact(
            svg_path,
            expected_width=expected_svg_width,
            expected_height=expected_svg_height,
        )
    except SvgArtifactError as exc:
        raise AdaptiveOptimizationError(exc.code, str(exc)) from exc
    cache_key = _digest(
        {
            "source": source_sha256,
            "svg": evidence["sha256"],
            "renderer": RENDERER_VERSION,
            "width": reference.width,
            "height": reference.height,
            "thresholds": thresholds.__dict__,
            "detail_protection": detail_protection,
        }
    )
    entry = cache_dir / cache_key[:2] / cache_key
    cached_report = entry / "quality.json"
    cached_render = entry / "render.png"
    if cached_report.is_file() and cached_render.is_file():
        try:
            report = json.loads(cached_report.read_text(encoding="utf-8"))
            render_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached_render, render_path)
            report["candidate_id"] = candidate_id
            report["cache_hit"] = True
            return report
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    started = time.perf_counter()
    try:
        render_verified_svg(
            svg_path,
            render_path,
            expected_width=expected_svg_width,
            expected_height=expected_svg_height,
            supersample=2,
            output_width=reference.width,
            output_height=reference.height,
        )
    except SvgRenderError as exc:
        raise AdaptiveOptimizationError("svg_render_failed", str(exc)) from exc
    with Image.open(render_path) as rendered_image:
        rendered = rendered_image.convert("RGBA")
    reference_rgb, reference_alpha = _composite_white(reference)
    rendered_rgb, rendered_alpha = _composite_white(rendered)
    low_reference, low_reference_alpha, analysis_cache_hit = _reference_analysis(
        reference_rgb=reference_rgb,
        reference_alpha=reference_alpha,
        source_sha256=source_sha256,
        cache_dir=cache_dir,
        detail_protection=detail_protection,
    )
    low_rendered = _resize_for_planning(rendered_rgb)
    low_rendered_alpha = _resize_for_planning(rendered_alpha)
    planning_metrics = _quality_metrics(
        low_reference,
        low_rendered,
        low_reference_alpha,
        low_rendered_alpha,
        detail_protection,
    )
    final_metrics = _quality_metrics(
        reference_rgb,
        rendered_rgb,
        reference_alpha,
        rendered_alpha,
        detail_protection,
    )
    hotspots, heatmap = _hotspots(
        reference_rgb,
        rendered_rgb,
        output_width=expected_svg_width,
        output_height=expected_svg_height,
    )
    gates = {
        "structural_difference": (
            final_metrics["difference_percent"] <= thresholds.maximum_difference_percent
        ),
        "normalized_mae": (final_metrics["normalized_mae"] <= thresholds.maximum_normalized_mae),
        "edge_dice": final_metrics["edge_dice"] >= thresholds.minimum_edge_dice,
        "embedded_rasters": evidence["embedded_raster_count"] == 0,
        "external_references": evidence["external_reference_count"] == 0,
    }
    report = {
        "candidate_id": candidate_id,
        "status": "pass" if all(gates.values()) else "preview-only",
        "planning_resolution": [low_reference.shape[1], low_reference.shape[0]],
        "final_resolution": [reference.width, reference.height],
        "planning_metrics": planning_metrics,
        "final_render_metrics": final_metrics,
        "gates": gates,
        "vector": {
            "anchors": evidence["anchor_point_count"],
            "subpaths": evidence["subpath_count"],
            "bytes": evidence["bytes"],
            "paths": evidence["path_count"],
            "curves": evidence["curve_segment_count"],
        },
        "hotspots": hotspots,
        "svg_sha256": evidence["sha256"],
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "cache_hit": False,
        "reference_analysis_cache_hit": analysis_cache_hit,
    }
    entry.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(render_path, cached_render)
    Image.fromarray(heatmap, mode="L").save(entry / "heatmap.png", format="PNG")
    cached_report.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return report


def _topology_signature(scene: ArtisanScene) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            shape.shape_id,
            shape.kind,
            shape.parent_shape_id,
            shape.depth,
            shape.role,
            shape.subpath_count,
            shape.hole_count,
        )
        for shape in scene.shapes
    )


def _bbox_intersects(first: tuple[int, int, int, int], second: list[int]) -> bool:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    return not (
        first_x + first_width <= second_x
        or second_x + second_width <= first_x
        or first_y + first_height <= second_y
        or second_y + second_height <= first_y
    )


def _merged_scene(
    sparse: ArtisanScene, baseline: ArtisanScene, restored_ids: set[str]
) -> ArtisanScene:
    baseline_shapes = {shape.shape_id: shape for shape in baseline.shapes}
    return ArtisanScene(
        width=sparse.width,
        height=sparse.height,
        shapes=tuple(
            baseline_shapes[shape.shape_id] if shape.shape_id in restored_ids else shape
            for shape in sparse.shapes
        ),
        strategy="adaptive-local-refinement-v1",
    )


def _metrics_for_merged(
    scene: ArtisanScene, baseline_metrics: dict[str, Any], inherited: dict[str, Any]
) -> dict[str, Any]:
    metrics = _scene_metrics(
        scene,
        skipped_contours=int(baseline_metrics.get("skipped_contours", 0)),
        suppressed_foundation_holes=int(baseline_metrics.get("suppressed_foundation_holes", 0)),
        suppressed_foundation_islands=int(baseline_metrics.get("suppressed_foundation_islands", 0)),
        error_tolerance=float(baseline_metrics.get("curve_error_tolerance_px", 1.0)),
    )
    for key, value in inherited.items():
        metrics.setdefault(key, value)
    return metrics


def pareto_candidate_ids(candidates: list[dict[str, Any]]) -> list[str]:
    def dimensions(item: dict[str, Any]) -> tuple[float | int, ...]:
        return (
            item["final_render_metrics"]["difference_percent"],
            item["final_render_metrics"]["normalized_mae"],
            1.0 - item["final_render_metrics"]["edge_dice"],
            item["vector"]["anchors"],
            item["vector"]["subpaths"],
            item["vector"]["bytes"],
        )

    frontier = []
    for candidate in candidates:
        values = dimensions(candidate)
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            other_values = dimensions(other)
            if all(left <= right for left, right in zip(other_values, values)) and any(
                left < right for left, right in zip(other_values, values)
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(str(candidate["candidate_id"]))
    return sorted(frontier)


def select_passing_candidate(
    candidates: list[dict[str, Any]], baseline: dict[str, Any]
) -> dict[str, Any] | None:
    baseline_passed = baseline["status"] == "pass"
    eligible = [
        candidate
        for candidate in candidates
        if candidate["status"] == "pass"
        and (not baseline_passed or candidate["vector"]["anchors"] <= baseline["vector"]["anchors"])
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda candidate: (
            candidate["vector"]["anchors"],
            candidate["vector"]["subpaths"],
            candidate["vector"]["bytes"],
            candidate["elapsed_seconds"],
            candidate["candidate_id"],
        ),
    )


def optimize_artisan_scene(
    *,
    labels: Any,
    baseline_scene: ArtisanScene,
    baseline_metrics: dict[str, Any],
    baseline_svg: Path,
    reference: Image.Image,
    source_sha256: str,
    preset: VectorPreset,
    options: AdaptiveOptions,
    staging_dir: Path,
    cache_dir: Path,
    write_scene: Callable[[Path, ArtisanScene], None],
) -> AdaptiveOptimizationResult:
    options, thresholds = validated_options(options)
    limit = resource_limit_bytes(options.resource_budget)
    estimated = (
        estimated_render_memory_bytes(reference.width, reference.height)
        + int(getattr(labels, "nbytes", 0)) * 6
    )
    if estimated > limit:
        raise AdaptiveOptimizationError(
            "resource_limit",
            "Final-resolution SVG validation exceeds the selected local resource budget.",
        )
    adaptive_dir = staging_dir / ".adaptive-candidates"
    adaptive_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    states: dict[str, tuple[ArtisanScene, dict[str, Any], Path, Path]] = {}
    seen_hashes: set[str] = set()

    def add_candidate(
        candidate_id: str, scene: ArtisanScene, metrics: dict[str, Any], svg_path: Path
    ) -> dict[str, Any] | None:
        svg_hash = _sha256(svg_path)
        if svg_hash in seen_hashes:
            return None
        seen_hashes.add(svg_hash)
        render_path = adaptive_dir / f"{candidate_id}-render.png"
        record = evaluate_svg_candidate(
            candidate_id=candidate_id,
            reference=reference,
            source_sha256=source_sha256,
            svg_path=svg_path,
            render_path=render_path,
            cache_dir=cache_dir,
            thresholds=thresholds,
            detail_protection=options.detail_protection,
            resource_limit=limit,
            expected_svg_width=baseline_scene.width,
            expected_svg_height=baseline_scene.height,
        )
        records.append(record)
        states[candidate_id] = (scene, metrics, svg_path, render_path)
        return record

    baseline_record = add_candidate("baseline", baseline_scene, baseline_metrics, baseline_svg)
    if baseline_record is None:
        raise AdaptiveOptimizationError("optimizer_failed", "Baseline candidate was not evaluated.")
    stop_reason = "search_completed"
    generation_failures = 0
    sparse_states: list[tuple[dict[str, Any], ArtisanScene, dict[str, Any], Path]] = []
    baseline_signature = _topology_signature(baseline_scene)
    if options.auto_minimize_anchors:
        for index, factor in enumerate(thresholds.simplify_factors, start=1):
            candidate_id = f"sparse-{index}"
            candidate_svg = adaptive_dir / f"{candidate_id}.svg"
            candidate_preset = replace(
                preset,
                simplify_ratio=min(0.1, preset.simplify_ratio * factor),
            )
            try:
                scene, metrics = trace_artisan_scene(labels, candidate_preset)
            except ArtisanComplexityError:
                generation_failures += 1
                continue
            if _topology_signature(scene) != baseline_signature:
                generation_failures += 1
                continue
            write_scene(candidate_svg, scene)
            record = add_candidate(candidate_id, scene, metrics, candidate_svg)
            if record is not None:
                sparse_states.append((record, scene, metrics, candidate_svg))

    passing = [record for record in records if record["status"] == "pass"]
    best_anchor_target = min(
        (record["vector"]["anchors"] for record in passing),
        default=baseline_record["vector"]["anchors"],
    )
    local_source = min(
        (
            item
            for item in sparse_states
            if item[0]["vector"]["anchors"] < best_anchor_target and item[0]["status"] != "pass"
        ),
        key=lambda item: (
            item[0]["final_render_metrics"]["difference_percent"],
            item[0]["vector"]["anchors"],
        ),
        default=None,
    )
    stagnation_rounds = 0
    if options.auto_minimize_anchors and local_source is not None:
        source_record, sparse_scene, sparse_metrics, _ = local_source
        sparse_shapes = {shape.shape_id: shape for shape in sparse_scene.shapes}
        baseline_shapes = {shape.shape_id: shape for shape in baseline_scene.shapes}
        restored: set[str] = set()
        previous_difference = float(source_record["final_render_metrics"]["difference_percent"])
        previous_anchors = int(source_record["vector"]["anchors"])
        local_passed = False
        for round_index, hotspot in enumerate(source_record["hotspots"], start=1):
            eligible = [
                shape_id
                for shape_id, shape in sparse_shapes.items()
                if shape_id not in restored
                and baseline_shapes[shape_id].anchors > shape.anchors
                and _bbox_intersects(shape.bbox, hotspot["bbox"])
            ]
            eligible.sort(
                key=lambda shape_id: (
                    -(baseline_shapes[shape_id].anchors - sparse_shapes[shape_id].anchors),
                    shape_id,
                )
            )
            restored.update(eligible[:32])
            if not eligible:
                continue
            scene = _merged_scene(sparse_scene, baseline_scene, restored)
            metrics = _metrics_for_merged(scene, baseline_metrics, sparse_metrics)
            candidate_id = f"local-{round_index}"
            candidate_svg = adaptive_dir / f"{candidate_id}.svg"
            write_scene(candidate_svg, scene)
            record = add_candidate(candidate_id, scene, metrics, candidate_svg)
            if record is None:
                continue
            difference_improvement = previous_difference - float(
                record["final_render_metrics"]["difference_percent"]
            )
            anchor_change = abs(previous_anchors - int(record["vector"]["anchors"])) / max(
                1, previous_anchors
            )
            stagnation_rounds = (
                stagnation_rounds + 1
                if difference_improvement < 0.2 and anchor_change < 0.01
                else 0
            )
            previous_difference = float(record["final_render_metrics"]["difference_percent"])
            previous_anchors = int(record["vector"]["anchors"])
            if record["status"] == "pass":
                local_passed = True
                break
            if stagnation_rounds >= 2:
                stop_reason = "early_stagnation"
                break

        if local_passed and restored:
            # Reverse deletion: restore sparse geometry one shape at a time and retain only passes.
            for attempt, shape_id in enumerate(
                sorted(
                    restored,
                    key=lambda value: (
                        baseline_shapes[value].anchors - sparse_shapes[value].anchors,
                        value,
                    ),
                )[:8],
                start=1,
            ):
                trial = set(restored)
                trial.remove(shape_id)
                scene = _merged_scene(sparse_scene, baseline_scene, trial)
                metrics = _metrics_for_merged(scene, baseline_metrics, sparse_metrics)
                candidate_id = f"delete-{attempt}"
                candidate_svg = adaptive_dir / f"{candidate_id}.svg"
                write_scene(candidate_svg, scene)
                record = add_candidate(candidate_id, scene, metrics, candidate_svg)
                if record is not None and record["status"] == "pass":
                    restored = trial

    selected = select_passing_candidate(records, baseline_record)
    if selected is not None:
        if selected["candidate_id"] == "baseline":
            stop_reason = (
                "baseline_retained_no_anchor_improvement"
                if stop_reason == "search_completed"
                else stop_reason
            )
        elif stop_reason == "search_completed":
            stop_reason = "quality_passed_minimum_anchors"
        official = True
    else:
        selected = baseline_record
        stop_reason = "baseline_retained_no_passing_candidate"
        official = False
    scene, vector_metrics, svg_path, render_path = states[str(selected["candidate_id"])]
    anchor_before = int(baseline_record["vector"]["anchors"])
    anchor_after = int(selected["vector"]["anchors"])
    anchor_budget = options.anchor_budget
    budget_satisfied = anchor_budget == "auto" or anchor_after <= int(anchor_budget)
    thresholds_report = {
        "difference_percent": thresholds.maximum_difference_percent,
        "normalized_mae": thresholds.maximum_normalized_mae,
        "edge_dice": thresholds.minimum_edge_dice,
    }
    quality_core = {
        "svg_sha256": selected["svg_sha256"],
        "thresholds": thresholds_report,
        "metrics": selected["final_render_metrics"],
    }
    quality_digest = _digest(quality_core)
    patch_digest = _digest(
        {
            "baseline": baseline_record["svg_sha256"],
            "selected": selected["svg_sha256"],
            "anchors": [anchor_before, anchor_after],
        }
    )
    compact_candidates = [
        {
            "id": record["candidate_id"],
            "status": record["status"],
            "difference_percent": record["final_render_metrics"]["difference_percent"],
            "mae": record["final_render_metrics"]["normalized_mae"],
            "edge_dice": record["final_render_metrics"]["edge_dice"],
            "anchors": record["vector"]["anchors"],
            "subpaths": record["vector"]["subpaths"],
            "bytes": record["vector"]["bytes"],
            "cache_hit": record["cache_hit"],
        }
        for record in records
    ]
    report = {
        "schema_version": 1,
        "status": "pass" if official else "baseline-retained",
        "official_optimization_result": official,
        "quality_preset": thresholds.key,
        "thresholds": thresholds_report,
        "selected_candidate": selected["candidate_id"],
        "candidate_count": len(records),
        "pareto_candidates": pareto_candidate_ids(records),
        "candidates": compact_candidates,
        "final_render_metrics": selected["final_render_metrics"],
        "planning_metrics": selected["planning_metrics"],
        "anchors": {
            "before": anchor_before,
            "after": anchor_after,
            "change": anchor_after - anchor_before,
            "reduction_ratio": round(
                max(0.0, 1.0 - anchor_after / anchor_before) if anchor_before else 0.0,
                6,
            ),
            "budget": anchor_budget,
            "budget_satisfied": budget_satisfied,
            "quality_gate_priority": True,
        },
        "cache": {
            "hits": sum(bool(record["cache_hit"]) for record in records),
            "evaluations": len(records),
            "hit_rate": round(
                sum(bool(record["cache_hit"]) for record in records) / len(records), 6
            ),
        },
        "resource": {
            "level": options.resource_budget,
            "limit_bytes": limit,
            "estimated_peak_bytes": estimated,
            "candidate_parallel_limit": 2,
        },
        "stop_reason": stop_reason,
        "generation_failures": generation_failures,
        "error_hotspots": selected["hotspots"][:5],
        "quality_ref": f"quality:{quality_digest[:12]}",
        "patch_ref": f"patch:{patch_digest[:12]}",
        "external_ai_calls": 0,
        "renderer": RENDERER_VERSION,
    }
    return AdaptiveOptimizationResult(scene, vector_metrics, svg_path, render_path, report)
