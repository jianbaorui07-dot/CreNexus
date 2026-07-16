from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .presets import VectorPreset


class ArtisanComplexityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    smooth: bool
    tangent_x: float
    tangent_y: float


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
        if current.smooth or following.smooth:
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


def trace_artisan_paths(
    labels: Any,
    preset: VectorPreset,
) -> tuple[dict[int, list[str]], dict[str, int | float]]:
    height, width = labels.shape
    paths: dict[int, list[str]] = {}
    subpaths = 0
    anchors = 0
    baseline_anchors = 0
    controls = 0
    curves = 0
    lines = 0
    corners = 0
    smooth_anchors = 0
    skipped = 0
    source_contour_points = 0
    contour_error_total = 0.0
    contour_error_samples = 0
    maximum_contour_error = 0.0
    error_tolerance = max(5.0, max(width, height) * 0.004)
    adapted_contours = 0

    for label in [int(value) for value in np.unique(labels) if value >= 0]:
        mask = (labels == label).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        label_paths: list[str] = []
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                skipped += 1
                continue
            source_contour_points += len(contour)
            baseline_epsilon = max(0.25, perimeter * 0.004)
            baseline_contour = cv2.approxPolyDP(contour, baseline_epsilon, True)
            baseline_anchors += max(3, len(baseline_contour))
            artisan_epsilon = max(0.6, perimeter * preset.simplify_ratio)
            smoothing = preset.curve_smoothing
            path_data = ""
            metrics: dict[str, Any] = {}
            error_total = 0.0
            error_samples = 0
            contour_maximum_error = 0.0
            for attempt in range(6):
                artisan_contour = cv2.approxPolyDP(contour, artisan_epsilon, True)
                points = _deduplicated_points(artisan_contour, width, height)
                if len(points) < 3:
                    break
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
                if contour_maximum_error <= error_tolerance:
                    if attempt:
                        adapted_contours += 1
                    break
                if artisan_epsilon > baseline_epsilon:
                    artisan_epsilon = max(baseline_epsilon, artisan_epsilon * 0.62)
                else:
                    smoothing *= 0.62
            if not path_data or not metrics:
                skipped += 1
                continue
            contour_error_total += error_total
            contour_error_samples += error_samples
            maximum_contour_error = max(maximum_contour_error, contour_maximum_error)
            subpaths += 1
            anchors += metrics["anchors"]
            controls += metrics["control_points"]
            curves += metrics["curve_segments"]
            lines += metrics["line_segments"]
            corners += metrics["corners"]
            smooth_anchors += metrics["smooth_anchors"]
            if subpaths > preset.max_subpaths or anchors + controls > preset.max_points:
                raise ArtisanComplexityError(
                    "Artisan reconstruction exceeds the configured subpath or point limit."
                )
            label_paths.append(path_data)
        if label_paths:
            paths[label] = label_paths

    if not paths:
        raise ArtisanComplexityError(
            "Artisan reconstruction removed every region; lower the cleanup threshold."
        )
    reduction = 0.0
    if baseline_anchors:
        reduction = max(0.0, 1.0 - anchors / baseline_anchors)
    return paths, {
        "path_objects": len(paths),
        "subpaths": subpaths,
        "anchors": anchors,
        "baseline_polygon_anchors": baseline_anchors,
        "anchor_reduction_ratio": round(reduction, 4),
        "control_points": controls,
        "curve_segments": curves,
        "line_segments": lines,
        "corner_anchors": corners,
        "smooth_anchors": smooth_anchors,
        "source_contour_points": source_contour_points,
        "mean_contour_error_px": round(
            contour_error_total / contour_error_samples if contour_error_samples else 0.0,
            4,
        ),
        "maximum_contour_error_px": round(maximum_contour_error, 4),
        "curve_error_tolerance_px": round(error_tolerance, 4),
        "adapted_contours": adapted_contours,
        "skipped_contours": skipped,
    }
