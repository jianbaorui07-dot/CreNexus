from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .presets import VectorPreset


class ArtisanComplexityError(RuntimeError):
    pass


ARTISAN_ROLE_ORDER = ("foundation", "subject", "detail", "accent")
ARTISAN_ROLE_LABELS_ZH = {
    "foundation": "基础",
    "subject": "主体",
    "detail": "细节",
    "accent": "点睛",
}


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    smooth: bool
    tangent_x: float
    tangent_y: float


@dataclass
class ArtisanShape:
    shape_id: str
    label: int
    path_parts: tuple[str, ...]
    outer_contour: Any
    outer_area: float
    area: float
    bbox: tuple[int, int, int, int]
    touches_canvas: bool
    hole_count: int
    anchors: int
    baseline_anchors: int
    control_points: int
    curve_segments: int
    line_segments: int
    corner_anchors: int
    smooth_anchors: int
    source_contour_points: int
    contour_error_total: float
    contour_error_samples: int
    maximum_contour_error: float
    area_error_total: float
    area_error_weight: float
    maximum_area_error_ratio: float
    compound_area_error_ratio: float
    adapted_contours: int
    quality_fallback_contours: int
    kind: str = "paint"
    parent_shape_id: str | None = None
    depth: int = 0
    role: str = "accent"

    @property
    def subpath_count(self) -> int:
        return len(self.path_parts)


@dataclass(frozen=True)
class ArtisanScene:
    width: int
    height: int
    shapes: tuple[ArtisanShape, ...]
    strategy: str = "geometry-hierarchy-v1"

    def ordered_layers(self) -> tuple[tuple[str, tuple[ArtisanShape, ...]], ...]:
        layers: list[tuple[str, tuple[ArtisanShape, ...]]] = []
        for role in ARTISAN_ROLE_ORDER:
            members = tuple(
                sorted(
                    (shape for shape in self.shapes if shape.role == role),
                    key=lambda shape: (shape.depth, -shape.area, shape.shape_id),
                )
            )
            if members:
                layers.append((role, members))
        return tuple(layers)


def _edge_coordinate(value: int, extent: int) -> float:
    if value >= extent - 1:
        return float(extent)
    return float(max(0, value))


def _deduplicated_points(contour: Any, width: int, height: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for raw_x, raw_y in contour.reshape((-1, 2)):
        point = (_edge_coordinate(int(raw_x), width), _edge_coordinate(int(raw_y), height))
        if not points or point != points[-1]:
            points.append(point)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


def _interior_angle(
    previous: tuple[float, float],
    current: tuple[float, float],
    following: tuple[float, float],
) -> float:
    first = (previous[0] - current[0], previous[1] - current[1])
    second = (following[0] - current[0], following[1] - current[1])
    first_length = math.hypot(*first)
    second_length = math.hypot(*second)
    if first_length == 0 or second_length == 0:
        return 0.0
    cosine = (first[0] * second[0] + first[1] * second[1]) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _anchors(points: list[tuple[float, float]], corner_angle: float) -> tuple[list[Anchor], int]:
    anchors: list[Anchor] = []
    corner_count = 0
    for index, current in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        smooth = _interior_angle(previous, current, following) >= corner_angle
        if smooth:
            tangent_x = following[0] - previous[0]
            tangent_y = following[1] - previous[1]
            length = math.hypot(tangent_x, tangent_y)
            if length:
                tangent_x /= length
                tangent_y /= length
            else:
                smooth = False
        if not smooth:
            tangent_x = 0.0
            tangent_y = 0.0
            corner_count += 1
        anchors.append(Anchor(current[0], current[1], smooth, tangent_x, tangent_y))
    return anchors, corner_count


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _format_coordinate(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=0.0005):
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _point_text(x: float, y: float) -> str:
    return f"{_format_coordinate(x)} {_format_coordinate(y)}"


def _closed_path(
    points: list[tuple[float, float]],
    *,
    corner_angle: float,
    smoothing: float,
) -> tuple[str, dict[str, Any]]:
    anchors, corner_count = _anchors(points, corner_angle)
    minimum_x = min(anchor.x for anchor in anchors)
    maximum_x = max(anchor.x for anchor in anchors)
    minimum_y = min(anchor.y for anchor in anchors)
    maximum_y = max(anchor.y for anchor in anchors)
    commands = [f"M {_point_text(anchors[0].x, anchors[0].y)}"]
    curves = 0
    lines = 0
    controls = 0
    sampled_points: list[tuple[float, float]] = [(anchors[0].x, anchors[0].y)]

    for index, current in enumerate(anchors):
        following = anchors[(index + 1) % len(anchors)]
        is_closing_segment = index == len(anchors) - 1
        chord = math.hypot(following.x - current.x, following.y - current.y)
        if smoothing > 0 and (current.smooth or following.smooth):
            handle = chord * smoothing / 3.0
            control_1 = (
                _clamp(current.x + current.tangent_x * handle, minimum_x, maximum_x),
                _clamp(current.y + current.tangent_y * handle, minimum_y, maximum_y),
            )
            control_2 = (
                _clamp(following.x - following.tangent_x * handle, minimum_x, maximum_x),
                _clamp(following.y - following.tangent_y * handle, minimum_y, maximum_y),
            )
            commands.append(
                "C "
                f"{_point_text(*control_1)} "
                f"{_point_text(*control_2)} "
                f"{_point_text(following.x, following.y)}"
            )
            curves += 1
            controls += 2
            for sample_index in range(1, 13):
                t = sample_index / 12.0
                inverse = 1.0 - t
                sample_x = (
                    inverse**3 * current.x
                    + 3 * inverse**2 * t * control_1[0]
                    + 3 * inverse * t**2 * control_2[0]
                    + t**3 * following.x
                )
                sample_y = (
                    inverse**3 * current.y
                    + 3 * inverse**2 * t * control_1[1]
                    + 3 * inverse * t**2 * control_2[1]
                    + t**3 * following.y
                )
                sampled_points.append((sample_x, sample_y))
        else:
            if not is_closing_segment:
                commands.append(f"L {_point_text(following.x, following.y)}")
            lines += 1
            sampled_points.append((following.x, following.y))
    commands.append("Z")
    return " ".join(commands), {
        "anchors": len(anchors),
        "corners": corner_count,
        "smooth_anchors": len(anchors) - corner_count,
        "curve_segments": curves,
        "line_segments": lines,
        "control_points": controls,
        "sampled_points": sampled_points,
    }


def _contour_error(
    contour: Any,
    sampled_points: list[tuple[float, float]],
    *,
    width: int,
    height: int,
) -> tuple[float, int, float]:
    sampled_contour = np.asarray(sampled_points, dtype=np.float32)
    if len(sampled_contour) < 3:
        return 0.0, 0, 0.0
    raw_points = contour.reshape((-1, 2))
    stride = max(1, math.ceil(len(raw_points) / 256))
    total = 0.0
    count = 0
    maximum = 0.0
    for raw_x, raw_y in raw_points[::stride]:
        point = (
            _edge_coordinate(int(raw_x), width),
            _edge_coordinate(int(raw_y), height),
        )
        distance = abs(cv2.pointPolygonTest(sampled_contour, point, True))
        total += distance
        count += 1
        maximum = max(maximum, distance)
    return total, count, maximum


def _area_error(
    contour: Any, sampled_points: list[tuple[float, float]]
) -> tuple[float, float, float, float, float]:
    source_area = abs(float(cv2.contourArea(contour)))
    sampled_contour = np.asarray(sampled_points, dtype=np.float32)
    fitted_area = abs(float(cv2.contourArea(sampled_contour)))
    absolute_error = abs(fitted_area - source_area)
    weight = max(60.0, source_area)
    return absolute_error, weight, absolute_error / weight, source_area, fitted_area


def _fit_contour(
    contour: Any,
    *,
    width: int,
    height: int,
    preset: VectorPreset,
    error_tolerance: float,
    force_high_fidelity: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    perimeter = cv2.arcLength(contour, True)
    if perimeter <= 0:
        return None
    baseline_epsilon = max(0.25, perimeter * 0.004)
    baseline_contour = cv2.approxPolyDP(contour, baseline_epsilon, True)
    artisan_epsilon = max(0.6, perimeter * preset.simplify_ratio)
    smoothing = preset.curve_smoothing
    path_data = ""
    metrics: dict[str, Any] = {}
    error_total = 0.0
    error_samples = 0
    contour_maximum_error = 0.0
    area_error_total = 0.0
    area_error_weight = 60.0
    area_error_ratio = 0.0
    source_area = 0.0
    fitted_area = 0.0
    area_error_tolerance = 0.2
    adapted = 0
    quality_fallback = 0
    if not force_high_fidelity:
        for attempt in range(8):
            artisan_contour = cv2.approxPolyDP(contour, artisan_epsilon, True)
            points = _deduplicated_points(artisan_contour, width, height)
            if len(points) < 3:
                return None
            path_data, metrics = _closed_path(
                points,
                corner_angle=preset.corner_angle,
                smoothing=smoothing,
            )
            sampled_points = metrics.pop("sampled_points")
            error_total, error_samples, contour_maximum_error = _contour_error(
                contour,
                sampled_points,
                width=width,
                height=height,
            )
            (
                area_error_total,
                area_error_weight,
                area_error_ratio,
                source_area,
                fitted_area,
            ) = _area_error(contour, sampled_points)
            if (
                contour_maximum_error <= error_tolerance
                and area_error_ratio <= area_error_tolerance
            ):
                adapted = int(attempt > 0)
                break
            if artisan_epsilon > baseline_epsilon:
                artisan_epsilon = max(baseline_epsilon, artisan_epsilon * 0.62)
            elif smoothing > 0.08:
                smoothing *= 0.55
            else:
                artisan_epsilon = max(0.25, artisan_epsilon * 0.5)
    if force_high_fidelity or (
        path_data
        and metrics
        and (contour_maximum_error > error_tolerance or area_error_ratio > area_error_tolerance)
    ):
        fallback_contour = cv2.approxPolyDP(contour, 0.25, True)
        points = _deduplicated_points(fallback_contour, width, height)
        if len(points) < 3:
            return None
        path_data, metrics = _closed_path(
            points,
            corner_angle=preset.corner_angle,
            smoothing=0.0,
        )
        sampled_points = metrics.pop("sampled_points")
        error_total, error_samples, contour_maximum_error = _contour_error(
            contour,
            sampled_points,
            width=width,
            height=height,
        )
        (
            area_error_total,
            area_error_weight,
            area_error_ratio,
            source_area,
            fitted_area,
        ) = _area_error(contour, sampled_points)
        quality_fallback = 1
        adapted = 1
    if not path_data or not metrics:
        return None
    if contour_maximum_error > error_tolerance or area_error_ratio > area_error_tolerance:
        raise ArtisanComplexityError(
            "Artisan high-fidelity fallback could not satisfy the quality tolerance."
        )
    return path_data, {
        **metrics,
        "baseline_anchors": max(3, len(baseline_contour)),
        "source_contour_points": len(contour),
        "error_total": error_total,
        "error_samples": error_samples,
        "maximum_error": contour_maximum_error,
        "area_error_total": area_error_total,
        "area_error_weight": area_error_weight,
        "area_error_ratio": area_error_ratio,
        "area_error_tolerance": area_error_tolerance,
        "source_area": source_area,
        "fitted_area": fitted_area,
        "adapted": adapted,
        "quality_fallback": quality_fallback,
    }


def _direct_children(hierarchy: Any, parent_index: int) -> list[int]:
    children: list[int] = []
    child_index = int(hierarchy[parent_index][2])
    while child_index >= 0:
        children.append(child_index)
        child_index = int(hierarchy[child_index][0])
    return children


def _compound_area_error(fitted: list[tuple[str, dict[str, Any], Any]]) -> float:
    source_area = max(
        0.0,
        float(fitted[0][1]["source_area"])
        - sum(float(item[1]["source_area"]) for item in fitted[1:]),
    )
    fitted_area = max(
        0.0,
        float(fitted[0][1]["fitted_area"])
        - sum(float(item[1]["fitted_area"]) for item in fitted[1:]),
    )
    return abs(fitted_area - source_area) / max(60.0, source_area)


def _assign_shape_structure(shapes: list[ArtisanShape], width: int, height: int) -> None:
    for child in shapes:
        if child.parent_shape_id is not None:
            continue
        raw_x, raw_y = child.outer_contour.reshape((-1, 2))[0]
        point = (float(raw_x), float(raw_y))
        candidates = [
            parent
            for parent in shapes
            if parent.shape_id != child.shape_id
            and parent.outer_area > child.outer_area
            and cv2.pointPolygonTest(parent.outer_contour, point, False) >= 0
        ]
        if candidates:
            child.parent_shape_id = min(candidates, key=lambda shape: shape.outer_area).shape_id

    shape_by_id = {shape.shape_id: shape for shape in shapes}
    for shape in shapes:
        depth = 0
        parent_id = shape.parent_shape_id
        visited = {shape.shape_id}
        while parent_id is not None and parent_id not in visited:
            visited.add(parent_id)
            parent = shape_by_id[parent_id]
            depth += 1
            parent_id = parent.parent_shape_id
        shape.depth = depth

    canvas_area = float(width * height)
    largest = max(shapes, key=lambda shape: shape.area)
    foundation_ids: set[str] = set()
    for shape in shapes:
        area_ratio = shape.area / canvas_area
        if shape.touches_canvas and area_ratio >= 0.2:
            foundation_ids.add(shape.shape_id)
    if not foundation_ids and len(shapes) > 1 and largest.area / canvas_area >= 0.45:
        foundation_ids.add(largest.shape_id)

    subject_count = 0
    for shape in shapes:
        area_ratio = shape.area / canvas_area
        if shape.shape_id in foundation_ids:
            shape.role = "foundation"
        elif (shape.depth <= 1 and area_ratio >= 0.025) or (
            shape.parent_shape_id is None and area_ratio >= 0.01
        ):
            shape.role = "subject"
            subject_count += 1
        elif area_ratio >= 0.002 or shape.depth >= 1:
            shape.role = "detail"
        else:
            shape.role = "accent"
    if subject_count == 0:
        candidates = [shape for shape in shapes if shape.role != "foundation"]
        (max(candidates, key=lambda shape: shape.area) if candidates else largest).role = "subject"


def _scene_metrics(
    scene: ArtisanScene,
    *,
    skipped_contours: int,
    suppressed_foundation_holes: int,
    suppressed_foundation_islands: int,
    error_tolerance: float,
) -> dict[str, Any]:
    shapes = scene.shapes
    anchors = sum(shape.anchors for shape in shapes)
    baseline_anchors = sum(shape.baseline_anchors for shape in shapes)
    error_total = sum(shape.contour_error_total for shape in shapes)
    error_samples = sum(shape.contour_error_samples for shape in shapes)
    area_error_total = sum(shape.area_error_total for shape in shapes)
    area_error_weight = sum(shape.area_error_weight for shape in shapes)
    role_counts = {role: sum(shape.role == role for shape in shapes) for role in ARTISAN_ROLE_ORDER}
    return {
        "path_objects": len(shapes),
        "subpaths": sum(shape.subpath_count for shape in shapes),
        "anchors": anchors,
        "baseline_polygon_anchors": baseline_anchors,
        "anchor_reduction_ratio": round(
            max(0.0, 1.0 - anchors / baseline_anchors) if baseline_anchors else 0.0,
            4,
        ),
        "control_points": sum(shape.control_points for shape in shapes),
        "curve_segments": sum(shape.curve_segments for shape in shapes),
        "line_segments": sum(shape.line_segments for shape in shapes),
        "corner_anchors": sum(shape.corner_anchors for shape in shapes),
        "smooth_anchors": sum(shape.smooth_anchors for shape in shapes),
        "source_contour_points": sum(shape.source_contour_points for shape in shapes),
        "mean_contour_error_px": round(error_total / error_samples if error_samples else 0.0, 4),
        "maximum_contour_error_px": round(
            max((shape.maximum_contour_error for shape in shapes), default=0.0), 4
        ),
        "curve_error_tolerance_px": round(error_tolerance, 4),
        "mean_shape_area_error_ratio": round(
            area_error_total / area_error_weight if area_error_weight else 0.0, 6
        ),
        "maximum_shape_area_error_ratio": round(
            max((shape.maximum_area_error_ratio for shape in shapes), default=0.0), 6
        ),
        "shape_area_error_tolerance_ratio": 0.2,
        "mean_compound_area_error_ratio": round(
            sum(shape.compound_area_error_ratio for shape in shapes) / len(shapes), 6
        ),
        "maximum_compound_area_error_ratio": round(
            max((shape.compound_area_error_ratio for shape in shapes), default=0.0), 6
        ),
        "compound_area_error_tolerance_ratio": 0.12,
        "adapted_contours": sum(shape.adapted_contours for shape in shapes),
        "quality_fallback_contours": sum(shape.quality_fallback_contours for shape in shapes),
        "skipped_contours": skipped_contours,
        "structure_strategy": scene.strategy,
        "layer_count": len(scene.ordered_layers()),
        "shape_count": len(shapes),
        "knockout_shape_count": sum(shape.kind == "knockout" for shape in shapes),
        "maximum_subpaths_per_shape": max((shape.subpath_count for shape in shapes), default=0),
        "root_shape_count": sum(shape.parent_shape_id is None for shape in shapes),
        "nested_shape_count": sum(shape.parent_shape_id is not None for shape in shapes),
        "maximum_structure_depth": max((shape.depth for shape in shapes), default=0),
        "hole_count": sum(shape.hole_count for shape in shapes),
        "suppressed_foundation_holes": suppressed_foundation_holes,
        "suppressed_foundation_islands": suppressed_foundation_islands,
        "design_role_counts": role_counts,
        "stable_shape_references": True,
        "external_ai_calls": 0,
    }


def _shape_from_fitted(
    *,
    shape_id: str,
    label: int,
    fitted: list[tuple[str, dict[str, Any], Any]],
    outer_contour: Any,
    outer_area: float,
    area: float,
    bbox: tuple[int, int, int, int],
    touches_canvas: bool,
    hole_count: int,
    compound_area_error: float,
    kind: str = "paint",
    parent_shape_id: str | None = None,
) -> ArtisanShape:
    shape_metrics = [item[1] for item in fitted]
    return ArtisanShape(
        shape_id=shape_id,
        label=label,
        path_parts=tuple(item[0] for item in fitted),
        outer_contour=outer_contour,
        outer_area=outer_area,
        area=area,
        bbox=bbox,
        touches_canvas=touches_canvas,
        hole_count=hole_count,
        anchors=sum(int(item["anchors"]) for item in shape_metrics),
        baseline_anchors=sum(int(item["baseline_anchors"]) for item in shape_metrics),
        control_points=sum(int(item["control_points"]) for item in shape_metrics),
        curve_segments=sum(int(item["curve_segments"]) for item in shape_metrics),
        line_segments=sum(int(item["line_segments"]) for item in shape_metrics),
        corner_anchors=sum(int(item["corners"]) for item in shape_metrics),
        smooth_anchors=sum(int(item["smooth_anchors"]) for item in shape_metrics),
        source_contour_points=sum(int(item["source_contour_points"]) for item in shape_metrics),
        contour_error_total=sum(float(item["error_total"]) for item in shape_metrics),
        contour_error_samples=sum(int(item["error_samples"]) for item in shape_metrics),
        maximum_contour_error=max(float(item["maximum_error"]) for item in shape_metrics),
        area_error_total=sum(float(item["area_error_total"]) for item in shape_metrics),
        area_error_weight=sum(float(item["area_error_weight"]) for item in shape_metrics),
        maximum_area_error_ratio=max(float(item["area_error_ratio"]) for item in shape_metrics),
        compound_area_error_ratio=compound_area_error,
        adapted_contours=sum(int(item["adapted"]) for item in shape_metrics),
        quality_fallback_contours=sum(int(item["quality_fallback"]) for item in shape_metrics),
        kind=kind,
        parent_shape_id=parent_shape_id,
    )


def trace_artisan_scene(
    labels: Any,
    preset: VectorPreset,
) -> tuple[ArtisanScene, dict[str, Any]]:
    height, width = labels.shape
    error_tolerance = max(5.0, max(width, height) * 0.004)
    shapes: list[ArtisanShape] = []
    skipped = 0
    suppressed_foundation_holes = 0
    suppressed_foundation_islands = 0
    opaque_canvas = bool(np.all(labels >= 0))
    canvas_area = width * height
    visible_labels = [int(value) for value in np.unique(labels) if value >= 0]
    foundation_labels = {
        int(label)
        for label, count in zip(*np.unique(labels, return_counts=True), strict=True)
        if int(label) >= 0 and int(count) >= canvas_area * 0.6
    }
    split_line_art_knockouts = (
        opaque_canvas and len(visible_labels) == 2 and len(foundation_labels) == 1
    )
    if split_line_art_knockouts:
        error_tolerance = min(error_tolerance, 1.25)

    for label in visible_labels:
        mask = (labels == label).astype(np.uint8) * 255
        contours, raw_hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if raw_hierarchy is None:
            continue
        hierarchy = raw_hierarchy[0]
        for outer_index, contour in enumerate(contours):
            if int(hierarchy[outer_index][3]) >= 0:
                continue
            child_indices = _direct_children(hierarchy, outer_index)
            outer_area = abs(float(cv2.contourArea(contour)))
            x, y, box_width, box_height = (int(value) for value in cv2.boundingRect(contour))
            spans_canvas = (
                x <= 1 and y <= 1 and x + box_width >= width - 1 and y + box_height >= height - 1
            )
            if opaque_canvas and label in foundation_labels and not spans_canvas:
                suppressed_foundation_islands += 1
                continue
            if opaque_canvas and spans_canvas and outer_area >= width * height * 0.7:
                contour_indices = [outer_index]
                suppressed_foundation_holes += len(child_indices)
            else:
                contour_indices = [outer_index, *child_indices]
            fitted: list[tuple[str, dict[str, Any], Any]] = []
            for contour_index in contour_indices:
                source_contour = contours[contour_index]
                result = _fit_contour(
                    source_contour,
                    width=width,
                    height=height,
                    preset=preset,
                    error_tolerance=error_tolerance,
                )
                if result is None:
                    skipped += 1
                    continue
                path_data, metrics = result
                fitted.append((path_data, metrics, source_contour))
            if not fitted or fitted[0][2] is not contour:
                skipped += 1
                continue
            compound_area_error = _compound_area_error(fitted)
            if compound_area_error > 0.12:
                high_fidelity: list[tuple[str, dict[str, Any], Any]] = []
                for contour_index in contour_indices:
                    source_contour = contours[contour_index]
                    result = _fit_contour(
                        source_contour,
                        width=width,
                        height=height,
                        preset=preset,
                        error_tolerance=error_tolerance,
                        force_high_fidelity=True,
                    )
                    if result is None:
                        high_fidelity = []
                        break
                    path_data, contour_metrics = result
                    high_fidelity.append((path_data, contour_metrics, source_contour))
                if not high_fidelity:
                    raise ArtisanComplexityError(
                        "Artisan compound path could not be rebuilt at high fidelity."
                    )
                fitted = high_fidelity
                compound_area_error = _compound_area_error(fitted)
            if compound_area_error > 0.12:
                raise ArtisanComplexityError(
                    "Artisan compound path exceeds the area-preservation tolerance."
                )
            hole_area = sum(abs(float(cv2.contourArea(item[2]))) for item in fitted[1:])
            split_knockouts = (
                split_line_art_knockouts and label not in foundation_labels and len(fitted) > 1
            )
            primary_fitted = fitted[:1] if split_knockouts else fitted
            primary_shape_id = f"shape-{len(shapes) + 1:04d}"
            shapes.append(
                _shape_from_fitted(
                    shape_id=primary_shape_id,
                    label=label,
                    fitted=primary_fitted,
                    outer_contour=contour,
                    outer_area=outer_area,
                    area=max(0.0, outer_area - hole_area),
                    bbox=(x, y, box_width, box_height),
                    touches_canvas=(
                        x <= 1
                        or y <= 1
                        or x + box_width >= width - 1
                        or y + box_height >= height - 1
                    ),
                    hole_count=max(0, len(fitted) - 1),
                    compound_area_error=compound_area_error,
                )
            )
            if split_knockouts:
                knockout_label = next(iter(foundation_labels))
                for batch_start in range(1, len(fitted), 96):
                    batch = fitted[batch_start : batch_start + 96]
                    boxes = [cv2.boundingRect(item[2]) for item in batch]
                    batch_x = min(int(box[0]) for box in boxes)
                    batch_y = min(int(box[1]) for box in boxes)
                    batch_x1 = max(int(box[0] + box[2]) for box in boxes)
                    batch_y1 = max(int(box[1] + box[3]) for box in boxes)
                    batch_source_area = sum(float(item[1]["source_area"]) for item in batch)
                    batch_fitted_area = sum(float(item[1]["fitted_area"]) for item in batch)
                    batch_compound_error = abs(batch_fitted_area - batch_source_area) / max(
                        60.0, batch_source_area
                    )
                    shapes.append(
                        _shape_from_fitted(
                            shape_id=f"shape-{len(shapes) + 1:04d}",
                            label=knockout_label,
                            fitted=batch,
                            outer_contour=batch[0][2],
                            outer_area=batch_source_area,
                            area=batch_source_area,
                            bbox=(
                                batch_x,
                                batch_y,
                                batch_x1 - batch_x,
                                batch_y1 - batch_y,
                            ),
                            touches_canvas=False,
                            hole_count=0,
                            compound_area_error=batch_compound_error,
                            kind="knockout",
                            parent_shape_id=primary_shape_id,
                        )
                    )

    if not shapes:
        raise ArtisanComplexityError(
            "Artisan reconstruction removed every region; lower the cleanup threshold."
        )
    _assign_shape_structure(shapes, width, height)
    scene = ArtisanScene(width=width, height=height, shapes=tuple(shapes))
    metrics = _scene_metrics(
        scene,
        skipped_contours=skipped,
        suppressed_foundation_holes=suppressed_foundation_holes,
        suppressed_foundation_islands=suppressed_foundation_islands,
        error_tolerance=error_tolerance,
    )
    if metrics["subpaths"] > preset.max_subpaths or (
        metrics["anchors"] + metrics["control_points"] > preset.max_points
    ):
        raise ArtisanComplexityError(
            "Artisan reconstruction exceeds the configured subpath or point limit."
        )
    return scene, metrics


def trace_artisan_paths(
    labels: Any,
    preset: VectorPreset,
) -> tuple[dict[int, list[str]], dict[str, Any]]:
    """Compatibility adapter for callers that only need paths grouped by paint label."""

    scene, metrics = trace_artisan_scene(labels, preset)
    paths: dict[int, list[str]] = {}
    for shape in scene.shapes:
        paths.setdefault(shape.label, []).extend(shape.path_parts)
    return paths, metrics
