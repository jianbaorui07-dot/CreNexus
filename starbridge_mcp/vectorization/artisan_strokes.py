from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .curve_geometry import interior_angle as _interior_angle
from .curve_geometry import open_path as _open_path
from .curve_geometry import unit as _unit
from .presets import VectorPreset

Pixel = tuple[int, int]
Point = tuple[float, float]

_ORTHOGONAL_AND_DIAGONAL = (
    (-1, 0),
    (0, -1),
    (0, 1),
    (1, 0),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)


@dataclass(frozen=True)
class StrokeBatch:
    path_parts: tuple[str, ...]
    stroke_width: float
    bbox: tuple[int, int, int, int]
    representative_path: Any
    anchors: int
    raw_anchors: int
    control_points: int
    curve_segments: int
    line_segments: int
    corner_anchors: int
    smooth_anchors: int
    source_points: int
    length_px: float
    intent: str = "unclassified"
    preview_paths: tuple[Any, ...] = ()


def _zhang_suen_thinning(mask: Any) -> tuple[Any, int]:
    image = np.pad((mask > 0).astype(np.uint8), 1)
    rounds = 0
    while True:
        removed = 0
        for phase in (0, 1):
            north = image[:-2, 1:-1]
            north_east = image[:-2, 2:]
            east = image[1:-1, 2:]
            south_east = image[2:, 2:]
            south = image[2:, 1:-1]
            south_west = image[2:, :-2]
            west = image[1:-1, :-2]
            north_west = image[:-2, :-2]
            center = image[1:-1, 1:-1]
            neighbor_count = (
                north + north_east + east + south_east + south + south_west + west + north_west
            )
            transitions = (
                ((north == 0) & (north_east == 1)).astype(np.uint8)
                + ((north_east == 0) & (east == 1))
                + ((east == 0) & (south_east == 1))
                + ((south_east == 0) & (south == 1))
                + ((south == 0) & (south_west == 1))
                + ((south_west == 0) & (west == 1))
                + ((west == 0) & (north_west == 1))
                + ((north_west == 0) & (north == 1))
            )
            if phase == 0:
                topology = (north * east * south == 0) & (east * south * west == 0)
            else:
                topology = (north * east * west == 0) & (north * south * west == 0)
            removable = (
                (center == 1)
                & (neighbor_count >= 2)
                & (neighbor_count <= 6)
                & (transitions == 1)
                & topology
            )
            count = int(np.count_nonzero(removable))
            center[removable] = 0
            removed += count
        rounds += 1
        if removed == 0:
            return image[1:-1, 1:-1], rounds


def _pixel_neighbors(pixel: Pixel, pixels: set[Pixel]) -> list[Pixel]:
    y, x = pixel
    neighbors: list[Pixel] = []
    for delta_y, delta_x in _ORTHOGONAL_AND_DIAGONAL:
        candidate = (y + delta_y, x + delta_x)
        if candidate not in pixels:
            continue
        if delta_y and delta_x and ((y, x + delta_x) in pixels or (y + delta_y, x) in pixels):
            continue
        neighbors.append(candidate)
    return neighbors


def _edge_key(first: Pixel, second: Pixel) -> tuple[Pixel, Pixel]:
    return (first, second) if first < second else (second, first)


def _graph_paths(skeleton: Any) -> tuple[list[list[Point]], dict[str, int]]:
    pixels = {(int(y), int(x)) for y, x in zip(*np.nonzero(skeleton), strict=True)}
    neighbors = {pixel: _pixel_neighbors(pixel, pixels) for pixel in pixels}
    node_pixels = {pixel for pixel, values in neighbors.items() if len(values) != 2}
    unseen = set(node_pixels)
    components: list[list[Pixel]] = []
    node_id: dict[Pixel, int] = {}
    for seed in sorted(node_pixels):
        if seed not in unseen:
            continue
        unseen.remove(seed)
        stack = [seed]
        component = [seed]
        while stack:
            pixel = stack.pop()
            for candidate in sorted(neighbors[pixel]):
                if candidate in unseen and candidate in node_pixels:
                    unseen.remove(candidate)
                    stack.append(candidate)
                    component.append(candidate)
        component_id = len(components)
        components.append(component)
        for pixel in component:
            node_id[pixel] = component_id
    centers = [
        (
            sum(pixel[0] for pixel in component) / len(component),
            sum(pixel[1] for pixel in component) / len(component),
        )
        for component in components
    ]

    visited: set[tuple[Pixel, Pixel]] = set()
    paths: list[list[Point]] = []
    components_with_edges: set[int] = set()
    for component_id, component in enumerate(components):
        for pixel in sorted(component):
            for candidate in sorted(neighbors[pixel]):
                edge = _edge_key(pixel, candidate)
                if candidate in node_pixels or edge in visited:
                    continue
                components_with_edges.add(component_id)
                path: list[Point] = [centers[component_id]]
                previous = pixel
                current = candidate
                visited.add(edge)
                while current not in node_pixels:
                    path.append((float(current[0]), float(current[1])))
                    options = sorted(value for value in neighbors[current] if value != previous)
                    if not options:
                        break
                    following = options[0]
                    edge = _edge_key(current, following)
                    if edge in visited:
                        break
                    previous, current = current, following
                    visited.add(edge)
                if current in node_pixels:
                    path.append(centers[node_id[current]])
                if len(path) >= 2:
                    paths.append(path)

    for component_id, center in enumerate(centers):
        if component_id not in components_with_edges:
            paths.append([center, (center[0], center[1] + 0.05)])

    for start in sorted(pixels - node_pixels):
        for candidate in sorted(neighbors[start]):
            edge = _edge_key(start, candidate)
            if candidate in node_pixels or edge in visited:
                continue
            path = [(float(start[0]), float(start[1]))]
            previous = start
            current = candidate
            visited.add(edge)
            while current != start:
                path.append((float(current[0]), float(current[1])))
                options = sorted(value for value in neighbors[current] if value != previous)
                if not options:
                    break
                following = options[0]
                edge = _edge_key(current, following)
                if edge in visited and following != start:
                    break
                previous, current = current, following
                visited.add(edge)
            if len(path) >= 3:
                path.append(path[0])
                paths.append(path)
    return paths, {
        "skeleton_pixels": len(pixels),
        "junction_pixels": len(node_pixels),
        "junction_clusters": len(components),
    }


def _distance_width(path: list[Point], distance: Any, height: int, width: int) -> float:
    values: list[float] = []
    for y, x in path:
        pixel_y = max(0, min(height - 1, int(round(y))))
        pixel_x = max(0, min(width - 1, int(round(x))))
        values.append(float(distance[pixel_y, pixel_x]) * 2.0)
    raw_width = float(np.median(values)) - 0.65 if values else 1.0
    return max(1.0, min(7.0, round(raw_width * 2.0) / 2.0))


def _path_extent(path: list[Point]) -> float:
    return sum(math.dist(path[index - 1], path[index]) for index in range(1, len(path)))


def _classify_path_intent(points: list[Point], *, closed: bool = False) -> str:
    """Classify editable strokes by geometry without claiming content recognition."""

    extent = _path_extent(points)
    if closed and len(points) >= 4:
        return "ornament"
    if extent <= 4.0:
        return "micro-detail"
    turn_energy = sum(
        abs(180.0 - _interior_angle(points[index - 1], points[index], points[index + 1]))
        for index in range(1, len(points) - 1)
    )
    turn_density = turn_energy / max(1.0, extent)
    if extent >= 48.0 and turn_density <= 10.0:
        return "flow-contour"
    if extent >= 16.0 or turn_density >= 10.0:
        return "ornament"
    return "detail"


def _intent_profile(
    intent: str,
    base_epsilon: float,
    preset: VectorPreset,
) -> tuple[float, float]:
    epsilon_scale, smoothing_limit = {
        "flow-contour": (1.4, 0.72),
        "ornament": (1.08, 0.64),
        "detail": (1.06, 0.56),
        "micro-detail": (1.0, 0.44),
    }.get(intent, (1.0, 0.72))
    return (
        max(0.65, min(2.25, base_epsilon * epsilon_scale)),
        min(smoothing_limit, preset.curve_smoothing),
    )


def _draw_entry(rendered: Any, entry: dict[str, Any]) -> None:
    render_points = np.rint(np.asarray(entry["sampled_points"], dtype=np.float32)).astype(np.int32)
    cv2.polylines(
        rendered,
        [render_points.reshape((-1, 1, 2))],
        False,
        1,
        max(1, round(float(entry["stroke_width"]))),
        cv2.LINE_8,
    )


def _micro_path_novelty(entry: dict[str, Any], rendered: Any, binary: Any) -> float:
    points = np.asarray(entry["sampled_points"], dtype=np.float32)
    radius = max(2, math.ceil(float(entry["stroke_width"]) / 2.0) + 1)
    height, width = binary.shape
    minimum_x = max(0, math.floor(float(points[:, 0].min())) - radius)
    maximum_x = min(width, math.ceil(float(points[:, 0].max())) + radius + 1)
    minimum_y = max(0, math.floor(float(points[:, 1].min())) - radius)
    maximum_y = min(height, math.ceil(float(points[:, 1].max())) + radius + 1)
    if minimum_x >= maximum_x or minimum_y >= maximum_y:
        return 0.0
    local = np.zeros((maximum_y - minimum_y, maximum_x - minimum_x), dtype=np.uint8)
    shifted = np.rint(points - np.asarray([minimum_x, minimum_y], dtype=np.float32)).astype(
        np.int32
    )
    cv2.polylines(
        local,
        [shifted.reshape((-1, 1, 2))],
        False,
        1,
        max(1, round(float(entry["stroke_width"]))),
        cv2.LINE_8,
    )
    source_ink = local.astype(bool) & binary[minimum_y:maximum_y, minimum_x:maximum_x].astype(bool)
    source_pixels = int(np.count_nonzero(source_ink))
    if not source_pixels:
        return 0.0
    covered = rendered[minimum_y:maximum_y, minimum_x:maximum_x].astype(bool)
    novel_pixels = int(np.count_nonzero(source_ink & ~covered))
    return novel_pixels / source_pixels


def _endpoint_direction(path: list[Point], endpoint: int) -> tuple[float, float]:
    origin = path[0] if endpoint == 0 else path[-1]
    candidates = path[1:] if endpoint == 0 else reversed(path[:-1])
    fallback = (0.0, 0.0)
    for candidate in candidates:
        vector = (candidate[0] - origin[0], candidate[1] - origin[1])
        fallback = _unit(*vector)
        if math.hypot(*vector) >= 2.0:
            return fallback
    return fallback


def _endpoint_width(
    path: list[Point],
    endpoint: int,
    distance: Any,
    height: int,
    width: int,
) -> float:
    candidates = path[1:6] if endpoint == 0 else list(reversed(path[:-1]))[:5]
    if not candidates:
        candidates = [path[0 if endpoint == 0 else -1]]
    values = []
    for y, x in candidates:
        pixel_y = max(0, min(height - 1, int(round(y))))
        pixel_x = max(0, min(width - 1, int(round(x))))
        values.append(float(distance[pixel_y, pixel_x]) * 2.0 - 0.65)
    return max(1.0, float(np.median(values)))


def _stitch_paths(
    paths: list[list[Point]],
    distance: Any,
    height: int,
    width: int,
    *,
    maximum_deviation_degrees: float = 38.0,
    maximum_width_difference: float = 1.5,
) -> tuple[list[list[Point]], dict[str, Any]]:
    endpoint_data: dict[
        tuple[float, float],
        list[tuple[tuple[int, int], tuple[float, float], float, float]],
    ] = {}
    for path_index, path in enumerate(paths):
        extent = _path_extent(path)
        if len(path) < 2 or extent < 1.0 or path[0] == path[-1]:
            continue
        for endpoint in (0, 1):
            point = path[0] if endpoint == 0 else path[-1]
            key = (round(point[0], 6), round(point[1], 6))
            endpoint_data.setdefault(key, []).append(
                (
                    (path_index, endpoint),
                    _endpoint_direction(path, endpoint),
                    _endpoint_width(path, endpoint, distance, height, width),
                    extent,
                )
            )

    connections: dict[tuple[int, int], tuple[int, int]] = {}
    used_deviations: list[float] = []
    used_width_differences: list[float] = []
    junctions_considered = 0
    eligible_pairs = 0
    for entries in endpoint_data.values():
        if len(entries) < 2:
            continue
        junctions_considered += 1
        candidates: list[tuple[float, float, float, tuple[int, int], tuple[int, int]]] = []
        for first_index, first in enumerate(entries[:-1]):
            for second in entries[first_index + 1 :]:
                first_endpoint, first_direction, first_width, first_extent = first
                second_endpoint, second_direction, second_width, second_extent = second
                if first_endpoint[0] == second_endpoint[0]:
                    continue
                dot = (
                    first_direction[0] * second_direction[0]
                    + first_direction[1] * second_direction[1]
                )
                deviation = math.degrees(math.acos(max(-1.0, min(1.0, -dot))))
                width_difference = abs(first_width - second_width)
                if (
                    deviation <= maximum_deviation_degrees
                    and width_difference <= maximum_width_difference
                ):
                    eligible_pairs += 1
                    candidates.append(
                        (
                            deviation,
                            width_difference,
                            -min(first_extent, second_extent),
                            first_endpoint,
                            second_endpoint,
                        )
                    )
        used: set[tuple[int, int]] = set()
        for deviation, width_difference, _, first_endpoint, second_endpoint in sorted(candidates):
            if first_endpoint in used or second_endpoint in used:
                continue
            connections[first_endpoint] = second_endpoint
            connections[second_endpoint] = first_endpoint
            used.add(first_endpoint)
            used.add(second_endpoint)
            used_deviations.append(deviation)
            used_width_differences.append(width_difference)

    starts: list[tuple[int, int]] = []
    for path_index in range(len(paths)):
        if (path_index, 0) not in connections:
            starts.append((path_index, 0))
        elif (path_index, 1) not in connections:
            starts.append((path_index, 1))
    starts.extend((path_index, 0) for path_index in range(len(paths)))

    stitched: list[list[Point]] = []
    visited: set[int] = set()
    for path_index, entry_endpoint in starts:
        if path_index in visited:
            continue
        trail: list[Point] = []
        current_index = path_index
        current_endpoint = entry_endpoint
        while current_index not in visited:
            path = paths[current_index]
            oriented = path if current_endpoint == 0 else list(reversed(path))
            if trail and trail[-1] == oriented[0]:
                trail.extend(oriented[1:])
            else:
                trail.extend(oriented)
            visited.add(current_index)
            exit_endpoint = (current_index, 1 - current_endpoint)
            continuation = connections.get(exit_endpoint)
            if continuation is None or continuation[0] in visited:
                break
            current_index, current_endpoint = continuation
        if len(trail) >= 2:
            stitched.append(trail)

    return stitched, {
        "continuation_junctions_considered": junctions_considered,
        "continuation_eligible_pairs": eligible_pairs,
        "continuation_pairs": len(connections) // 2,
        "continuation_maximum_deviation_degrees": round(max(used_deviations, default=0.0), 4),
        "continuation_mean_deviation_degrees": round(
            sum(used_deviations) / len(used_deviations) if used_deviations else 0.0,
            4,
        ),
        "continuation_maximum_width_difference_px": round(
            max(used_width_differences, default=0.0), 4
        ),
        "continuation_deviation_limit_degrees": maximum_deviation_degrees,
        "continuation_width_difference_limit_px": maximum_width_difference,
    }


def _bbox(points: list[Point], width: int, height: int) -> tuple[int, int, int, int]:
    minimum_x = max(0, math.floor(min(point[0] for point in points)))
    minimum_y = max(0, math.floor(min(point[1] for point in points)))
    maximum_x = min(width, math.ceil(max(point[0] for point in points)))
    maximum_y = min(height, math.ceil(max(point[1] for point in points)))
    return minimum_x, minimum_y, max(1, maximum_x - minimum_x), max(1, maximum_y - minimum_y)


def _trace_paths(
    paths: list[list[Point]],
    binary: Any,
    distance: Any,
    preset: VectorPreset,
    batch_limit: int,
    *,
    semantic_profiles: bool = False,
) -> tuple[tuple[StrokeBatch, ...], dict[str, Any]]:
    height, width = binary.shape
    rendered = np.zeros_like(binary)
    base_epsilon = max(0.8, min(1.5, preset.simplify_ratio * 90.0))
    entries: list[dict[str, Any]] = []
    raw_anchor_count = 0
    for raw_path in paths:
        coordinates = np.asarray(
            [(x + 0.5, y + 0.5) for y, x in raw_path], dtype=np.float32
        ).reshape((-1, 1, 2))
        preview_approximation = cv2.approxPolyDP(coordinates, base_epsilon, False).reshape((-1, 2))
        preview_points = [(float(x), float(y)) for x, y in preview_approximation]
        if len(preview_points) < 2:
            continue
        closed = raw_path[0] == raw_path[-1]
        intent = (
            _classify_path_intent(preview_points, closed=closed)
            if semantic_profiles
            else "unclassified"
        )
        simplify_epsilon, smoothing = (
            _intent_profile(intent, base_epsilon, preset)
            if semantic_profiles
            else (base_epsilon, min(0.72, preset.curve_smoothing))
        )
        approximation = cv2.approxPolyDP(coordinates, simplify_epsilon, False).reshape((-1, 2))
        points = [(float(x), float(y)) for x, y in approximation]
        if len(points) < 2:
            continue
        path_data, path_metrics = _open_path(
            points,
            corner_angle=preset.corner_angle,
            smoothing=smoothing,
        )
        sampled_points = path_metrics.pop("sampled_points")
        stroke_width = _distance_width(raw_path, distance, height, width)
        raw_anchor_count += len(raw_path)
        entries.append(
            {
                "path_data": path_data,
                "metrics": path_metrics,
                "sampled_points": sampled_points,
                "raw_anchors": len(raw_path),
                "source_points": len(raw_path),
                "length_px": _path_extent(points),
                "stroke_width": stroke_width,
                "intent": intent,
                "simplify_epsilon": simplify_epsilon,
            }
        )

    selected_entries: list[dict[str, Any]] = []
    pruned_entries: list[dict[str, Any]] = []
    if semantic_profiles:
        for entry in entries:
            if entry["intent"] != "micro-detail":
                selected_entries.append(entry)
                _draw_entry(rendered, entry)
        for entry in (item for item in entries if item["intent"] == "micro-detail"):
            if _micro_path_novelty(entry, rendered, binary) <= 0.0:
                pruned_entries.append(entry)
                continue
            selected_entries.append(entry)
            _draw_entry(rendered, entry)
    else:
        selected_entries = entries
        for entry in selected_entries:
            _draw_entry(rendered, entry)

    grouped: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for entry in selected_entries:
        group_intent = str(entry["intent"]) if semantic_profiles else "unclassified"
        grouped.setdefault((group_intent, float(entry["stroke_width"])), []).append(entry)

    original = binary.astype(bool)
    predicted = rendered.astype(bool)
    intersection = int(np.count_nonzero(original & predicted))
    original_count = int(np.count_nonzero(original))
    predicted_count = int(np.count_nonzero(predicted))
    precision = intersection / predicted_count if predicted_count else 0.0
    recall = intersection / original_count if original_count else 0.0
    dice = (
        2.0 * intersection / (original_count + predicted_count)
        if original_count + predicted_count
        else 0.0
    )

    batches: list[StrokeBatch] = []
    for intent, stroke_width in sorted(grouped):
        group_entries = grouped[(intent, stroke_width)]
        for start in range(0, len(group_entries), batch_limit):
            batch = group_entries[start : start + batch_limit]
            all_points = [point for entry in batch for point in entry["sampled_points"]]
            box = _bbox(all_points, width, height)
            representative = np.asarray(batch[0]["sampled_points"], dtype=np.float32).reshape(
                (-1, 1, 2)
            )
            batches.append(
                StrokeBatch(
                    path_parts=tuple(str(entry["path_data"]) for entry in batch),
                    stroke_width=stroke_width,
                    bbox=box,
                    representative_path=representative,
                    anchors=sum(int(entry["metrics"]["anchors"]) for entry in batch),
                    raw_anchors=sum(int(entry["raw_anchors"]) for entry in batch),
                    control_points=sum(int(entry["metrics"]["control_points"]) for entry in batch),
                    curve_segments=sum(int(entry["metrics"]["curve_segments"]) for entry in batch),
                    line_segments=sum(int(entry["metrics"]["line_segments"]) for entry in batch),
                    corner_anchors=sum(int(entry["metrics"]["corner_anchors"]) for entry in batch),
                    smooth_anchors=sum(int(entry["metrics"]["smooth_anchors"]) for entry in batch),
                    source_points=sum(int(entry["source_points"]) for entry in batch),
                    length_px=sum(float(entry["length_px"]) for entry in batch),
                    intent=intent,
                    preview_paths=tuple(
                        np.rint(np.asarray(entry["sampled_points"], dtype=np.float32))
                        .astype(np.int32)
                        .reshape((-1, 1, 2))
                        for entry in batch
                    ),
                )
            )
    intent_counts = {
        intent: sum(entry["intent"] == intent for entry in selected_entries)
        for intent in ("flow-contour", "ornament", "detail", "micro-detail")
    }
    return tuple(batches), {
        "subpaths": sum(len(batch.path_parts) for batch in batches),
        "batches": len(batches),
        "raw_anchors": raw_anchor_count,
        "anchors": sum(batch.anchors for batch in batches),
        "control_points": sum(batch.control_points for batch in batches),
        "precision": precision,
        "recall": recall,
        "dice": dice,
        "simplify_epsilon": base_epsilon,
        "min_stroke_width": min((batch.stroke_width for batch in batches), default=0.0),
        "max_stroke_width": max((batch.stroke_width for batch in batches), default=0.0),
        "semantic_profiles": semantic_profiles,
        "semantic_intent_counts": intent_counts,
        "semantic_pruned_micro_paths": len(pruned_entries),
        "semantic_pruned_micro_anchors": sum(
            int(entry["metrics"]["anchors"]) for entry in pruned_entries
        ),
        "semantic_minimum_epsilon": round(
            min((float(entry["simplify_epsilon"]) for entry in selected_entries), default=0.0), 4
        ),
        "semantic_maximum_epsilon": round(
            max((float(entry["simplify_epsilon"]) for entry in selected_entries), default=0.0), 4
        ),
    }


def _semantic_rejection_reasons(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    continuation_used: bool,
) -> list[str]:
    reasons: list[str] = []
    baseline_points = int(baseline["anchors"]) + int(baseline["control_points"])
    candidate_points = int(candidate["anchors"]) + int(candidate["control_points"])
    path_reduction = (
        max(0.0, 1.0 - int(candidate["subpaths"]) / int(baseline["subpaths"]))
        if baseline["subpaths"]
        else 0.0
    )
    anchor_reduction = (
        max(0.0, 1.0 - int(candidate["anchors"]) / int(baseline["anchors"]))
        if baseline["anchors"]
        else 0.0
    )
    point_reduction = max(0.0, 1.0 - candidate_points / baseline_points) if baseline_points else 0.0
    intent_counts = candidate.get("semantic_intent_counts", {})
    populated_intents = sum(int(value) > 0 for value in intent_counts.values())
    if not continuation_used:
        reasons.append("continuation_not_selected")
    if populated_intents < 2:
        reasons.append("insufficient_geometric_intent_diversity")
    if path_reduction < 0.03:
        reasons.append("semantic_path_reduction_below_3_percent")
    if anchor_reduction < 0.03:
        reasons.append("semantic_anchor_reduction_below_3_percent")
    if point_reduction < 0.03:
        reasons.append("semantic_point_reduction_below_3_percent")
    if int(candidate["batches"]) > int(baseline["batches"]):
        reasons.append("semantic_edit_batch_count_increased")
    if float(candidate["precision"]) < float(baseline["precision"]) - 0.006:
        reasons.append("semantic_precision_regression_over_0_006")
    if float(candidate["recall"]) < float(baseline["recall"]) - 0.01:
        reasons.append("semantic_recall_regression_over_0_01")
    if float(candidate["dice"]) < float(baseline["dice"]) - 0.006:
        reasons.append("semantic_dice_regression_over_0_006")
    return reasons


def trace_centerline_batches(
    ink_mask: Any,
    preset: VectorPreset,
    *,
    batch_limit: int = 96,
) -> tuple[tuple[StrokeBatch, ...], dict[str, Any]]:
    height, width = ink_mask.shape
    binary = (ink_mask > 0).astype(np.uint8)
    skeleton, thinning_rounds = _zhang_suen_thinning(binary)
    raw_paths, graph_metrics = _graph_paths(skeleton)
    distance = cv2.distanceTransform(binary * 255, cv2.DIST_L2, 5)
    continued_paths, continuation_metrics = _stitch_paths(
        raw_paths,
        distance,
        height,
        width,
    )
    baseline_batches, baseline = _trace_paths(
        raw_paths,
        binary,
        distance,
        preset,
        batch_limit,
    )
    continued_batches, continued = _trace_paths(
        continued_paths,
        binary,
        distance,
        preset,
        batch_limit,
    )
    semantic_batches, semantic = _trace_paths(
        continued_paths,
        binary,
        distance,
        preset,
        batch_limit,
        semantic_profiles=True,
    )
    baseline_lengths = [_path_extent(path) for path in raw_paths]
    continued_lengths = [_path_extent(path) for path in continued_paths]
    baseline_mean_length = (
        sum(baseline_lengths) / len(baseline_lengths) if baseline_lengths else 0.0
    )
    continued_mean_length = (
        sum(continued_lengths) / len(continued_lengths) if continued_lengths else 0.0
    )
    mean_length_gain = (
        max(0.0, continued_mean_length / baseline_mean_length - 1.0)
        if baseline_mean_length
        else 0.0
    )
    baseline_total_length = sum(baseline_lengths)
    continued_total_length = sum(continued_lengths)
    length_preservation = (
        continued_total_length / baseline_total_length if baseline_total_length else 1.0
    )
    path_reduction = (
        max(0.0, 1.0 - continued["subpaths"] / baseline["subpaths"])
        if baseline["subpaths"]
        else 0.0
    )
    anchor_reduction = (
        max(0.0, 1.0 - continued["anchors"] / baseline["anchors"]) if baseline["anchors"] else 0.0
    )
    baseline_points = int(baseline["anchors"]) + int(baseline["control_points"])
    continued_points = int(continued["anchors"]) + int(continued["control_points"])
    point_reduction = max(0.0, 1.0 - continued_points / baseline_points) if baseline_points else 0.0
    batch_reduction = (
        max(0.0, 1.0 - continued["batches"] / baseline["batches"]) if baseline["batches"] else 0.0
    )
    rejection_reasons: list[str] = []
    if path_reduction < 0.15:
        rejection_reasons.append("path_reduction_below_15_percent")
    if anchor_reduction < 0.03:
        rejection_reasons.append("anchor_reduction_below_3_percent")
    if continued["batches"] > baseline["batches"]:
        rejection_reasons.append("edit_batch_count_increased")
    if not math.isclose(length_preservation, 1.0, rel_tol=0.0, abs_tol=0.0001):
        rejection_reasons.append("skeleton_length_not_preserved")
    if continued["precision"] < baseline["precision"] - 0.01:
        rejection_reasons.append("precision_regression_over_0_01")
    if continued["recall"] < baseline["recall"] - 0.015:
        rejection_reasons.append("recall_regression_over_0_015")
    if continued["dice"] < baseline["dice"] - 0.01:
        rejection_reasons.append("dice_regression_over_0_01")
    continuation_used = not rejection_reasons
    continuation_selected = continued if continuation_used else baseline
    continuation_selected_batches = continued_batches if continuation_used else baseline_batches
    semantic_rejection_reasons = _semantic_rejection_reasons(
        continued,
        semantic,
        continuation_used=continuation_used,
    )
    semantic_used = not semantic_rejection_reasons
    batches = semantic_batches if semantic_used else continuation_selected_batches
    selected = semantic if semantic_used else continuation_selected
    semantic_baseline_points = int(continued["anchors"]) + int(continued["control_points"])
    semantic_candidate_points = int(semantic["anchors"]) + int(semantic["control_points"])
    semantic_path_reduction = (
        max(0.0, 1.0 - semantic["subpaths"] / continued["subpaths"])
        if continued["subpaths"]
        else 0.0
    )
    semantic_anchor_reduction = (
        max(0.0, 1.0 - semantic["anchors"] / continued["anchors"]) if continued["anchors"] else 0.0
    )
    semantic_point_reduction = (
        max(0.0, 1.0 - semantic_candidate_points / semantic_baseline_points)
        if semantic_baseline_points
        else 0.0
    )
    semantic_batch_reduction = (
        max(0.0, 1.0 - semantic["batches"] / continued["batches"]) if continued["batches"] else 0.0
    )
    return batches, {
        **graph_metrics,
        **continuation_metrics,
        "thinning_rounds": thinning_rounds,
        "centerline_raw_paths": len(raw_paths),
        "centerline_subpaths": selected["subpaths"],
        "centerline_batches": selected["batches"],
        "centerline_raw_anchors": selected["raw_anchors"],
        "centerline_anchors": selected["anchors"],
        "centerline_simplify_epsilon": round(float(selected["simplify_epsilon"]), 4),
        "centerline_precision": round(float(selected["precision"]), 6),
        "centerline_recall": round(float(selected["recall"]), 6),
        "centerline_dice": round(float(selected["dice"]), 6),
        "centerline_min_stroke_width": selected["min_stroke_width"],
        "centerline_max_stroke_width": selected["max_stroke_width"],
        "continuation_candidate_used": continuation_used,
        "continuation_rejection_reasons": rejection_reasons,
        "continuation_baseline_subpaths": baseline["subpaths"],
        "continuation_candidate_subpaths": continued["subpaths"],
        "continuation_path_reduction_ratio": round(path_reduction, 4),
        "continuation_baseline_anchors": baseline["anchors"],
        "continuation_candidate_anchors": continued["anchors"],
        "continuation_anchor_reduction_ratio": round(anchor_reduction, 4),
        "continuation_baseline_points": baseline_points,
        "continuation_candidate_points": continued_points,
        "continuation_point_reduction_ratio": round(point_reduction, 4),
        "continuation_baseline_batches": baseline["batches"],
        "continuation_candidate_batches": continued["batches"],
        "continuation_batch_reduction_ratio": round(batch_reduction, 4),
        "continuation_baseline_mean_path_length_px": round(baseline_mean_length, 4),
        "continuation_candidate_mean_path_length_px": round(continued_mean_length, 4),
        "continuation_mean_path_length_gain_ratio": round(mean_length_gain, 4),
        "continuation_length_preservation_ratio": round(length_preservation, 6),
        "continuation_baseline_maximum_path_length_px": round(
            max(baseline_lengths, default=0.0), 4
        ),
        "continuation_candidate_maximum_path_length_px": round(
            max(continued_lengths, default=0.0), 4
        ),
        "continuation_precision_delta": round(
            float(continued["precision"] - baseline["precision"]), 6
        ),
        "continuation_recall_delta": round(float(continued["recall"] - baseline["recall"]), 6),
        "continuation_dice_delta": round(float(continued["dice"] - baseline["dice"]), 6),
        "semantic_candidate_used": semantic_used,
        "semantic_rejection_reasons": semantic_rejection_reasons,
        "semantic_intent_counts": semantic["semantic_intent_counts"],
        "semantic_pruned_micro_paths": semantic["semantic_pruned_micro_paths"],
        "semantic_pruned_micro_anchors": semantic["semantic_pruned_micro_anchors"],
        "semantic_baseline_subpaths": continued["subpaths"],
        "semantic_candidate_subpaths": semantic["subpaths"],
        "semantic_path_reduction_ratio": round(semantic_path_reduction, 4),
        "semantic_baseline_anchors": continued["anchors"],
        "semantic_candidate_anchors": semantic["anchors"],
        "semantic_anchor_reduction_ratio": round(semantic_anchor_reduction, 4),
        "semantic_baseline_points": semantic_baseline_points,
        "semantic_candidate_points": semantic_candidate_points,
        "semantic_point_reduction_ratio": round(semantic_point_reduction, 4),
        "semantic_baseline_batches": continued["batches"],
        "semantic_candidate_batches": semantic["batches"],
        "semantic_batch_reduction_ratio": round(semantic_batch_reduction, 4),
        "semantic_precision_delta": round(float(semantic["precision"] - continued["precision"]), 6),
        "semantic_recall_delta": round(float(semantic["recall"] - continued["recall"]), 6),
        "semantic_dice_delta": round(float(semantic["dice"] - continued["dice"]), 6),
        "semantic_minimum_epsilon": semantic["semantic_minimum_epsilon"],
        "semantic_maximum_epsilon": semantic["semantic_maximum_epsilon"],
        "semantic_quality_thresholds": {
            "minimum_path_reduction_ratio": 0.03,
            "minimum_anchor_reduction_ratio": 0.03,
            "minimum_point_reduction_ratio": 0.03,
            "maximum_precision_regression": 0.006,
            "maximum_recall_regression": 0.01,
            "maximum_dice_regression": 0.006,
        },
    }
