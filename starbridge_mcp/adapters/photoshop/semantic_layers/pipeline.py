from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .intent import (
    client_questions,
    intent_profile_hash,
    load_intent_profile,
    normalise_intent_profile,
    recommended_intent_profile,
)
from .manifest import GROUPS_BOTTOM_TO_TOP, SCHEMA_VERSION, load_manifest, write_manifest

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
LINE_ART_STRATEGIES = {"line_art_on_texture", "monochrome_line_art"}
PIPELINE_VERSION = "starbridge.image_to_editable_psd.pipeline.v10"


@dataclass(frozen=True)
class DecompositionOptions:
    preset: str = "auto"
    subject_engine: str = "offline_iterative"
    max_refinements: int = 3
    text_mode: str = "conservative"
    resolution: int = 72
    review_region_limit: int = 8


def _deps() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError as exc:  # pragma: no cover - covered by dependency-specific setup
        raise RuntimeError(
            "Image decomposition requires Pillow, numpy, and opencv-python-headless. "
            "Install with: pip install -e .[image-to-psd]"
        ) from exc
    return cv2, np, Image, ImageDraw, ImageFilter


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value).strip("_-")
    return cleaned[:64] or "image"


def _source_summary(path: Path) -> dict[str, Any]:
    _, _, Image, _, _ = _deps()
    with Image.open(path) as image:
        width, height = image.size
        mode = image.mode
    digest = _sha256(path)
    return {
        "name": path.name,
        "sha256": digest,
        "sha256_12": digest[:12],
        "width": width,
        "height": height,
        "mode": mode,
    }


def plan_image(
    input_path: str | Path, options: DecompositionOptions | None = None
) -> dict[str, Any]:
    source_path = Path(input_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError("Input image does not exist")
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {source_path.suffix}")
    options = options or DecompositionOptions()
    source = _source_summary(source_path)
    strategy = _recommend_strategy(_load_rgb(source_path), options.preset)
    intent_profile = recommended_intent_profile(
        strategy["id"],
        text_mode=options.text_mode,
        review_region_limit=options.review_region_limit,
    )
    strategy_stages = (
        [
            "composition_center_and_circle_geometry_check",
            "local_subject_candidate_search",
            "low_ink_density_boundary_warping",
            "stroke_continuity_check",
        ]
        if strategy["id"] in LINE_ART_STRATEGIES
        else [
            "local_subject_candidate_search",
            "conservative_text_region_detection",
        ]
    )
    return {
        "ok": True,
        "dry_run": True,
        "task": "image_to_editable_psd_plan",
        "source": source,
        "options": asdict(options),
        "recommended_strategy": strategy,
        "client_questions": client_questions(strategy["id"]),
        "recommended_intent_profile": intent_profile,
        "intent_profile_sha256": intent_profile_hash(intent_profile),
        "expected_groups": list(GROUPS_BOTTOM_TO_TOP),
        "stages": [
            *strategy_stages,
            "background_inpainting",
            "recomposition_quality_check",
            "low_confidence_review_packet",
            "staged_stroke_ambiguity_assignment",
            "photoshop_psd_build",
        ],
        "token_policy": {
            "local_first": True,
            "full_image_review_by_default": False,
            "review_payload": "semantic crops first, then at most two local stroke ambiguities",
            "cache_key": (
                "pipeline version + source hash + options hash + intent hash + optional analysis hash"
            ),
        },
        "writes_files": False,
    }


def _recommend_strategy(rgb: Any, preset: str) -> dict[str, Any]:
    cv2, np, _, _, _ = _deps()
    if preset != "auto":
        return {"id": preset, "confidence": 1.0, "reason": "explicit_preset"}
    height, width = rgb.shape[:2]
    border_size = max(2, int(round(min(height, width) * 0.04)))
    border = np.concatenate(
        [
            rgb[:border_size].reshape(-1, 3),
            rgb[-border_size:].reshape(-1, 3),
            rgb[:, :border_size].reshape(-1, 3),
            rgb[:, -border_size:].reshape(-1, 3),
        ]
    )
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    border_gray = cv2.cvtColor(border.reshape(-1, 1, 3), cv2.COLOR_RGB2GRAY).reshape(-1)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    channels = [rgb[:, :, index].astype(np.int16) for index in range(3)]
    redness = channels[0] - channels[1]
    ink = (redness > 34) & (gray < 225)
    border_luma = float(np.median(border_gray))
    border_luma_std = float(np.std(border_gray))
    border_luma_mad = float(np.median(np.abs(border_gray - border_luma)))
    ink_coverage = float(np.mean(ink))
    red_dominance = float(np.percentile(redness, 95) - np.percentile(redness, 50))
    saturation_p90 = float(np.percentile(hsv[:, :, 1], 90))
    dark_coverage = float(np.mean(gray < border_luma - 28.0))
    edge_coverage = float(np.mean(cv2.Canny(gray, 60, 160) > 0))
    uniform_light_border = border_luma >= 205 and border_luma_std <= 24 and border_luma_mad <= 14
    signals = {
        "border_luma": round(border_luma, 3),
        "border_luma_std": round(border_luma_std, 3),
        "border_luma_mad": round(border_luma_mad, 3),
        "ink_coverage": round(ink_coverage, 6),
        "red_dominance": round(red_dominance, 3),
        "saturation_p90": round(saturation_p90, 3),
        "dark_coverage": round(dark_coverage, 6),
        "edge_coverage": round(edge_coverage, 6),
    }
    if (
        border_luma >= 235
        and uniform_light_border
        and saturation_p90 <= 32
        and 0.01 <= dark_coverage <= 0.4
        and edge_coverage >= 0.02
    ):
        confidence = min(
            0.97,
            0.70
            + min(0.12, edge_coverage)
            + min(0.1, dark_coverage * 0.35)
            + min(0.05, (255.0 - saturation_p90) / 5100.0),
        )
        return {
            "id": "monochrome_line_art",
            "confidence": round(confidence, 4),
            "reason": "uniform light border with monochrome high-frequency line structure",
            "signals": signals,
        }
    if (
        uniform_light_border
        and 0.015 <= ink_coverage <= 0.24
        and red_dominance >= 24
        and edge_coverage >= 0.02
    ):
        confidence = min(
            0.97,
            0.62 + min(0.2, red_dominance / 300.0) + min(0.15, ink_coverage),
        )
        return {
            "id": "line_art_on_texture",
            "confidence": round(confidence, 4),
            "reason": "light textured border with sparse red/brown line structure",
            "signals": signals,
        }
    return {
        "id": "poster_basic",
        "confidence": 0.72,
        "reason": "general raster composition",
        "signals": signals,
    }


def _load_rgb(path: Path) -> Any:
    _, np, Image, _, _ = _deps()
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _save_rgb(path: Path, rgb: Any) -> None:
    _, _, Image, _, _ = _deps()
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, "RGB").save(path)


def _save_mask(path: Path, mask: Any) -> None:
    _, _, Image, _, _ = _deps()
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, "L").save(path)


def _save_rgba(path: Path, rgb: Any, alpha: Any) -> None:
    _, np, Image, _, _ = _deps()
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA").save(path)


def _normalise_bbox(
    bbox: list[int] | tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(value) for value in bbox]
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


def _grabcut_candidate(rgb: Any, rect: tuple[int, int, int, int]) -> Any:
    cv2, np, _, _, _ = _deps()
    height, width = rgb.shape[:2]
    x1, y1, x2, y2 = _normalise_bbox(rect, width, height)
    gc_rect = (x1, y1, x2 - x1, y2 - y1)
    mask = np.zeros((height, width), np.uint8)
    bg_model = np.zeros((1, 65), np.float64)
    fg_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        mask,
        gc_rect,
        bg_model,
        fg_model,
        5,
        cv2.GC_INIT_WITH_RECT,
    )
    binary = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    return _keep_relevant_components(binary)


def _keep_relevant_components(mask: Any) -> Any:
    cv2, np, _, _, _ = _deps()
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 2:
        return mask
    height, width = mask.shape
    image_area = height * width
    kept = np.zeros_like(mask)
    ranked: list[tuple[float, int]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        cx, cy = centroids[label]
        center_distance = math.hypot((cx / width) - 0.5, (cy / height) - 0.5)
        score = (area / image_area) * 4.0 + max(0.0, 0.8 - center_distance)
        ranked.append((score, label))
    ranked.sort(reverse=True)
    largest_area = int(stats[ranked[0][1], cv2.CC_STAT_AREA])
    for _, label in ranked:
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= max(64, int(largest_area * 0.025)):
            kept[labels == label] = 255
    return kept


def _score_subject_mask(rgb: Any, mask: Any) -> dict[str, float]:
    cv2, np, _, _, _ = _deps()
    height, width = mask.shape
    binary = mask > 0
    coverage = float(np.mean(binary))
    center = binary[int(height * 0.25) : int(height * 0.75), int(width * 0.25) : int(width * 0.75)]
    center_overlap = float(np.mean(center)) if center.size else 0.0
    border = np.concatenate([binary[0], binary[-1], binary[:, 0], binary[:, -1]])
    border_touch = float(np.mean(border))
    boundary = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    edges = cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 70, 150) > 0
    expanded_edges = cv2.dilate(edges.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    edge_alignment = float(np.mean(expanded_edges[boundary])) if np.any(boundary) else 0.0
    coverage_score = max(0.0, 1.0 - abs(coverage - 0.42) / 0.58)
    score = (
        0.30 * edge_alignment
        + 0.25 * center_overlap
        + 0.25 * coverage_score
        + 0.20 * (1.0 - border_touch)
    )
    if coverage < 0.015 or coverage > 0.92:
        score *= 0.25
    return {
        "score": round(float(score), 6),
        "coverage": round(coverage, 6),
        "center_overlap": round(center_overlap, 6),
        "border_touch": round(border_touch, 6),
        "edge_alignment": round(edge_alignment, 6),
    }


def _subject_mask(
    rgb: Any, analysis: dict[str, Any], max_refinements: int
) -> tuple[Any, dict[str, Any]]:
    _, np, Image, _, _ = _deps()
    height, width = rgb.shape[:2]
    supplied_mask = analysis.get("subject_mask_path")
    if supplied_mask:
        with Image.open(Path(str(supplied_mask))) as image:
            alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
        if alpha.shape != (height, width):
            raise ValueError("Provided subject mask/cutout must match the input canvas size")
        binary = np.where(alpha >= 24, 255, 0).astype(np.uint8)
        metrics = _score_subject_mask(rgb, binary)
        return binary, {
            "engine": "provided_or_photoshop",
            "selected_candidate": 1,
            "candidates": [{"candidate": 1, "source": "subject_mask_path", **metrics}],
            "confidence": round(min(0.98, 0.72 + metrics["score"] * 0.25), 4),
        }

    boxes = analysis.get("subject_boxes") or []
    if boxes:
        candidates = [
            _normalise_bbox(item["bbox"] if isinstance(item, dict) else item, width, height)
            for item in boxes
        ]
    else:
        ratios = [
            (0.035, 0.035, 0.965, 0.965),
            (0.075, 0.055, 0.925, 0.94),
            (0.12, 0.08, 0.88, 0.91),
        ]
        candidates = [
            (int(width * x1), int(height * y1), int(width * x2), int(height * y2))
            for x1, y1, x2, y2 in ratios[: max(1, min(max_refinements, 3))]
        ]
    attempts: list[dict[str, Any]] = []
    masks: list[Any] = []
    for index, rect in enumerate(candidates, start=1):
        mask = _grabcut_candidate(rgb, rect)
        masks.append(mask)
        attempts.append({"candidate": index, "rect": list(rect), **_score_subject_mask(rgb, mask)})
    selected_index = max(range(len(attempts)), key=lambda index: attempts[index]["score"])
    selected = masks[selected_index]
    confidence = max(0.2, min(0.88, 0.35 + attempts[selected_index]["score"] * 0.7))
    return selected, {
        "engine": "offline_iterative_grabcut",
        "selected_candidate": selected_index + 1,
        "candidates": attempts,
        "confidence": round(confidence, 4),
    }


def _mask_bbox(mask: Any) -> list[int] | None:
    _, np, _, _, _ = _deps()
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _detect_central_circle(
    binary: Any, main_bbox: list[int]
) -> tuple[tuple[int, int, int] | None, dict[str, Any]]:
    cv2, np, _, _, _ = _deps()
    x1, y1, x2, y2 = main_bbox
    bbox_width = x2 - x1
    bbox_height = y2 - y1
    scale = min(bbox_width, bbox_height)
    composition_x = (x1 + x2) / 2.0
    composition_y = (y1 + y2) / 2.0
    search_span = max(12, int(round(scale * 0.075)))
    step = max(3, int(round(scale / 120.0)))
    radius_min = max(12, int(round(scale * 0.05)))
    radius_max = max(radius_min + 3, int(round(scale * 0.115)))
    radius_step = max(2, int(round(scale / 180.0)))
    radius_prior = scale * 0.082
    dilation = max(3, int(round(scale * 0.004)))
    if dilation % 2 == 0:
        dilation += 1
    expanded = cv2.dilate(binary, np.ones((dilation, dilation), np.uint8)) > 0
    angles = np.linspace(0.0, math.tau, 240, endpoint=False)
    cosines = np.cos(angles)
    sines = np.sin(angles)
    height, width = binary.shape
    best: tuple[float, float, int, int, int] | None = None
    for center_y in range(
        int(round(composition_y)) - search_span,
        int(round(composition_y)) + search_span + 1,
        step,
    ):
        for center_x in range(
            int(round(composition_x)) - search_span,
            int(round(composition_x)) + search_span + 1,
            step,
        ):
            center_distance = math.hypot(center_x - composition_x, center_y - composition_y) / max(
                search_span, 1
            )
            for radius in range(radius_min, radius_max + 1, radius_step):
                sample_x = np.clip(
                    np.rint(center_x + radius * cosines).astype(np.int32), 0, width - 1
                )
                sample_y = np.clip(
                    np.rint(center_y + radius * sines).astype(np.int32), 0, height - 1
                )
                boundary_support = float(np.mean(expanded[sample_y, sample_x]))
                radius_deviation = abs(radius - radius_prior) / max(radius_prior, 1.0)
                score = boundary_support - 0.055 * center_distance - 0.15 * radius_deviation
                candidate = (score, boundary_support, center_x, center_y, radius)
                if best is None or candidate > best:
                    best = candidate
    if best is None or best[1] < 0.42:
        return None, {
            "detected": False,
            "boundary_support": round(float(best[1]), 6) if best else 0.0,
            "reason": "no_centered_circle_with_sufficient_boundary_support",
        }
    score, boundary_support, center_x, center_y, radius = best
    offset_ratio = math.hypot(center_x - composition_x, center_y - composition_y) / max(scale, 1)
    confidence = min(
        0.96,
        max(0.5, 0.52 + boundary_support * 0.38 - offset_ratio * 0.35),
    )
    return (center_x, center_y, radius), {
        "detected": True,
        "method": "center_constrained_circular_boundary_search",
        "boundary_support": round(boundary_support, 6),
        "score": round(score, 6),
        "composition_center": [round(composition_x, 2), round(composition_y, 2)],
        "detected_center": [center_x, center_y],
        "detected_radius": radius,
        "center_offset_ratio": round(offset_ratio, 6),
        "confidence": round(confidence, 4),
    }


def _position_label(angle_degrees: float) -> str:
    labels = ("右侧", "右下", "下方", "左下", "左侧", "左上", "上方", "右上")
    index = int(round((angle_degrees % 360.0) / 45.0)) % len(labels)
    return labels[index]


def _warped_angular_assignments(
    main_alpha: Any,
    xs: Any,
    ys: Any,
    angles: Any,
    main_bbox: list[int],
    center: tuple[int, int],
    region_count: int,
    phase: float,
    sector_width: float,
) -> tuple[Any, dict[str, Any]]:
    cv2, np, _, _, _ = _deps()
    center_x, center_y = center
    bbox_width = main_bbox[2] - main_bbox[0]
    bbox_height = main_bbox[3] - main_bbox[1]
    scale = min(bbox_width, bbox_height)
    inner_radius = max(8, int(round(scale * 0.07)))
    corners = (
        (main_bbox[0], main_bbox[1]),
        (main_bbox[2], main_bbox[1]),
        (main_bbox[2], main_bbox[3]),
        (main_bbox[0], main_bbox[3]),
    )
    maximum_radius = max(
        inner_radius + 2,
        int(math.ceil(max(math.hypot(x - center_x, y - center_y) for x, y in corners))),
    )
    radial_step = max(1, int(round(scale / 500.0)))
    radii = np.arange(inner_radius, maximum_radius + 1, radial_step, dtype=np.float64)
    half_width = max(3, min(12, int(round(sector_width * 0.22))))
    offsets = np.arange(-half_width, half_width + 1, dtype=np.float64)
    density_kernel = max(5, int(round(scale * 0.008)))
    if density_kernel % 2 == 0:
        density_kernel += 1
    density = cv2.GaussianBlur(
        (main_alpha > 0).astype(np.float32),
        (density_kernel, density_kernel),
        0,
    )
    height, width = main_alpha.shape
    transition_penalty = 0.022 * np.abs(offsets[:, None] - offsets[None, :])
    offset_curves: list[Any] = []
    straight_densities: list[float] = []
    warped_densities: list[float] = []
    for boundary_index in range(region_count):
        base_angle = phase + boundary_index * sector_width
        sample_angles = np.radians(base_angle + offsets[None, :])
        sample_x = np.clip(
            np.rint(center_x + radii[:, None] * np.cos(sample_angles)).astype(np.int32),
            0,
            width - 1,
        )
        sample_y = np.clip(
            np.rint(center_y + radii[:, None] * np.sin(sample_angles)).astype(np.int32),
            0,
            height - 1,
        )
        samples = density[sample_y, sample_x]
        anchor_penalty = 0.0012 * np.square(offsets)
        costs = samples[0] + 0.008 * np.abs(offsets)
        backtrack = np.zeros((len(radii), len(offsets)), dtype=np.int16)
        for radius_index in range(1, len(radii)):
            transitions = costs[:, None] + transition_penalty
            previous = np.argmin(transitions, axis=0)
            costs = (
                samples[radius_index]
                + anchor_penalty
                + transitions[previous, np.arange(len(offsets))]
            )
            backtrack[radius_index] = previous
        state = int(np.argmin(costs))
        path = np.zeros(len(radii), dtype=np.float64)
        path[-1] = offsets[state]
        for radius_index in range(len(radii) - 1, 0, -1):
            state = int(backtrack[radius_index, state])
            path[radius_index - 1] = offsets[state]
        zero_index = int(np.where(offsets == 0)[0][0])
        straight_density = float(np.mean(samples[:, zero_index]))
        warped_density = float(
            np.mean(samples[np.arange(len(radii)), (path + half_width).astype(np.int32)])
        )
        if warped_density > straight_density:
            path[:] = 0.0
            warped_density = straight_density
        all_radii = np.arange(maximum_radius + 1, dtype=np.float64)
        curve = np.interp(all_radii, radii, path, left=path[0], right=path[-1])
        offset_curves.append(curve)
        straight_densities.append(straight_density)
        warped_densities.append(warped_density)

    point_radii = np.clip(
        np.rint(np.hypot(xs - center_x, ys - center_y)).astype(np.int32),
        0,
        maximum_radius,
    )
    curves = np.stack(offset_curves)
    boundary_zero = curves[0, point_radii]
    relative_angles = ((angles - phase) % 360.0 - boundary_zero) % 360.0
    assignments = np.zeros(len(xs), dtype=np.int32)
    for boundary_index in range(1, region_count):
        threshold = (
            boundary_index * sector_width + curves[boundary_index, point_radii] - boundary_zero
        )
        assignments += relative_angles >= threshold
    straight_mean = float(np.mean(straight_densities))
    warped_mean = float(np.mean(warped_densities))
    reduction = max(0.0, (straight_mean - warped_mean) / max(straight_mean, 1e-6))
    return assignments, {
        "warped_boundaries": True,
        "boundary_method": "radial_dynamic_programming_low_ink_seam_v1",
        "boundary_half_width_degrees": half_width,
        "straight_boundary_density": round(straight_mean, 6),
        "warped_boundary_density": round(warped_mean, 6),
        "boundary_density_reduction": round(reduction, 6),
        "maximum_boundary_deviation_degrees": round(float(np.max(np.abs(curves))), 4),
    }


def _preserve_stroke_continuity(
    main_alpha: Any,
    continuity_core: Any,
    xs: Any,
    ys: Any,
    assignments: Any,
    region_count: int,
    scale: int,
) -> tuple[Any, dict[str, Any]]:
    cv2, np, _, _, _ = _deps()
    label_map = np.full(main_alpha.shape, -1, dtype=np.int16)
    label_map[ys, xs] = assignments
    core = ((continuity_core > 0) & (label_map >= 0)).astype(np.uint8)
    core_pixels = int(np.count_nonzero(core))
    if core_pixels < 64:
        return assignments, {
            "enabled": False,
            "reason": "insufficient_high_confidence_stroke_core",
        }
    component_count, component_labels, stats, _ = cv2.connectedComponentsWithStats(core, 8)
    maximum_component_area = max(256, int(round(core_pixels * 0.10)))
    maximum_extent = max(24, int(round(scale * 0.43)))
    candidates: list[tuple[float, int, int, int]] = []
    ambiguous_records: list[dict[str, Any]] = []
    split_before = 0
    unresolved_large = 0
    unresolved_ambiguous = 0
    for component_id in range(1, component_count):
        component = component_labels == component_id
        values = label_map[component]
        region_ids, counts = np.unique(values[values >= 0], return_counts=True)
        if len(region_ids) <= 1:
            continue
        split_before += 1
        area = int(stats[component_id, cv2.CC_STAT_AREA])
        extent = max(
            int(stats[component_id, cv2.CC_STAT_WIDTH]),
            int(stats[component_id, cv2.CC_STAT_HEIGHT]),
        )
        dominant_index = int(np.argmax(counts))
        dominance = float(counts[dominant_index] / max(np.sum(counts), 1))
        dominant_region = int(region_ids[dominant_index])
        if area > maximum_component_area or extent > maximum_extent:
            unresolved_large += 1
            continue
        if dominance < 0.72:
            unresolved_ambiguous += 1
            ambiguous_records.append(
                {
                    "component_id": component_id,
                    "area": area,
                    "dominance": dominance,
                    "region_ids": [int(value) for value in region_ids],
                    "region_counts": [int(value) for value in counts],
                }
            )
            continue
        candidates.append((dominance, area, component_id, dominant_region))

    updated = label_map.copy()
    original = label_map.copy()
    for _, _, component_id, dominant_region in candidates:
        updated[component_labels == component_id] = dominant_region

    dilation = max(3, int(round(scale * 0.006)))
    if dilation % 2 == 0:
        dilation += 1
    kernel = np.ones((dilation, dilation), np.uint8)
    claimed = np.zeros(main_alpha.shape, dtype=np.float32)
    for dominance, _, component_id, dominant_region in sorted(candidates, reverse=True):
        component = (component_labels == component_id).astype(np.uint8)
        influence = cv2.dilate(component, kernel) > 0
        influence &= label_map >= 0
        influence &= core == 0
        take = influence & (dominance > claimed)
        updated[take] = dominant_region
        claimed[take] = dominance

    split_after = 0
    for component_id in range(1, component_count):
        values = updated[component_labels == component_id]
        if len(np.unique(values[values >= 0])) > 1:
            split_after += 1
    changed_pixels = int(np.count_nonzero((updated != original) & (original >= 0)))
    support_pixels = int(np.count_nonzero(original >= 0))
    split_reduction = max(0.0, (split_before - split_after) / split_before) if split_before else 0.0
    corrected = updated[ys, xs].astype(np.int32)
    masses = np.bincount(corrected, minlength=region_count)
    ambiguity_components: list[dict[str, Any]] = []
    ranked_ambiguities = sorted(
        ambiguous_records,
        key=lambda item: (item["area"] * (1.0 - item["dominance"]), item["area"]),
        reverse=True,
    )
    for index, record in enumerate(ranked_ambiguities[:6], start=1):
        component = (component_labels == int(record["component_id"])).astype(np.uint8)
        influence = cv2.dilate(component, kernel) > 0
        influence &= label_map >= 0
        mask = np.where(influence, 255, 0).astype(np.uint8)
        total = max(sum(record["region_counts"]), 1)
        ambiguity_components.append(
            {
                "component_id": f"stroke_ambiguity_{index:02d}",
                "mask": mask,
                "bbox": _mask_bbox(mask),
                "impact_score": round(float(record["area"] * (1.0 - record["dominance"])), 4),
                "core_area": int(record["area"]),
                "candidate_raw_regions": [
                    {
                        "raw_region_index": region_id,
                        "core_pixel_count": count,
                        "share": round(count / total, 6),
                    }
                    for region_id, count in zip(
                        record["region_ids"], record["region_counts"], strict=True
                    )
                ],
            }
        )
    return corrected, {
        "enabled": True,
        "method": "dominant_high_confidence_connected_stroke_recovery_v1",
        "core_threshold": 112,
        "core_pixel_count": core_pixels,
        "connected_component_count": component_count - 1,
        "split_component_count_before": split_before,
        "eligible_component_count": len(candidates),
        "split_component_count_after": split_after,
        "split_component_reduction": round(split_reduction, 6),
        "changed_foreground_pixels": changed_pixels,
        "changed_foreground_ratio": round(changed_pixels / max(support_pixels, 1), 6),
        "unresolved_large_component_count": unresolved_large,
        "unresolved_ambiguous_component_count": unresolved_ambiguous,
        "reviewable_ambiguity_count": len(ambiguity_components),
        "region_pixel_counts": [int(value) for value in masses],
        "ambiguity_components_runtime": ambiguity_components,
    }


def _angular_region_components(
    main_alpha: Any,
    main_bbox: list[int],
    center: tuple[int, int],
    continuity_core: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, np, _, _, _ = _deps()
    ys, xs = np.where(main_alpha > 0)
    if len(xs) < 256:
        return [], {"activated": False, "reason": "insufficient_ink_pixels"}
    bbox_width = main_bbox[2] - main_bbox[0]
    bbox_height = main_bbox[3] - main_bbox[1]
    aspect_ratio = bbox_width / max(bbox_height, 1)
    if not 0.72 <= aspect_ratio <= 1.38:
        return [], {"activated": False, "reason": "composition_is_not_near_circular"}

    center_x, center_y = center
    angles = (np.degrees(np.arctan2(ys - center_y, xs - center_x)) + 360.0) % 360.0
    histogram = np.bincount(np.floor(angles).astype(np.int32), minlength=360).astype(np.float64)
    kernel_radius = 8
    kernel_axis = np.arange(-kernel_radius, kernel_radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * np.square(kernel_axis / 3.0))
    kernel /= np.sum(kernel)
    extended = np.concatenate([histogram[-kernel_radius:], histogram, histogram[:kernel_radius]])
    smoothed = np.convolve(extended, kernel, mode="same")[kernel_radius:-kernel_radius]
    mean_density = max(float(np.mean(smoothed)), 1e-6)
    best: tuple[float, int, float, float, float, Any] | None = None
    for region_count in range(6, 11):
        sector_width = 360.0 / region_count
        for phase in np.arange(0.0, sector_width, 1.0):
            assignments = np.floor(((angles - phase) % 360.0) / sector_width).astype(np.int32)
            masses = np.bincount(assignments, minlength=region_count).astype(np.float64)
            if np.any(masses <= 0):
                continue
            boundary_indices = (
                np.rint(
                    (phase + np.arange(region_count, dtype=np.float64) * sector_width) % 360.0
                ).astype(np.int32)
                % 360
            )
            boundary_density_ratio = float(np.mean(smoothed[boundary_indices]) / mean_density)
            balance_cv = float(np.std(masses) / max(np.mean(masses), 1.0))
            score = boundary_density_ratio + 0.18 * balance_cv + 0.03 * abs(region_count - 8)
            candidate = (
                score,
                region_count,
                float(phase),
                boundary_density_ratio,
                balance_cv,
                assignments,
            )
            if best is None or candidate[:5] < best[:5]:
                best = candidate
    if best is None:
        return [], {"activated": False, "reason": "no_balanced_angular_partition"}

    score, region_count, phase, boundary_density_ratio, balance_cv, _ = best
    sector_width = 360.0 / region_count
    assignments, seam_info = _warped_angular_assignments(
        main_alpha,
        xs,
        ys,
        angles,
        main_bbox,
        center,
        region_count,
        phase,
        sector_width,
    )
    assignments, continuity_info = _preserve_stroke_continuity(
        main_alpha,
        continuity_core,
        xs,
        ys,
        assignments,
        region_count,
        min(bbox_width, bbox_height),
    )
    masses = np.bincount(assignments, minlength=region_count).astype(np.float64)
    balance_cv = float(np.std(masses) / max(np.mean(masses), 1.0))
    regions: list[dict[str, Any]] = []
    for raw_index in range(region_count):
        mask = np.zeros_like(main_alpha)
        selected = assignments == raw_index
        mask[ys[selected], xs[selected]] = 255
        center_angle = (phase + (raw_index + 0.5) * sector_width) % 360.0
        regions.append(
            {
                "raw_index": raw_index,
                "alpha": mask,
                "bbox": _mask_bbox(mask),
                "center_angle": center_angle,
                "position_label": _position_label(center_angle),
                "pixel_count": int(np.count_nonzero(mask)),
            }
        )
    regions.sort(key=lambda item: (float(item["center_angle"]) + 90.0) % 360.0)
    confidence = max(
        0.45,
        min(
            0.9,
            0.84
            - 0.16 * boundary_density_ratio
            - 0.08 * balance_cv
            + 0.12 * float(seam_info["boundary_density_reduction"])
            + 0.08 * float(continuity_info.get("split_component_reduction", 0.0)),
        ),
    )
    for index, region in enumerate(regions, start=1):
        region.update(
            {
                "id": f"ring_region_{index:02d}",
                "name": f"环形纹样_{index:02d}_{region['position_label']}_候选区域",
                "group": "02_主体",
                "confidence": round(confidence, 4),
                "kind": "angular_region_candidate",
                "semantic_status": "region_candidate_unreviewed",
            }
        )
    raw_region_ids = {int(region["raw_index"]): str(region["id"]) for region in regions}
    for ambiguity in continuity_info.get("ambiguity_components_runtime", []):
        ambiguity["candidate_regions"] = [
            {
                "region_id": raw_region_ids[int(candidate.pop("raw_region_index"))],
                **candidate,
            }
            for candidate in ambiguity.pop("candidate_raw_regions")
        ]
    for region in regions:
        region.pop("raw_index", None)
    return regions, {
        "activated": True,
        "method": "adaptive_warped_stroke_continuity_partition_v3",
        "region_count": region_count,
        "center": [center_x, center_y],
        "phase_degrees": round(phase, 4),
        "sector_width_degrees": round(sector_width, 4),
        "boundary_density_ratio": round(boundary_density_ratio, 6),
        "mass_balance_cv": round(balance_cv, 6),
        "selection_score": round(score, 6),
        "mutually_exclusive": True,
        "coverage_ratio": 1.0,
        "semantic_labels_confirmed": False,
        "confidence": round(confidence, 4),
        **seam_info,
        "stroke_continuity": continuity_info,
    }


def _line_art_masks(
    rgb: Any,
    *,
    strategy_id: str = "line_art_on_texture",
    allow_semantic_subdivision: bool = True,
    separate_salient_decorations: bool = True,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    cv2, np, _, _, _ = _deps()
    height, width = rgb.shape[:2]
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    redness = r - g

    # A continuous alpha retains anti-aliased strokes; the binary mask drives repair and QA.
    if strategy_id == "monochrome_line_art":
        border_size = max(2, int(round(min(height, width) * 0.04)))
        border_gray = np.concatenate(
            [
                gray[:border_size].reshape(-1),
                gray[-border_size:].reshape(-1),
                gray[:, :border_size].reshape(-1),
                gray[:, -border_size:].reshape(-1),
            ]
        )
        background_luma = float(np.median(border_gray))
        alpha = np.clip(
            (background_luma - gray.astype(np.float32) - 8.0) * 4.5,
            0,
            255,
        )
        alpha = np.where(gray < background_luma - 12.0, alpha, 0)
        broad_binary = np.where(gray < background_luma - 18.0, 255, 0).astype(np.uint8)
    else:
        # Red/brown ink is separated from warm paper by both redness and luminance.
        alpha_red = np.clip((redness.astype(np.float32) - 18.0) * 5.5, 0, 255)
        alpha_dark = np.clip((238.0 - gray.astype(np.float32)) * 3.2, 0, 255)
        alpha = np.minimum(alpha_red, alpha_dark)
        alpha = np.where((redness > 18) & (gray < 238), alpha, 0)
        broad_binary = np.where((redness > 18) & (gray < 238), 255, 0).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha.astype(np.uint8), (3, 3), 0)
    binary = np.where(alpha >= 28, 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # Find a compact lower-right seal without assuming a fixed pixel coordinate.
    seal_region = np.zeros_like(binary)
    count, _, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    seal_candidates: list[tuple[float, int]] = []
    image_area = width * height
    for label in range(1, count):
        x, y, w, h, area = [int(value) for value in stats[label]]
        cx, cy = centroids[label]
        if cx < width * 0.62 or cy < height * 0.62:
            continue
        if area < max(80, image_area * 0.00015):
            continue
        if w > width * 0.22 or h > height * 0.22:
            continue
        compactness = area / max(w * h, 1)
        lower_right = (cx / width) + (cy / height)
        seal_candidates.append((lower_right + compactness * 0.5, label))
    seal_bbox: list[int] | None = None
    seal_label: int | None = None
    if seal_candidates:
        _, label = max(seal_candidates)
        seal_label = label
        x, y, w, h, _ = [int(value) for value in stats[label]]
        pad = max(5, int(round(max(w, h) * 0.08)))
        x1, y1, x2, y2 = _normalise_bbox(
            (x - pad, y - pad, x + w + pad, y + h + pad), width, height
        )
        seal_region[y1:y2, x1:x2] = broad_binary[y1:y2, x1:x2]
        seal_bbox = [x1, y1, x2, y2]
    if strategy_id == "monochrome_line_art":
        seal_region[:] = 0
        seal_bbox = None
        seal_label = None

    # Paper grain can share the ink hue. Restrict the broad alpha candidate to the
    # bounding envelope of substantial central components, plus the detected seal.
    main_boxes: list[tuple[int, int, int, int]] = []
    minimum_component_area = max(120, int(round(image_area * 0.00012)))
    for label in range(1, count):
        if label == seal_label:
            continue
        x, y, w, h, area = [int(value) for value in stats[label]]
        cx, cy = centroids[label]
        if area < minimum_component_area:
            continue
        if not (width * 0.06 <= cx <= width * 0.94 and height * 0.12 <= cy <= height * 0.84):
            continue
        main_boxes.append((x, y, x + w, y + h))
    main_bbox: list[int] | None = None
    support = np.zeros_like(broad_binary)
    if main_boxes:
        pad_x = max(6, int(round(width * 0.025)))
        pad_y = max(6, int(round(height * 0.02)))
        x1 = min(item[0] for item in main_boxes) - pad_x
        y1 = min(item[1] for item in main_boxes) - pad_y
        x2 = max(item[2] for item in main_boxes) + pad_x
        y2 = max(item[3] for item in main_boxes) + pad_y
        x1, y1, x2, y2 = _normalise_bbox((x1, y1, x2, y2), width, height)
        support[y1:y2, x1:x2] = 255
        main_bbox = [x1, y1, x2, y2]
    else:
        support[:] = 255
    if seal_bbox:
        x1, y1, x2, y2 = seal_bbox
        support[y1:y2, x1:x2] = 255
    broad_binary = cv2.bitwise_and(broad_binary, support)

    # A central ornament must be both near the composition center and supported by a
    # circular ink boundary. Density alone tends to mislabel a detailed animal head.
    central_region = np.zeros_like(binary)
    central_bbox: list[int] | None = None
    central_circle: tuple[int, int, int] | None = None
    central_circle_info: dict[str, Any] = {
        "detected": False,
        "reason": "main_composition_bbox_unavailable",
    }
    if main_bbox:
        central_circle, central_circle_info = _detect_central_circle(binary, main_bbox)
    if central_circle:
        center_x, center_y, radius = central_circle
        pad = max(2, int(round(radius * 0.04)))
        circle = np.zeros_like(binary)
        cv2.circle(circle, (center_x, center_y), radius + pad, 255, -1)
        central_region = cv2.bitwise_and(broad_binary, circle)
        central_region[seal_region > 0] = 0
        central_bbox = _mask_bbox(central_region)

    if not separate_salient_decorations:
        seal_region[:] = 0
        central_region[:] = 0
        seal_bbox = None
        central_bbox = None
    seal_alpha = np.where(seal_region > 0, 255, 0).astype(np.uint8)
    central_alpha = np.where(central_region > 0, 255, 0).astype(np.uint8)
    main_alpha = broad_binary.copy()
    main_alpha[seal_region > 0] = 0
    main_alpha[central_region > 0] = 0
    continuity_core = np.where(alpha >= 112, 255, 0).astype(np.uint8)
    continuity_core[seal_region > 0] = 0
    continuity_core[central_region > 0] = 0
    composition_center = (
        (
            int(round((main_bbox[0] + main_bbox[2]) / 2)),
            int(round((main_bbox[1] + main_bbox[3]) / 2)),
        )
        if main_bbox
        else (width // 2, height // 2)
    )
    if central_circle:
        composition_center = (central_circle[0], central_circle[1])
    ring_regions: list[dict[str, Any]] = []
    subdivision_info: dict[str, Any] = {
        "activated": False,
        "reason": "main_composition_bbox_unavailable",
    }
    if not allow_semantic_subdivision:
        subdivision_info = {
            "activated": False,
            "reason": "intent_requests_whole_subject",
        }
    elif main_bbox and central_circle:
        ring_regions, subdivision_info = _angular_region_components(
            main_alpha,
            main_bbox,
            composition_center,
            continuity_core,
        )
    primary_layer_name = "主体线稿_整体_可调色"
    primary_bbox = _mask_bbox(main_alpha)
    if len(ring_regions) > 1:
        primary = ring_regions[0]
        main_alpha = primary["alpha"]
        primary_layer_name = primary["name"]
        primary_bbox = primary["bbox"]
    union = broad_binary
    separability = float(np.mean(alpha[union > 0]) / 255.0) if np.any(union) else 0.0
    confidence = min(0.96, 0.74 + separability * 0.22)
    extras: list[dict[str, Any]] = []
    if len(ring_regions) > 1:
        extras.extend(ring_regions[1:])
    if np.any(central_alpha):
        extras.append(
            {
                "id": "central_ornament",
                "name": "中央绣球_独立可移动",
                "group": "02_主体",
                "alpha": central_alpha,
                "bbox": central_bbox,
                "confidence": central_circle_info["confidence"],
                "kind": "central_ornament",
                "semantic_status": "geometry_confirmed",
            }
        )
    if np.any(seal_alpha):
        extras.append(
            {
                "id": "seal",
                "name": "右下印章_独立可移动",
                "group": "03_装饰",
                "alpha": seal_alpha,
                "bbox": seal_bbox,
                "confidence": 0.9,
                "kind": "seal",
                "semantic_status": "geometry_confirmed",
            }
        )
    return (
        main_alpha,
        extras,
        {
            "engine": "local_monochrome_line_art"
            if strategy_id == "monochrome_line_art"
            else "local_color_line_art",
            "selected_candidate": 1,
            "candidates": [
                {
                    "candidate": 1,
                    "score": round(confidence, 6),
                    "coverage": round(float(np.mean(union > 0)), 6),
                    "central_circle": central_circle_info,
                    "seal_detected": bool(seal_bbox),
                    "main_bbox": main_bbox,
                }
            ],
            "confidence": round(confidence, 4),
            "strategy": strategy_id,
            "primary_layer_name": primary_layer_name,
            "primary_bbox": primary_bbox,
            "semantic_subdivision": subdivision_info,
            "union_mask": union,
        },
    )


def _detect_text_regions(
    rgb: Any, subject_mask: Any, analysis: dict[str, Any], mode: str
) -> tuple[Any, list[dict[str, Any]]]:
    cv2, np, _, _, _ = _deps()
    height, width = rgb.shape[:2]
    provided = analysis.get("text_regions")
    regions: list[dict[str, Any]] = []
    if provided is not None:
        for index, item in enumerate(provided, start=1):
            bbox = _normalise_bbox(item["bbox"], width, height)
            regions.append(
                {
                    "id": str(item.get("id") or f"text_{index:02d}"),
                    "bbox": list(bbox),
                    "content": str(item.get("content") or ""),
                    "confidence": float(
                        item.get("confidence", 0.95 if item.get("content") else 0.6)
                    ),
                    "font_candidates": list(item.get("font_candidates") or []),
                    "font_size": int(item.get("font_size") or max(12, bbox[3] - bbox[1])),
                    "color": str(item.get("color") or "#FFFFFF"),
                    "source": "analysis_override",
                }
            )
    elif mode != "off":
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        _, threshold = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        threshold[subject_mask > 0] = 0
        kernel_width = max(9, width // 45)
        connected = cv2.morphologyEx(
            threshold,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 3)),
            iterations=2,
        )
        count, _, stats, _ = cv2.connectedComponentsWithStats(connected, 8)
        candidates: list[tuple[int, int, int, int, float]] = []
        for label in range(1, count):
            x, y, w, h, area = [int(value) for value in stats[label]]
            if w < width * 0.06 or h < max(5, height * 0.008):
                continue
            if h > height * 0.16 or w / max(h, 1) < 1.35:
                continue
            bbox_area = w * h
            density = area / max(bbox_area, 1)
            if not 0.08 <= density <= 0.78:
                continue
            band_bonus = 0.12 if y < height * 0.32 or y + h > height * 0.72 else 0.0
            confidence = min(0.72, 0.34 + density * 0.45 + band_bonus)
            candidates.append((x, y, x + w, y + h, confidence))
        candidates.sort(key=lambda item: item[4], reverse=True)
        for index, (x1, y1, x2, y2, confidence) in enumerate(candidates[:8], start=1):
            regions.append(
                {
                    "id": f"text_{index:02d}",
                    "bbox": [x1, y1, x2, y2],
                    "content": "",
                    "confidence": round(confidence, 4),
                    "font_candidates": [],
                    "font_size": max(12, y2 - y1),
                    "color": "#FFFFFF",
                    "source": "local_conservative_detector",
                }
            )

    mask = np.zeros((height, width), dtype=np.uint8)
    for region in regions:
        x1, y1, x2, y2 = region["bbox"]
        pad_x = max(2, int((x2 - x1) * 0.025))
        pad_y = max(2, int((y2 - y1) * 0.08))
        x1, y1, x2, y2 = _normalise_bbox(
            (x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), width, height
        )
        mask[y1:y2, x1:x2] = 255
    mask[subject_mask > 0] = 0
    return mask, regions


def _inpaint_background(rgb: Any, repair_mask: Any, *, radius: int | None = None) -> Any:
    cv2, np, _, _, _ = _deps()
    if not np.any(repair_mask):
        return rgb.copy()
    radius = radius or max(3, min(15, int(round(min(rgb.shape[:2]) * 0.008))))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    repaired = cv2.inpaint(bgr, repair_mask, radius, cv2.INPAINT_TELEA)
    return cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB)


def _unmix_line_art(
    rgb: Any,
    background: Any,
    ink_region: Any,
    *,
    strategy_id: str,
) -> tuple[Any, Any, dict[str, Any]]:
    cv2, np, _, _, _ = _deps()
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    redness = rgb[:, :, 0].astype(np.int16) - rgb[:, :, 1].astype(np.int16)
    if strategy_id == "monochrome_line_art":
        strong = (gray < 72) & (ink_region > 0)
        if int(np.count_nonzero(strong)) < 64:
            strong = (gray < 120) & (ink_region > 0)
        fallback_color = np.array([18.0, 18.0, 18.0], dtype=np.float32)
    else:
        strong = (redness > 50) & (gray < 120) & (ink_region > 0)
        if int(np.count_nonzero(strong)) < 64:
            strong = (redness > 42) & (gray < 150) & (ink_region > 0)
        fallback_color = np.array([166.0, 82.0, 58.0], dtype=np.float32)
    if int(np.count_nonzero(strong)) < 16:
        ink_color = fallback_color
    else:
        ink_color = np.median(rgb[strong], axis=0).astype(np.float32)
    observed = rgb.astype(np.float32)
    base = background.astype(np.float32)
    direction = base - ink_color[None, None, :]
    delta = base - observed
    alpha = np.sum(delta * direction, axis=2) / (np.sum(direction * direction, axis=2) + 1e-6)
    alpha = np.clip(alpha, 0.0, 1.0)
    alpha[ink_region == 0] = 0.0
    alpha[alpha < 0.025] = 0.0
    layer_rgb = np.empty_like(rgb)
    layer_rgb[:, :] = np.clip(ink_color, 0, 255).astype(np.uint8)
    return (
        layer_rgb,
        np.round(alpha * 255.0).astype(np.uint8),
        {
            "ink_color_rgb": [int(round(value)) for value in ink_color],
            "alpha_coverage": round(float(np.mean(alpha > 0)), 6),
            "method": "foreground_background_alpha_unmix",
        },
    )


def _composite(background: Any, layers: list[tuple[Any, Any]]) -> Any:
    _, np, _, _, _ = _deps()
    result = background.astype(np.float32)
    for rgb, alpha in layers:
        a = (alpha.astype(np.float32) / 255.0)[:, :, None]
        result = rgb.astype(np.float32) * a + result * (1.0 - a)
    return np.clip(result, 0, 255).astype(np.uint8)


def _quality(
    original: Any, recomposed: Any, subject_mask: Any, text_mask: Any, subject_info: dict[str, Any]
) -> dict[str, Any]:
    _, np, _, _, _ = _deps()
    diff = np.abs(original.astype(np.float32) - recomposed.astype(np.float32))
    mae = float(np.mean(diff))
    mse = float(np.mean(np.square(diff)))
    psnr = 99.0 if mse == 0 else 20.0 * math.log10(255.0 / math.sqrt(mse))
    similarity = max(0.0, 1.0 - mae / 255.0)
    subject_coverage = float(np.mean(subject_mask > 0))
    text_coverage = float(np.mean(text_mask > 0))
    reasons: list[str] = []
    if subject_info["confidence"] < 0.7:
        reasons.append("主体遮罩由本地启发式生成，建议检查边缘和漏选区域。")
    if subject_coverage < 0.02:
        reasons.append("主体覆盖率过低，可能未识别主视觉。")
    if subject_coverage > 0.8:
        reasons.append("主体覆盖率较高，可能把部分背景并入主体。")
    if similarity < 0.965:
        reasons.append("重组相似度低于 0.965，需要检查分层重叠或缺失。")
    return {
        "overall_score": round(
            100.0 * (0.55 * similarity + 0.45 * float(subject_info["confidence"])), 2
        ),
        "recomposition_similarity": round(similarity, 6),
        "mean_absolute_error": round(mae, 4),
        "psnr_db": round(psnr, 3),
        "subject_coverage": round(subject_coverage, 6),
        "text_coverage": round(text_coverage, 6),
        "requires_manual_review": bool(reasons),
        "manual_review_reasons": reasons,
    }


def _background_quality(background: Any, repair_mask: Any, strategy_id: str) -> dict[str, Any]:
    cv2, np, _, _, _ = _deps()
    repaired = repair_mask > 0
    if not np.any(repaired):
        return {
            "clean_score": 1.0,
            "residual_ink_ratio": 0.0,
            "texture_retention": 1.0,
        }
    gray = cv2.cvtColor(background, cv2.COLOR_RGB2GRAY)
    if strategy_id == "line_art_on_texture":
        redness = background[:, :, 0].astype(np.int16) - background[:, :, 1].astype(np.int16)
        clean = ~repaired
        baseline = float(np.percentile(redness[clean], 95)) if np.any(clean) else 18.0
        residual = repaired & (redness > max(24.0, baseline + 7.0)) & (gray < 235)
        residual_ratio = float(np.mean(residual[repaired]))
    elif strategy_id == "monochrome_line_art":
        clean = ~repaired
        baseline = float(np.percentile(gray[clean], 5)) if np.any(clean) else 235.0
        residual = repaired & (gray < baseline - 18.0)
        residual_ratio = float(np.mean(residual[repaired]))
    else:
        residual_ratio = 0.0
    high_frequency = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    inside_texture = float(np.mean(high_frequency[repaired]))
    outside_texture = (
        float(np.mean(high_frequency[~repaired])) if np.any(~repaired) else inside_texture
    )
    texture_ratio = inside_texture / max(outside_texture, 1e-6)
    texture_retention = min(texture_ratio, 1.0 / max(texture_ratio, 1e-6))
    clean_score = max(0.0, 1.0 - residual_ratio * 5.0)
    return {
        "clean_score": round(clean_score, 6),
        "residual_ink_ratio": round(residual_ratio, 6),
        "texture_retention": round(texture_retention, 6),
    }


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        return 255, 255, 255
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return 255, 255, 255


def _make_overlay(rgb: Any, subject_mask: Any, text_mask: Any) -> Any:
    _, np, _, _, _ = _deps()
    overlay = rgb.astype(np.float32)
    subject = subject_mask > 0
    text = text_mask > 0
    overlay[subject] = overlay[subject] * 0.58 + np.array([0, 235, 255]) * 0.42
    overlay[text] = overlay[text] * 0.50 + np.array([255, 64, 110]) * 0.50
    return np.clip(overlay, 0, 255).astype(np.uint8)


def _analysis_payload(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("analysis JSON must contain an object")
    return payload


def _cache_key(
    source_hash: str,
    options: DecompositionOptions,
    analysis: dict[str, Any],
    intent_profile: dict[str, Any] | None = None,
) -> str:
    payload = json.dumps(
        {
            "pipeline_version": PIPELINE_VERSION,
            "source_hash": source_hash,
            "options": asdict(options),
            "analysis": analysis,
            "intent_profile": intent_profile,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _artifact_paths_exist(job_dir: Path, manifest: dict[str, Any]) -> bool:
    for layer in manifest.get("layers", []):
        if layer.get("type") == "pixel" and not (job_dir / layer["source"]).is_file():
            return False
    return True


def decompose_image(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    options: DecompositionOptions | None = None,
    analysis_path: str | Path | None = None,
    analysis: dict[str, Any] | None = None,
    intent_path: str | Path | None = None,
    intent: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cv2, np, Image, _, _ = _deps()
    source_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_dir).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError("Input image does not exist")
    output_path.mkdir(parents=True, exist_ok=True)
    options = options or DecompositionOptions()
    source = _source_summary(source_path)
    analysis_payload = dict(analysis or _analysis_payload(analysis_path))
    if analysis_payload.get("subject_mask_path"):
        mask_path = Path(str(analysis_payload["subject_mask_path"])).expanduser().resolve()
        analysis_payload["subject_mask_path"] = str(mask_path)
    rgb = _load_rgb(source_path)
    strategy = _recommend_strategy(rgb, options.preset)
    intent_was_provided = intent is not None or intent_path is not None
    intent_payload = (
        dict(intent)
        if intent is not None
        else load_intent_profile(intent_path)
        if intent_path
        else None
    )
    intent_profile = normalise_intent_profile(
        intent_payload,
        strategy_id=strategy["id"],
        text_mode=options.text_mode,
        review_region_limit=options.review_region_limit,
    )
    cache_key = _cache_key(source["sha256"], options, analysis_payload, intent_profile)
    manifest_path = output_path / "manifest.json"
    if not force and manifest_path.is_file():
        existing = load_manifest(manifest_path)
        if existing.get("pipeline", {}).get("cache_key") == cache_key and _artifact_paths_exist(
            output_path, existing
        ):
            return {
                "ok": True,
                "cached": True,
                "job_dir": str(output_path),
                "manifest_path": str(manifest_path),
                "quality": existing.get("quality", {}),
                "review_packet_path": str(output_path / "review_packet.json"),
            }

    height, width = rgb.shape[:2]
    component_masks: list[dict[str, Any]] = []
    stroke_ambiguities: list[dict[str, Any]] = []
    if strategy["id"] in LINE_ART_STRATEGIES:
        main_subject_alpha, component_masks, subject_info = _line_art_masks(
            rgb,
            strategy_id=strategy["id"],
            allow_semantic_subdivision=intent_profile["subject_granularity"] != "whole_subject",
            separate_salient_decorations=intent_profile["decoration_policy"] == "separate_salient",
        )
        subject_mask = subject_info.pop("union_mask")
        stroke_ambiguities = (
            subject_info.get("semantic_subdivision", {})
            .get("stroke_continuity", {})
            .pop("ambiguity_components_runtime", [])
        )
        text_mask = np.zeros((height, width), dtype=np.uint8)
        text_regions: list[dict[str, Any]] = []
        subject_layer_name = str(subject_info.pop("primary_layer_name"))
        subject_rgba_alpha = main_subject_alpha
    else:
        subject_mask, subject_info = _subject_mask(rgb, analysis_payload, options.max_refinements)
        effective_text_mode = (
            "off" if intent_profile["text_policy"] == "ignore" else options.text_mode
        )
        text_mask, text_regions = _detect_text_regions(
            rgb, subject_mask, analysis_payload, effective_text_mode
        )
        subject_layer_name = "主体_01_可移动"
        subject_rgba_alpha = np.where(subject_mask > 0, 255, 0).astype(np.uint8)
    combined = np.maximum(subject_mask, text_mask)
    dilation_ratio = 0.005 if strategy["id"] in LINE_ART_STRATEGIES else 0.012
    dilation_size = max(3, int(round(min(width, height) * dilation_ratio)))
    if dilation_size % 2 == 0:
        dilation_size += 1
    repair_mask = cv2.dilate(combined, np.ones((dilation_size, dilation_size), np.uint8))
    inpaint_radius = (
        max(7, int(round(min(width, height) * 0.015)))
        if strategy["id"] in LINE_ART_STRATEGIES
        else None
    )
    background = (
        rgb.copy()
        if intent_profile["background_policy"] == "keep_original_pixels"
        else _inpaint_background(rgb, repair_mask, radius=inpaint_radius)
    )
    background_repair_applied = intent_profile["background_policy"] == "preserve_and_complete"
    subject_layer_rgb = rgb
    if strategy["id"] in LINE_ART_STRATEGIES:
        subject_layer_rgb, unmixed_alpha, unmix_info = _unmix_line_art(
            rgb,
            background,
            subject_mask,
            strategy_id=strategy["id"],
        )
        subject_rgba_alpha = np.where(main_subject_alpha > 0, unmixed_alpha, 0).astype(np.uint8)
        for component in component_masks:
            component["alpha"] = np.where(component["alpha"] > 0, unmixed_alpha, 0).astype(np.uint8)
            component["rgb"] = subject_layer_rgb
        subject_info["ink_unmix"] = unmix_info
    text_rgba_alpha = np.where(text_mask > 0, 255, 0).astype(np.uint8)
    compositing_layers = [(subject_layer_rgb, subject_rgba_alpha)]
    compositing_layers.extend((item.get("rgb", rgb), item["alpha"]) for item in component_masks)
    compositing_layers.append((rgb, text_rgba_alpha))
    recomposed = _composite(
        background,
        compositing_layers,
    )
    quality = _quality(rgb, recomposed, subject_mask, text_mask, subject_info)
    if subject_info.get("engine") == "offline_iterative_grabcut":
        subject_info["review_status"] = "unreviewed"
        quality["manual_review_reasons"].append(
            "本地主体遮罩尚未由客户确认；内部几何分数不能证明语义主体选择正确。"
        )
    semantic_subdivision = subject_info.get("semantic_subdivision", {})
    primary_layer_id = "ring_region_01" if semantic_subdivision.get("activated") else "subject_01"
    if semantic_subdivision.get("activated"):
        continuity_quality = semantic_subdivision.get("stroke_continuity", {})
        boundary_reduction = float(semantic_subdivision.get("boundary_density_reduction", 0.0))
        stroke_reduction = float(continuity_quality.get("split_component_reduction", 0.0))
        semantic_confidence = float(semantic_subdivision["confidence"])
        editability_score = 100.0 * (
            0.45 * semantic_confidence + 0.30 * boundary_reduction + 0.25 * stroke_reduction
        )
        quality["semantic_subdivision"] = {
            "region_count": int(semantic_subdivision["region_count"]),
            "mutually_exclusive": bool(semantic_subdivision["mutually_exclusive"]),
            "coverage_ratio": float(semantic_subdivision["coverage_ratio"]),
            "semantic_labels_confirmed": bool(semantic_subdivision["semantic_labels_confirmed"]),
            "confidence": semantic_confidence,
            "layer_editability_score": round(editability_score, 2),
            "boundary_density_reduction": boundary_reduction,
            "stroke_split_component_reduction": stroke_reduction,
            "stroke_changed_foreground_ratio": float(
                continuity_quality.get("changed_foreground_ratio", 0.0)
            ),
            "unresolved_stroke_components": int(
                continuity_quality.get("split_component_count_after", 0)
            ),
        }
        quality["manual_review_reasons"].append(
            "环形纹样已拆成互斥几何候选区域；语义名称尚未确认，移动单层前只需复审对应局部小图。"
        )
        unresolved_strokes = int(continuity_quality.get("split_component_count_after", 0))
        if unresolved_strokes:
            quality["manual_review_reasons"].append(
                f"仍有 {unresolved_strokes} 个大型或归属不明确的连通笔画跨层；系统已保留为歧义而未强行猜测。"
            )
    background_quality = _background_quality(background, repair_mask, strategy["id"])
    quality["background"] = background_quality
    quality["overall_score"] = round(
        100.0
        * (
            0.45 * float(quality["recomposition_similarity"])
            + 0.30 * float(subject_info["confidence"])
            + 0.25 * float(background_quality["clean_score"])
        ),
        2,
    )
    if not background_repair_applied:
        quality["manual_review_reasons"].append(
            "客户意图要求保留原始背景像素；移动主体后可能看到原主体重影，这是已确认的可编辑性取舍。"
        )
    elif background_quality["clean_score"] < 0.9:
        quality["manual_review_reasons"].append(
            "背景补全仍检测到主体色残留，移动主体前应检查鬼影。"
        )
    if strategy["id"] in LINE_ART_STRATEGIES and background_quality["texture_retention"] < 0.45:
        quality["manual_review_reasons"].append("补全区域纸纹保留率偏低，放大后可能需要纹理修补。")
    if not intent_was_provided:
        quality["manual_review_reasons"].append(
            "客户分层意图尚未显式确认；当前结果使用保守默认配置，可通过 Layer Intent Profile 重新运行。"
        )
    quality["requires_manual_review"] = bool(quality["manual_review_reasons"])

    original_rel = Path("layers/00_original_reference.png")
    background_rel = Path("layers/04_background/background_clean.png")
    subject_rel = Path("layers/02_subjects/subject_01.png")
    text_rel = Path("layers/01_text/text_reference_pixels.png")
    subject_mask_rel = Path("masks/subject_01_mask.png")
    subject_union_mask_rel = Path("masks/subject_union_mask.png")
    text_mask_rel = Path("masks/text_mask.png")
    repair_mask_rel = Path("masks/background_repair_mask.png")
    recomposed_rel = Path("preview/recomposed.png")
    overlay_rel = Path("preview/mask_overlay.png")
    _save_rgb(output_path / original_rel, rgb)
    _save_rgb(output_path / background_rel, background)
    _save_rgba(output_path / subject_rel, subject_layer_rgb, subject_rgba_alpha)
    _save_rgba(output_path / text_rel, rgb, text_rgba_alpha)
    _save_mask(
        output_path / subject_mask_rel,
        np.where(subject_rgba_alpha > 0, 255, 0).astype(np.uint8),
    )
    _save_mask(output_path / subject_union_mask_rel, subject_mask)
    _save_mask(output_path / text_mask_rel, text_mask)
    _save_mask(output_path / repair_mask_rel, repair_mask)
    _save_rgb(output_path / recomposed_rel, recomposed)
    _save_rgb(output_path / overlay_rel, _make_overlay(rgb, subject_mask, text_mask))
    stroke_ambiguity_metadata: list[dict[str, Any]] = []
    for ambiguity in stroke_ambiguities:
        ambiguity_mask_rel = Path(f"masks/stroke_ambiguities/{ambiguity['component_id']}.png")
        _save_mask(output_path / ambiguity_mask_rel, ambiguity["mask"])
        stroke_ambiguity_metadata.append(
            {
                "component_id": ambiguity["component_id"],
                "mask_source": ambiguity_mask_rel.as_posix(),
                "bbox": ambiguity["bbox"],
                "impact_score": ambiguity["impact_score"],
                "core_area": ambiguity["core_area"],
                "candidate_regions": ambiguity["candidate_regions"],
                "status": "unresolved",
            }
        )

    layers: list[dict[str, Any]] = [
        {
            "id": "background_clean",
            "name": "完整背景_已补全" if background_repair_applied else "原始背景像素_未补全",
            "group": "04_背景",
            "type": "pixel",
            "source": background_rel.as_posix(),
            "visible": True,
            "locked": False,
            "z_index": 10,
            "confidence": round(max(0.15, 1.0 - float(np.mean(repair_mask > 0))), 4),
        },
        {
            "id": primary_layer_id,
            "name": subject_layer_name,
            "group": "02_主体",
            "type": "pixel",
            "source": subject_rel.as_posix(),
            "visible": True,
            "locked": False,
            "z_index": 30,
            "confidence": float(semantic_subdivision["confidence"])
            if semantic_subdivision.get("activated")
            else subject_info["confidence"],
            "mask_source": subject_mask_rel.as_posix(),
            "bbox": subject_info.get("primary_bbox"),
            "semantic_status": "region_candidate_unreviewed"
            if semantic_subdivision.get("activated")
            else "coarse_subject",
        },
    ]
    for component_index, component in enumerate(component_masks, start=1):
        component_rel = Path(f"layers/02_subjects/{component['id']}.png")
        if component["group"] == "03_装饰":
            component_rel = Path(f"layers/03_decorations/{component['id']}.png")
        _save_rgba(
            output_path / component_rel,
            component.get("rgb", rgb),
            component["alpha"],
        )
        component_mask_rel = Path(f"masks/{component['id']}_mask.png")
        _save_mask(
            output_path / component_mask_rel,
            np.where(component["alpha"] > 0, 255, 0).astype(np.uint8),
        )
        layers.append(
            {
                "id": component["id"],
                "name": component["name"],
                "group": component["group"],
                "type": "pixel",
                "source": component_rel.as_posix(),
                "visible": True,
                "locked": False,
                "z_index": 31 + component_index,
                "confidence": component["confidence"],
                "bbox": component["bbox"],
                "mask_source": component_mask_rel.as_posix(),
                "semantic_status": component.get("semantic_status", "unreviewed"),
            }
        )
    if text_regions:
        layers.append(
            {
                "id": "text_reference_pixels",
                "name": "原文字像素_位置参考",
                "group": "01_文字",
                "type": "pixel",
                "source": text_rel.as_posix(),
                "visible": True,
                "locked": False,
                "z_index": 40,
                "confidence": round(
                    sum(float(item["confidence"]) for item in text_regions) / len(text_regions), 4
                ),
                "mask_source": text_mask_rel.as_posix(),
            }
        )
    editable_text_regions = (
        text_regions if intent_profile["text_policy"] == "editable_when_confident" else []
    )
    for index, region in enumerate(editable_text_regions, start=1):
        x1, y1, x2, y2 = region["bbox"]
        content = region["content"] or f"待识别_{index:02d}"
        layers.append(
            {
                "id": f"editable_{region['id']}",
                "name": f"可编辑文字_{index:02d}"
                if region["content"]
                else f"可编辑文字_{index:02d}_待OCR",
                "group": "01_文字",
                "type": "text",
                "content": content,
                "position": [x1, y1 + max(12, int(region["font_size"]))],
                "bbox": [x1, y1, x2, y2],
                "font_size": int(region["font_size"]),
                "font_candidates": region["font_candidates"],
                "color": region["color"],
                "visible": bool(region["content"]),
                "locked": False,
                "z_index": 50 + index,
                "confidence": region["confidence"],
            }
        )
    layers.extend(
        [
            {
                "id": "original_reference",
                "name": "原图参考_锁定_默认隐藏",
                "group": "00_原始参考",
                "type": "pixel",
                "source": original_rel.as_posix(),
                "visible": False,
                "locked": True,
                "z_index": 90,
                "confidence": 1.0,
            },
            {
                "id": "repair_mask_qa",
                "name": "QA_背景修补区域",
                "group": "99_QA",
                "type": "pixel",
                "source": repair_mask_rel.as_posix(),
                "visible": False,
                "locked": True,
                "z_index": 100,
                "confidence": 1.0,
            },
        ]
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _utc_now(),
        "source": source,
        "canvas": {
            "width": width,
            "height": height,
            "resolution": options.resolution,
            "color_mode": "RGB",
        },
        "preset": options.preset,
        "strategy": strategy,
        "intent": {
            "status": "explicit" if intent_was_provided else "conservative_default",
            "profile_sha256": intent_profile_hash(intent_profile),
            "profile": intent_profile,
            "applied_controls": [
                "subject_granularity",
                "text_policy",
                "background_policy",
                "decoration_policy",
                "review_budget",
            ],
        },
        "groups_bottom_to_top": list(GROUPS_BOTTOM_TO_TOP),
        "layers": sorted(layers, key=lambda item: int(item["z_index"])),
        "analysis": {
            "subject": subject_info,
            "subject_union_mask": subject_union_mask_rel.as_posix(),
            "semantic_regions": [
                {
                    "region_id": layer["id"],
                    "name": layer["name"],
                    "bbox": layer.get("bbox"),
                    "confidence": layer["confidence"],
                    "semantic_status": layer.get("semantic_status"),
                }
                for layer in layers
                if layer.get("semantic_status") == "region_candidate_unreviewed"
            ],
            "stroke_ambiguities": stroke_ambiguity_metadata,
            "text_regions": text_regions,
            "background_repair_coverage": round(float(np.mean(repair_mask > 0)), 6),
            "background_repair_applied": background_repair_applied,
        },
        "quality": quality,
        "pipeline": {
            "version": PIPELINE_VERSION,
            "cache_key": cache_key,
            "options": asdict(options),
            "iteration": 1,
            "previous_manifest": None,
        },
        "token_policy": {
            "local_first": True,
            "full_image_sent_to_model": False,
            "review_mode": "staged_crops_with_manifest_or_local_alpha_patch",
        },
    }
    write_manifest(manifest_path, manifest)

    review_dir = output_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_items: list[dict[str, Any]] = []
    review_limit = int(intent_profile["review_budget"]["max_total_crops"])
    text_review_regions = (
        text_regions if intent_profile["text_policy"] == "editable_when_confident" else []
    )
    for region in text_review_regions:
        if region["content"] and region["confidence"] >= 0.85:
            continue
        if len(review_items) >= review_limit:
            break
        x1, y1, x2, y2 = region["bbox"]
        pad = max(6, int((y2 - y1) * 0.3))
        x1, y1, x2, y2 = _normalise_bbox((x1 - pad, y1 - pad, x2 + pad, y2 + pad), width, height)
        crop = Image.fromarray(rgb[y1:y2, x1:x2], "RGB")
        crop.thumbnail((768, 256), Image.Resampling.LANCZOS)
        crop_rel = Path(f"review/{region['id']}.png")
        crop.save(output_path / crop_rel)
        review_items.append(
            {
                "kind": "text_ocr",
                "region_id": region["id"],
                "crop": crop_rel.as_posix(),
                "question": "只识别这块文字内容；返回 content、候选字体类别和颜色，不重分析整张图。",
            }
        )
    if (
        subject_info.get("engine") == "offline_iterative_grabcut"
        or subject_info["confidence"] < 0.78
    ):
        review_items.append(
            {
                "kind": "subject_mask",
                "mask_id": "subject_01",
                "overlay": overlay_rel.as_posix(),
                "question": (
                    "确认青色是否只覆盖客户希望独立移动的主体；返回 accepted、0–1 质量分数和失败模式，"
                    "不要把重组相似度当成语义正确证据。"
                ),
            }
        )
    semantic_region_layers = [
        layer for layer in layers if layer.get("semantic_status") == "region_candidate_unreviewed"
    ]
    remaining_review_slots = max(0, review_limit - len(review_items))
    for layer in semantic_region_layers[:remaining_review_slots]:
        bbox = layer.get("bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        pad = max(8, int(round(max(x2 - x1, y2 - y1) * 0.06)))
        x1, y1, x2, y2 = _normalise_bbox((x1 - pad, y1 - pad, x2 + pad, y2 + pad), width, height)
        layer_mask_path = output_path / str(layer["mask_source"])
        with Image.open(layer_mask_path) as mask_image:
            local_mask = np.asarray(mask_image.convert("L"), dtype=np.uint8)[y1:y2, x1:x2]
        crop_rgb = rgb[y1:y2, x1:x2].astype(np.float32)
        selected = local_mask > 0
        crop_rgb[~selected] *= 0.38
        crop_rgb[selected] = crop_rgb[selected] * 0.72 + np.array([0, 205, 255]) * 0.28
        crop = Image.fromarray(np.clip(crop_rgb, 0, 255).astype(np.uint8), "RGB")
        crop.thumbnail((420, 420), Image.Resampling.LANCZOS)
        crop_rel = Path(f"review/{layer['id']}.png")
        crop.save(output_path / crop_rel)
        review_items.append(
            {
                "kind": "semantic_region_label",
                "region_id": layer["id"],
                "crop": crop_rel.as_posix(),
                "current_name": layer["name"],
                "question": "只判断青色区域的简短语义名称并确认边界是否可用；不要重分析整张图。",
            }
        )
    ambiguity_review_queue: list[dict[str, Any]] = []
    for ambiguity in stroke_ambiguity_metadata:
        bbox = ambiguity.get("bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        pad = max(10, int(round(max(x2 - x1, y2 - y1) * 0.12)))
        x1, y1, x2, y2 = _normalise_bbox((x1 - pad, y1 - pad, x2 + pad, y2 + pad), width, height)
        with Image.open(output_path / str(ambiguity["mask_source"])) as mask_image:
            local_mask = np.asarray(mask_image.convert("L"), dtype=np.uint8)[y1:y2, x1:x2]
        crop_rgb = rgb[y1:y2, x1:x2].astype(np.float32)
        selected = local_mask > 0
        crop_rgb[~selected] *= 0.42
        crop_rgb[selected] = crop_rgb[selected] * 0.68 + np.array([255, 190, 0]) * 0.32
        crop = Image.fromarray(np.clip(crop_rgb, 0, 255).astype(np.uint8), "RGB")
        crop.thumbnail((420, 420), Image.Resampling.LANCZOS)
        crop_rel = Path(f"review/{ambiguity['component_id']}.png")
        crop.save(output_path / crop_rel)
        ambiguity_review_queue.append(
            {
                "kind": "stroke_ambiguity_assignment",
                "component_id": ambiguity["component_id"],
                "crop": crop_rel.as_posix(),
                "candidate_region_ids": [
                    item["region_id"] for item in ambiguity["candidate_regions"]
                ],
                "question": "只判断黄色连通笔画应整体归入哪个候选区域；返回 target_region_id，不重分析整张图。",
            }
        )
    max_active_ambiguities = int(intent_profile["review_budget"]["max_active_crops"])
    if review_items:
        active_review_items = review_items
        deferred_ambiguities = ambiguity_review_queue[:max_active_ambiguities]
        queued_ambiguities = ambiguity_review_queue[max_active_ambiguities:]
        review_stage = "semantic_region_labeling" if semantic_region_layers else "candidate_review"
    elif ambiguity_review_queue:
        active_review_items = ambiguity_review_queue[:max_active_ambiguities]
        deferred_ambiguities = []
        queued_ambiguities = ambiguity_review_queue[max_active_ambiguities:]
        review_stage = "stroke_ambiguity_assignment"
    else:
        active_review_items = []
        deferred_ambiguities = []
        queued_ambiguities = []
        review_stage = "complete"
    review_packet = {
        "schema_version": "starbridge.layer_review_packet.v1",
        "created_at": _utc_now(),
        "source_sha256_12": source["sha256_12"],
        "manifest": "manifest.json",
        "stage": review_stage,
        "items": active_review_items,
        "deferred_items": deferred_ambiguities,
        "queued_items": queued_ambiguities,
        "expected_response": {
            "schema_version": "starbridge.layer_review_patch.v1",
            "text_regions": [
                {
                    "region_id": "text_01",
                    "content": "识别出的文字",
                    "font_candidates": ["sans-serif-heavy"],
                    "color": "#FFFFFF",
                    "confidence": 0.9,
                }
            ],
            "semantic_regions": [
                {
                    "region_id": "ring_region_01",
                    "name": "上方神兽_候选区域",
                    "semantic_label": "神兽",
                    "accepted": True,
                    "confidence": 0.9,
                }
            ],
            "stroke_assignments": [
                {
                    "component_id": "stroke_ambiguity_01",
                    "target_region_id": "ring_region_01",
                    "confidence": 0.9,
                }
            ],
            "subject_masks": [
                {
                    "mask_id": "subject_01",
                    "accepted": False,
                    "quality_score": 0.45,
                    "failure_modes": ["over_selection"],
                    "confidence": 0.95,
                }
            ],
        },
        "token_saving": {
            "send_full_image": False,
            "send_only_listed_crops": True,
            "reuse_manifest_on_next_iteration": True,
            "max_active_ambiguity_crops": max_active_ambiguities,
            "max_total_crops": review_limit,
        },
        "intent_profile_sha256": intent_profile_hash(intent_profile),
    }
    review_packet_path = output_path / "review_packet.json"
    review_packet_path.write_text(
        json.dumps(review_packet, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "ok": True,
        "cached": False,
        "job_dir": str(output_path),
        "manifest_path": str(manifest_path),
        "review_packet_path": str(review_packet_path),
        "review_items": len(active_review_items),
        "quality": quality,
    }


def _apply_stroke_assignments(
    manifest_file: Path,
    manifest: dict[str, Any],
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    _, np, Image, _, _ = _deps()
    if not updates:
        return {"assigned_components": [], "changed_pixels": 0}
    job_dir = manifest_file.parent.resolve()

    def resolve_asset(relative: str) -> Path:
        path = (job_dir / relative).resolve()
        if not path.is_relative_to(job_dir):
            raise ValueError("Stroke assignment asset escaped the job directory")
        if not path.is_file():
            raise FileNotFoundError("Stroke assignment asset is missing")
        return path

    region_layers = {
        str(layer["id"]): layer
        for layer in manifest["layers"]
        if layer.get("semantic_status")
        in {"region_candidate_unreviewed", "region_candidate_accepted"}
    }
    ambiguities = {
        str(item["component_id"]): item
        for item in manifest.get("analysis", {}).get("stroke_ambiguities", [])
    }
    layer_arrays: dict[str, Any] = {}
    for region_id, layer in region_layers.items():
        with Image.open(resolve_asset(str(layer["source"]))) as image:
            layer_arrays[region_id] = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()

    assigned: list[str] = []
    changed_pixels = 0
    for update in updates:
        component_id = str(update.get("component_id") or "")
        target_region_id = str(update.get("target_region_id") or "")
        ambiguity = ambiguities.get(component_id)
        if ambiguity is None:
            raise ValueError("Unknown stroke ambiguity component_id")
        if ambiguity.get("status") == "assigned":
            continue
        candidate_ids = {str(item["region_id"]) for item in ambiguity.get("candidate_regions", [])}
        if target_region_id not in candidate_ids or target_region_id not in region_layers:
            raise ValueError("target_region_id is not allowlisted for this stroke component")
        with Image.open(resolve_asset(str(ambiguity["mask_source"]))) as mask_image:
            mask = np.asarray(mask_image.convert("L"), dtype=np.uint8) > 0
        alphas = np.stack([array[:, :, 3] for array in layer_arrays.values()])
        union_alpha = np.max(alphas, axis=0)
        previous_target = layer_arrays[target_region_id][:, :, 3].copy()
        for array in layer_arrays.values():
            array[:, :, 3][mask] = 0
        layer_arrays[target_region_id][:, :, 3][mask] = union_alpha[mask]
        changed_pixels += int(np.count_nonzero(previous_target[mask] != union_alpha[mask]))
        ambiguity["status"] = "assigned"
        ambiguity["target_region_id"] = target_region_id
        ambiguity["assignment_confidence"] = float(update.get("confidence", 0.0))
        assigned.append(component_id)

    if not assigned:
        return {"assigned_components": [], "changed_pixels": 0}

    region_analysis = {
        str(item["region_id"]): item
        for item in manifest.get("analysis", {}).get("semantic_regions", [])
    }
    for region_id, array in layer_arrays.items():
        layer = region_layers[region_id]
        Image.fromarray(array, "RGBA").save(resolve_asset(str(layer["source"])))
        if layer.get("mask_source"):
            mask_path = resolve_asset(str(layer["mask_source"]))
            Image.fromarray(np.where(array[:, :, 3] > 0, 255, 0).astype(np.uint8), "L").save(
                mask_path
            )
        bbox = _mask_bbox(array[:, :, 3])
        layer["bbox"] = bbox
        if region_id in region_analysis:
            region_analysis[region_id]["bbox"] = bbox

    if assigned:
        continuity = (
            manifest.get("analysis", {})
            .get("subject", {})
            .get("semantic_subdivision", {})
            .get("stroke_continuity", {})
        )
        original_before = int(continuity.get("split_component_count_before", 0))
        original_after = int(continuity.get("split_component_count_after", 0))
        assigned_total = sum(1 for item in ambiguities.values() if item.get("status") == "assigned")
        remaining = max(0, original_after - assigned_total)
        continuity["assigned_component_count"] = assigned_total
        continuity["split_component_count_after_review"] = remaining
        reviewed_reduction = (
            max(0.0, (original_before - remaining) / original_before) if original_before else 0.0
        )
        continuity["split_component_reduction_after_review"] = round(reviewed_reduction, 6)
        semantic_quality = manifest.get("quality", {}).get("semantic_subdivision", {})
        semantic_quality["unresolved_stroke_components"] = remaining
        semantic_quality["stroke_split_component_reduction"] = round(reviewed_reduction, 6)
        confidence = float(semantic_quality.get("confidence", 0.0))
        boundary_reduction = float(semantic_quality.get("boundary_density_reduction", 0.0))
        semantic_quality["layer_editability_score"] = round(
            100.0 * (0.45 * confidence + 0.30 * boundary_reduction + 0.25 * reviewed_reduction),
            2,
        )
        reasons = manifest.get("quality", {}).get("manual_review_reasons", [])
        reasons = [reason for reason in reasons if not str(reason).startswith("仍有 ")]
        if remaining:
            reasons.append(
                f"仍有 {remaining} 个大型或归属不明确的连通笔画跨层；系统已保留为歧义而未强行猜测。"
            )
        manifest["quality"]["manual_review_reasons"] = reasons
        manifest["quality"]["requires_manual_review"] = bool(reasons)
    return {"assigned_components": assigned, "changed_pixels": changed_pixels}


def _advance_review_packet(
    manifest_file: Path,
    *,
    semantic_labels_confirmed: bool,
    assigned_components: list[str],
    reviewed_subject_masks: list[str],
    reviewed_text_regions: list[str],
) -> None:
    packet_path = manifest_file.parent / "review_packet.json"
    if not packet_path.is_file():
        return
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assigned = set(assigned_components)
    reviewed_masks = set(reviewed_subject_masks)
    reviewed_text = set(reviewed_text_regions)
    if reviewed_masks:
        packet["items"] = [
            item for item in packet.get("items", []) if item.get("mask_id") not in reviewed_masks
        ]
    if reviewed_text:
        packet["items"] = [
            item
            for item in packet.get("items", [])
            if not (item.get("kind") == "text_ocr" and item.get("region_id") in reviewed_text)
        ]
    if semantic_labels_confirmed and packet.get("stage") == "semantic_region_labeling":
        packet["items"] = list(packet.get("deferred_items", []))
        packet["deferred_items"] = []
        packet["stage"] = "stroke_ambiguity_assignment" if packet["items"] else "complete"
    if assigned:
        packet["items"] = [
            item for item in packet.get("items", []) if item.get("component_id") not in assigned
        ]
        packet["deferred_items"] = [
            item
            for item in packet.get("deferred_items", [])
            if item.get("component_id") not in assigned
        ]
        queued = [
            item
            for item in packet.get("queued_items", [])
            if item.get("component_id") not in assigned
        ]
        max_active = int(packet.get("token_saving", {}).get("max_active_ambiguity_crops", 2))
        while len(packet["items"]) < max_active and queued:
            packet["items"].append(queued.pop(0))
        packet["queued_items"] = queued
        if not packet["items"]:
            packet["stage"] = "complete"
    if not packet.get("items") and packet.get("deferred_items"):
        packet["items"] = list(packet["deferred_items"])
        packet["deferred_items"] = []
        packet["stage"] = "stroke_ambiguity_assignment"
    if (
        not packet.get("items")
        and not packet.get("deferred_items")
        and not packet.get("queued_items")
    ):
        packet["stage"] = "complete"
    packet["updated_at"] = _utc_now()
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_decision_examples(
    manifest_file: Path,
    manifest: dict[str, Any],
    patch: dict[str, Any],
    stroke_result: dict[str, Any],
) -> int:
    learning_policy = manifest.get("intent", {}).get("profile", {}).get("learning", {})
    if not learning_policy.get("record_decisions"):
        return 0
    if learning_policy.get("include_pixels"):
        raise ValueError("Pixel-bearing learning records are not supported")

    width = int(manifest["canvas"]["width"])
    height = int(manifest["canvas"]["height"])

    def normalised_bbox(bbox: list[int] | None) -> list[float] | None:
        if not bbox:
            return None
        return [
            round(float(bbox[0]) / width, 6),
            round(float(bbox[1]) / height, 6),
            round(float(bbox[2]) / width, 6),
            round(float(bbox[3]) / height, 6),
        ]

    base = {
        "schema_version": "starbridge.layer_decision_example.v1",
        "pipeline_version": manifest.get("pipeline", {}).get("version"),
        "source_fingerprint": manifest.get("source", {}).get("sha256_12"),
        "intent_profile_sha256": manifest.get("intent", {}).get("profile_sha256"),
        "includes_pixels": False,
    }
    examples: list[dict[str, Any]] = []
    subject = manifest.get("analysis", {}).get("subject", {})
    selected_candidate = int(subject.get("selected_candidate", 0))
    subject_candidate = next(
        (
            item
            for item in subject.get("candidates", [])
            if int(item.get("candidate", -1)) == selected_candidate
        ),
        {},
    )
    for update in patch.get("subject_masks", []):
        if str(update.get("mask_id")) != "subject_01":
            continue
        examples.append(
            {
                **base,
                "decision_type": "subject_mask_review",
                "features": {
                    "engine": str(subject.get("engine") or "unknown"),
                    "candidate_score": float(subject_candidate.get("score", 0.0)),
                    "coverage": float(subject_candidate.get("coverage", 0.0)),
                    "center_overlap": float(subject_candidate.get("center_overlap", 0.0)),
                    "border_touch": float(subject_candidate.get("border_touch", 0.0)),
                    "edge_alignment": float(subject_candidate.get("edge_alignment", 0.0)),
                    "recomposition_similarity": float(
                        manifest.get("quality", {}).get("recomposition_similarity", 0.0)
                    ),
                },
                "decision": {
                    "accepted": bool(update.get("accepted")),
                    "quality_score": float(update.get("quality_score", 0.0)),
                    "failure_modes": list(update.get("failure_modes", [])),
                    "confidence": float(update.get("confidence", 0.0)),
                },
            }
        )
    semantic_regions = {
        str(item["region_id"]): item
        for item in manifest.get("analysis", {}).get("semantic_regions", [])
    }
    for update in patch.get("semantic_regions", []):
        region = semantic_regions.get(str(update.get("region_id")))
        if not region:
            continue
        examples.append(
            {
                **base,
                "decision_type": "semantic_region_review",
                "features": {
                    "bbox_normalized": normalised_bbox(region.get("bbox")),
                    "candidate_confidence": float(region.get("confidence", 0.0)),
                },
                "decision": {
                    "accepted": bool(update.get("accepted")),
                    "semantic_label": str(update.get("semantic_label") or ""),
                    "confidence": float(update.get("confidence", 0.0)),
                },
            }
        )
    text_regions = {
        str(item["id"]): item for item in manifest.get("analysis", {}).get("text_regions", [])
    }
    for update in patch.get("text_regions", []):
        region = text_regions.get(str(update.get("region_id")))
        if not region:
            continue
        examples.append(
            {
                **base,
                "decision_type": "text_region_review",
                "features": {
                    "bbox_normalized": normalised_bbox(region.get("bbox")),
                    "candidate_confidence": float(region.get("confidence", 0.0)),
                },
                "decision": {
                    "content_was_confirmed": bool(update.get("content")),
                    "font_candidates": list(update.get("font_candidates", []))[:3],
                    "confidence": float(update.get("confidence", 0.0)),
                },
            }
        )
    assigned = set(stroke_result.get("assigned_components", []))
    ambiguities = {
        str(item["component_id"]): item
        for item in manifest.get("analysis", {}).get("stroke_ambiguities", [])
    }
    for update in patch.get("stroke_assignments", []):
        component_id = str(update.get("component_id") or "")
        if component_id not in assigned:
            continue
        ambiguity = ambiguities[component_id]
        candidates = list(ambiguity.get("candidate_regions", []))
        target = str(update.get("target_region_id") or "")
        target_rank = next(
            (index for index, item in enumerate(candidates) if item.get("region_id") == target),
            -1,
        )
        examples.append(
            {
                **base,
                "decision_type": "stroke_component_assignment",
                "features": {
                    "bbox_normalized": normalised_bbox(ambiguity.get("bbox")),
                    "impact_score": float(ambiguity.get("impact_score", 0.0)),
                    "core_area_ratio": round(
                        float(ambiguity.get("core_area", 0)) / max(width * height, 1), 8
                    ),
                    "candidate_shares": [float(item.get("share", 0.0)) for item in candidates],
                },
                "decision": {
                    "target_candidate_rank": target_rank,
                    "confidence": float(update.get("confidence", 0.0)),
                },
            }
        )
    if not examples:
        return 0

    learning_dir = manifest_file.parent / "learning"
    learning_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = learning_dir / "decision_examples.jsonl"
    existing_ids: set[str] = set()
    if dataset_path.is_file():
        for line in dataset_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_ids.add(str(json.loads(line).get("example_id")))
    new_examples: list[dict[str, Any]] = []
    for example in examples:
        example_id = hashlib.sha256(
            json.dumps(example, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        if example_id in existing_ids:
            continue
        new_examples.append({"example_id": example_id, **example})
        existing_ids.add(example_id)
    if new_examples:
        with dataset_path.open("a", encoding="utf-8", newline="\n") as handle:
            for example in new_examples:
                handle.write(json.dumps(example, ensure_ascii=False, sort_keys=True) + "\n")
    manifest["learning"] = {
        "enabled": True,
        "dataset": "learning/decision_examples.jsonl",
        "example_count": len(existing_ids),
        "includes_pixels": False,
        "source_paths_recorded": False,
    }
    return len(new_examples)


def _validate_review_patch(patch: dict[str, Any]) -> None:
    if patch.get("schema_version") != "starbridge.layer_review_patch.v1":
        raise ValueError("Unsupported review patch schema_version")
    allowed_fields = {
        "text_regions": {"region_id", "content", "font_candidates", "color", "confidence"},
        "subject_masks": {
            "mask_id",
            "accepted",
            "quality_score",
            "failure_modes",
            "confidence",
        },
        "semantic_regions": {
            "region_id",
            "name",
            "semantic_label",
            "accepted",
            "confidence",
        },
        "stroke_assignments": {"component_id", "target_region_id", "confidence"},
    }
    unknown_top_level = set(patch) - {"schema_version", *allowed_fields}
    if unknown_top_level:
        raise ValueError(f"Unsupported review patch keys: {sorted(unknown_top_level)!r}")
    if not any(field in patch for field in allowed_fields):
        raise ValueError("Review patch must contain at least one decision array")
    for field, allowed in allowed_fields.items():
        values = patch.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"review patch {field} must be an array")
        if len(values) > 64:
            raise ValueError(f"review patch {field} cannot contain more than 64 entries")
        for item in values:
            if not isinstance(item, dict):
                raise ValueError(f"review patch {field} entries must be objects")
            unknown = set(item) - allowed
            if unknown:
                raise ValueError(f"Unsupported {field} keys: {sorted(unknown)!r}")
            identifier = {
                "stroke_assignments": "component_id",
                "subject_masks": "mask_id",
            }.get(field, "region_id")
            identifier_value = str(item.get(identifier) or "").strip()
            if not identifier_value:
                raise ValueError(f"review patch {field}.{identifier} is required")
            if len(identifier_value) > 128:
                raise ValueError(f"review patch {field}.{identifier} is too long")
            if (
                field == "stroke_assignments"
                and not str(item.get("target_region_id") or "").strip()
            ):
                raise ValueError("review patch stroke_assignments.target_region_id is required")
            if field == "subject_masks" and not isinstance(item.get("accepted"), bool):
                raise ValueError("review patch subject_masks.accepted must be boolean")
            for string_key, maximum in (
                ("content", 512),
                ("name", 128),
                ("semantic_label", 128),
                ("color", 32),
                ("target_region_id", 128),
            ):
                if string_key in item and len(str(item[string_key])) > maximum:
                    raise ValueError(f"review patch {field}.{string_key} is too long")
            if "font_candidates" in item:
                fonts = item["font_candidates"]
                if not isinstance(fonts, list) or len(fonts) > 5:
                    raise ValueError("review patch font_candidates must contain at most 5 entries")
                if any(len(str(font)) > 128 for font in fonts):
                    raise ValueError("review patch font candidate is too long")
            if "confidence" in item:
                confidence = float(item["confidence"])
                if not 0.0 <= confidence <= 1.0:
                    raise ValueError("review patch confidence must be between 0 and 1")
            if "quality_score" in item:
                quality_score = float(item["quality_score"])
                if not 0.0 <= quality_score <= 1.0:
                    raise ValueError("review patch quality_score must be between 0 and 1")
            if "failure_modes" in item:
                failure_modes = item["failure_modes"]
                allowed_failure_modes = {
                    "over_selection",
                    "under_selection",
                    "wrong_subject",
                    "edge_quality",
                }
                if (
                    not isinstance(failure_modes, list)
                    or len(failure_modes) > 4
                    or not set(failure_modes).issubset(allowed_failure_modes)
                ):
                    raise ValueError("review patch failure_modes are not allowlisted")


def apply_review_patch(manifest_path: str | Path, patch_path: str | Path) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    patch_file = Path(patch_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    patch = json.loads(patch_file.read_text(encoding="utf-8"))
    if not isinstance(patch, dict):
        raise ValueError("Review patch must contain an object")
    _validate_review_patch(patch)
    updates = {str(item["region_id"]): item for item in patch.get("text_regions", [])}
    semantic_updates = {str(item["region_id"]): item for item in patch.get("semantic_regions", [])}
    subject_updates = {str(item["mask_id"]): item for item in patch.get("subject_masks", [])}
    stroke_updates = list(patch.get("stroke_assignments", []))
    changed: list[str] = []
    changed_semantic: list[str] = []
    for region in manifest.get("analysis", {}).get("text_regions", []):
        update = updates.get(str(region["id"]))
        if not update:
            continue
        for key in ("content", "font_candidates", "color", "confidence"):
            if key in update:
                region[key] = update[key]
        changed.append(str(region["id"]))
    for layer in manifest["layers"]:
        if layer["type"] != "text" or not layer["id"].startswith("editable_"):
            continue
        region_id = layer["id"][len("editable_") :]
        update = updates.get(region_id)
        if not update:
            continue
        if update.get("content"):
            layer["content"] = str(update["content"])
            layer["name"] = layer["name"].replace("_待OCR", "")
            layer["visible"] = True
        for key in ("font_candidates", "color", "confidence"):
            if key in update:
                layer[key] = update[key]
    for region in manifest.get("analysis", {}).get("semantic_regions", []):
        update = semantic_updates.get(str(region["region_id"]))
        if not update:
            continue
        for key in ("name", "semantic_label", "confidence", "accepted"):
            if key in update:
                region[key] = update[key]
        if update.get("accepted"):
            region["semantic_status"] = "region_candidate_accepted"
        changed_semantic.append(str(region["region_id"]))
    for layer in manifest["layers"]:
        update = semantic_updates.get(str(layer["id"]))
        if not update:
            continue
        if update.get("name"):
            layer["name"] = str(update["name"])
        for key in ("semantic_label", "confidence", "accepted"):
            if key in update:
                layer[key] = update[key]
        if update.get("accepted"):
            layer["semantic_status"] = "region_candidate_accepted"
    semantic_regions = manifest.get("analysis", {}).get("semantic_regions", [])
    accepted_semantic_count = sum(1 for region in semantic_regions if region.get("accepted"))
    semantic_region_count = len(semantic_regions)
    semantic_labels_confirmed = bool(
        semantic_region_count and accepted_semantic_count == semantic_region_count
    )
    if semantic_labels_confirmed:
        subdivision = (
            manifest.get("analysis", {}).get("subject", {}).get("semantic_subdivision", {})
        )
        subdivision["semantic_labels_confirmed"] = True
        semantic_quality = manifest.get("quality", {}).get("semantic_subdivision", {})
        semantic_quality["semantic_labels_confirmed"] = True
        reasons = manifest.get("quality", {}).get("manual_review_reasons", [])
        manifest["quality"]["manual_review_reasons"] = [
            reason
            for reason in reasons
            if not str(reason).startswith("环形纹样已拆成互斥几何候选区域")
        ]
        manifest["quality"]["requires_manual_review"] = bool(
            manifest["quality"]["manual_review_reasons"]
        )
    subject_review: dict[str, Any] = {"reviewed": False, "accepted": None}
    subject_update = subject_updates.get("subject_01")
    if subject_update:
        subject = manifest.get("analysis", {}).get("subject", {})
        accepted = bool(subject_update["accepted"])
        subject["review_status"] = "accepted" if accepted else "rejected"
        subject["human_quality_score"] = float(subject_update.get("quality_score", 0.0))
        subject["failure_modes"] = list(subject_update.get("failure_modes", []))
        subject["review_confidence"] = float(subject_update.get("confidence", 0.0))
        for layer in manifest["layers"]:
            if layer.get("id") == "subject_01":
                layer["subject_review_status"] = subject["review_status"]
        reasons = [
            reason
            for reason in manifest["quality"].get("manual_review_reasons", [])
            if not str(reason).startswith("本地主体遮罩尚未由客户确认")
            and not str(reason).startswith("客户复核已拒绝当前主体遮罩")
        ]
        if not accepted:
            reasons.append("客户复核已拒绝当前主体遮罩；修正前不得作为可训练的正样本。")
        manifest["quality"]["manual_review_reasons"] = reasons
        manifest["quality"]["requires_manual_review"] = bool(reasons)
        subject_review = {
            "reviewed": True,
            "accepted": accepted,
            "quality_score": subject["human_quality_score"],
            "failure_modes": subject["failure_modes"],
        }
    stroke_result = _apply_stroke_assignments(manifest_file, manifest, stroke_updates)
    pipeline = manifest.setdefault("pipeline", {})
    previous_cache_key = pipeline.get("cache_key")
    pipeline["iteration"] = int(pipeline.get("iteration", 1)) + 1
    pipeline["previous_cache_key"] = previous_cache_key
    pipeline["last_patch_name"] = patch_file.name
    pipeline["patched_at"] = _utc_now()
    if stroke_result["assigned_components"]:
        pipeline["artifact_revision"] = int(pipeline.get("artifact_revision", 0)) + 1
    pipeline["cache_key"] = hashlib.sha256(
        (str(previous_cache_key) + json.dumps(patch, sort_keys=True, ensure_ascii=False)).encode(
            "utf-8"
        )
    ).hexdigest()
    recorded_examples = _record_decision_examples(
        manifest_file,
        manifest,
        patch,
        stroke_result,
    )
    write_manifest(manifest_file, manifest)
    _advance_review_packet(
        manifest_file,
        semantic_labels_confirmed=semantic_labels_confirmed,
        assigned_components=stroke_result["assigned_components"],
        reviewed_subject_masks=list(subject_updates),
        reviewed_text_regions=changed,
    )
    return {
        "ok": True,
        "manifest_path": str(manifest_file),
        "changed_regions": changed,
        "changed_semantic_regions": changed_semantic,
        "semantic_review_progress": {
            "accepted": accepted_semantic_count,
            "total": semantic_region_count,
            "labels_confirmed": semantic_labels_confirmed,
        },
        "subject_review": subject_review,
        "iteration": pipeline["iteration"],
        "stroke_assignment": stroke_result,
        "learning_examples_recorded": recorded_examples,
        "reprocessed_pixels": bool(stroke_result["assigned_components"]),
        "full_image_analysis_repeated": False,
        "background_recomputed": False,
        "token_policy": (
            "local alpha patch applied; full image analysis and background rebuild were not repeated"
            if stroke_result["assigned_components"]
            else "manifest diff applied; full image analysis was not repeated"
        ),
    }


def batch_decompose(
    input_dir: str | Path,
    output_root: str | Path,
    *,
    options: DecompositionOptions | None = None,
    intent_path: str | Path | None = None,
    intent: dict[str, Any] | None = None,
    workers: int = 2,
    force: bool = False,
) -> dict[str, Any]:
    source_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_root).expanduser().resolve()
    if not source_dir.is_dir():
        raise NotADirectoryError("Input directory does not exist")
    output_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    options = options or DecompositionOptions()
    intent_payload = (
        dict(intent)
        if intent is not None
        else load_intent_profile(intent_path)
        if intent_path
        else None
    )
    intent_was_provided = intent is not None or intent_path is not None
    results: list[dict[str, Any]] = []

    def run_one(path: Path) -> dict[str, Any]:
        digest = _sha256(path)[:8]
        job_dir = output_dir / f"{_safe_stem(path.stem)}_{digest}"
        result = decompose_image(
            path,
            job_dir,
            options=options,
            intent=intent_payload,
            force=force,
        )
        return {
            "source_name": path.name,
            "ok": bool(result["ok"]),
            "cached": bool(result.get("cached")),
            "job_id": job_dir.name,
            "manifest": "manifest.json",
            "review_packet": "review_packet.json",
            "quality": result.get("quality", {}),
        }

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 4))) as pool:
        futures = {pool.submit(run_one, path): path for path in images}
        for future in as_completed(futures):
            path = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "source_name": path.name,
                        "error_type": type(exc).__name__,
                        "error": "Image decomposition failed for the named input.",
                    }
                )
    results.sort(key=lambda item: str(item["source_name"]))
    report = {
        "schema_version": "starbridge.image_to_editable_psd.batch.v1",
        "created_at": _utc_now(),
        "input_count": len(images),
        "completed": sum(1 for item in results if item.get("ok")),
        "cached": sum(1 for item in results if item.get("cached")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "options": asdict(options),
        "intent_status": "explicit" if intent_was_provided else "conservative_default",
        "results": results,
        "resume": "Re-run the same command; matching content hashes reuse completed jobs.",
    }
    report_path = output_dir / "batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**report, "report_path": str(report_path)}
