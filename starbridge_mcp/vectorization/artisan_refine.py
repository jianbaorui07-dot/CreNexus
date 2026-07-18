from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .artisan_brief import ArtisanBriefError, load_style_profile
from .artisan_edit import (
    INTENT_SELECTOR,
    SHAPE_ID,
    EditIndexError,
    build_edit_index,
    load_edit_index,
)
from .curve_geometry import open_path
from .svg_verify import SvgArtifactError, _tokenize_path, verify_svg_artifact

Point = tuple[float, float]
MAX_PATCH_TARGETS = 4096
PATH_ID = re.compile(r'<path\s+id="(shape-[0-9]{4,})"')
PATH_DATA = re.compile(r'\bd="([^"]*)"')


class ArtisanRefineError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _path_lines(svg_text: str) -> dict[str, str]:
    lines: dict[str, str] = {}
    for line in svg_text.splitlines(keepends=True):
        match = PATH_ID.search(line)
        if match:
            lines[match.group(1)] = line
    return lines


def _parse_open_subpaths(path_data: str) -> list[tuple[Point, list[tuple[str, tuple[Point, ...]]]]]:
    tokens = _tokenize_path(path_data)
    index = 0
    subpaths: list[tuple[Point, list[tuple[str, tuple[Point, ...]]]]] = []

    def pair() -> Point:
        nonlocal index
        point = (float(tokens[index]), float(tokens[index + 1]))
        index += 2
        return point

    while index < len(tokens):
        if tokens[index] != "M":
            raise ArtisanRefineError("unsupported_path", "Refinement requires absolute open paths.")
        index += 1
        start = pair()
        segments: list[tuple[str, tuple[Point, ...]]] = []
        while index < len(tokens) and tokens[index] != "M":
            command = tokens[index]
            index += 1
            if command == "L":
                segments.append((command, (pair(),)))
            elif command == "C":
                segments.append((command, (pair(), pair(), pair())))
            else:
                raise ArtisanRefineError(
                    "unsupported_path", "Refinement supports M, L, and C centerline commands only."
                )
        subpaths.append((start, segments))
    return subpaths


def _anchors(subpath: tuple[Point, list[tuple[str, tuple[Point, ...]]]]) -> list[Point]:
    start, segments = subpath
    return [start, *(points[-1] for _, points in segments)]


def _sample_subpath(
    subpath: tuple[Point, list[tuple[str, tuple[Point, ...]]]],
    *,
    curve_steps: int = 8,
) -> list[Point]:
    start, segments = subpath
    sampled = [start]
    current = start
    for command, points in segments:
        if command == "L":
            sampled.append(points[0])
            current = points[0]
            continue
        control_1, control_2, following = points
        for sample_index in range(1, curve_steps + 1):
            t = sample_index / curve_steps
            inverse = 1.0 - t
            sampled.append(
                (
                    inverse**3 * current[0]
                    + 3 * inverse**2 * t * control_1[0]
                    + 3 * inverse * t**2 * control_2[0]
                    + t**3 * following[0],
                    inverse**3 * current[1]
                    + 3 * inverse**2 * t * control_1[1]
                    + 3 * inverse * t**2 * control_2[1]
                    + t**3 * following[1],
                )
            )
        current = following
    return sampled


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    squared = delta_x * delta_x + delta_y * delta_y
    if squared == 0:
        return math.dist(point, start)
    ratio = ((point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y) / squared
    ratio = max(0.0, min(1.0, ratio))
    projection = (start[0] + ratio * delta_x, start[1] + ratio * delta_y)
    return math.dist(point, projection)


def _rdp(points: list[Point], epsilon: float) -> list[Point]:
    if len(points) <= 2:
        return points
    maximum = -1.0
    split_index = 0
    for index, point in enumerate(points[1:-1], start=1):
        distance = _point_segment_distance(point, points[0], points[-1])
        if distance > maximum:
            maximum = distance
            split_index = index
    if maximum > epsilon:
        left = _rdp(points[: split_index + 1], epsilon)
        right = _rdp(points[split_index:], epsilon)
        return [*left[:-1], *right]
    return [points[0], points[-1]]


def _nearest_polyline_distance(point: Point, polyline: list[Point]) -> float:
    return min(
        _point_segment_distance(point, start, end) for start, end in zip(polyline, polyline[1:])
    )


def _deviation(first: list[Point], second: list[Point]) -> tuple[float, float]:
    distances = [*(_nearest_polyline_distance(point, second) for point in first)]
    distances.extend(_nearest_polyline_distance(point, first) for point in second)
    return sum(distances) / len(distances), max(distances, default=0.0)


def _orientation(first: Point, second: Point, third: Point) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )


def _segments_intersect(first: Point, second: Point, third: Point, fourth: Point) -> bool:
    first_side = _orientation(first, second, third)
    second_side = _orientation(first, second, fourth)
    third_side = _orientation(third, fourth, first)
    fourth_side = _orientation(third, fourth, second)
    tolerance = 1e-8
    return (
        (first_side > tolerance and second_side < -tolerance)
        or (first_side < -tolerance and second_side > tolerance)
    ) and (
        (third_side > tolerance and fourth_side < -tolerance)
        or (third_side < -tolerance and fourth_side > tolerance)
    )


def _self_intersections(points: list[Point]) -> int:
    segments = list(zip(points, points[1:]))
    count = 0
    for first_index, (first, second) in enumerate(segments):
        for second_index in range(first_index + 2, len(segments)):
            if second_index == first_index + 1:
                continue
            third, fourth = segments[second_index]
            if _segments_intersect(first, second, third, fourth):
                count += 1
    return count


def _backtracking(points: list[Point]) -> int:
    count = 0
    for previous, current, following in zip(points, points[1:], points[2:]):
        first = (current[0] - previous[0], current[1] - previous[1])
        second = (following[0] - current[0], following[1] - current[1])
        lengths = math.hypot(*first) * math.hypot(*second)
        if lengths and (first[0] * second[0] + first[1] * second[1]) / lengths < -0.92:
            count += 1
    return count


def _refine_path(path_data: str, geometry: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    source_subpaths = _parse_open_subpaths(path_data)
    source_parts = re.findall(r"M\s.*?(?=\sM\s|$)", path_data.strip())
    if len(source_parts) != len(source_subpaths):
        raise ArtisanRefineError("unsupported_path", "Centerline subpaths could not be isolated.")
    maximum_mean = float(geometry["maximum_mean_deviation_px"])
    maximum = float(geometry["maximum_deviation_px"])
    epsilon = max(0.1, maximum * 0.62)
    candidate_parts: list[str] = []
    anchors_before = 0
    anchors_after = 0
    mean_total = 0.0
    sample_total = 0
    maximum_seen = 0.0
    intersections_before = 0
    intersections_after = 0
    backtracking_before = 0
    backtracking_after = 0
    accepted_subpaths = 0
    for source_part, subpath in zip(source_parts, source_subpaths):
        source_anchors = _anchors(subpath)
        source_samples = _sample_subpath(subpath)
        simplified = _rdp(source_samples, epsilon)
        if len(simplified) >= len(source_anchors):
            simplified = _rdp(source_samples, maximum * 0.82)
        source_intersections = _self_intersections(source_samples)
        source_backtracking = _backtracking(source_anchors)
        anchors_before += len(source_anchors)
        sample_total += len(source_samples)
        intersections_before += source_intersections
        backtracking_before += source_backtracking
        candidate_accepted = len(simplified) >= 2 and len(simplified) < len(source_anchors)
        if candidate_accepted:
            candidate_data, _ = open_path(
                simplified,
                corner_angle=152.0,
                smoothing=0.72,
            )
            candidate_subpath = _parse_open_subpaths(candidate_data)[0]
            candidate_samples = _sample_subpath(candidate_subpath)
            mean_deviation, max_deviation = _deviation(source_samples, candidate_samples)
            candidate_intersections = _self_intersections(candidate_samples)
            candidate_backtracking = _backtracking(simplified)
            candidate_accepted = not (
                (
                    geometry["preserve_endpoints"]
                    and (simplified[0] != source_anchors[0] or simplified[-1] != source_anchors[-1])
                )
                or mean_deviation > maximum_mean
                or max_deviation > maximum
                or (
                    geometry["reject_new_self_intersections"]
                    and candidate_intersections > source_intersections
                )
                or (
                    geometry["reject_new_backtracking"]
                    and candidate_backtracking > source_backtracking
                )
            )
        if candidate_accepted:
            candidate_parts.append(candidate_data)
            anchors_after += len(simplified)
            mean_total += mean_deviation * len(source_samples)
            maximum_seen = max(maximum_seen, max_deviation)
            intersections_after += candidate_intersections
            backtracking_after += candidate_backtracking
            accepted_subpaths += 1
        else:
            candidate_parts.append(source_part)
            anchors_after += len(source_anchors)
            intersections_after += source_intersections
            backtracking_after += source_backtracking
    reduction = 1.0 - anchors_after / anchors_before if anchors_before else 0.0
    if reduction < float(geometry["minimum_anchor_reduction_ratio"]):
        return None
    return " ".join(candidate_parts), {
        "anchors_before": anchors_before,
        "anchors_after": anchors_after,
        "anchor_reduction_ratio": reduction,
        "mean_deviation_px": mean_total / sample_total if sample_total else 0.0,
        "maximum_deviation_px": maximum_seen,
        "self_intersections_before": intersections_before,
        "self_intersections_after": intersections_after,
        "backtracking_before": backtracking_before,
        "backtracking_after": backtracking_after,
        "subpaths": len(source_subpaths),
        "refined_subpaths": accepted_subpaths,
    }


def _selected_objects(index: dict[str, Any], selector: str) -> list[list[Any]]:
    if INTENT_SELECTOR.fullmatch(selector):
        intent = selector.removeprefix("intent:")
        selected = [item for item in index["objects"] if item[1] == intent]
    elif SHAPE_ID.fullmatch(selector):
        selected = [item for item in index["objects"] if item[0] == selector]
    else:
        raise ArtisanRefineError(
            "invalid_selector", "Selector must be intent:<name> or one stable shape ID."
        )
    if not selected:
        raise ArtisanRefineError("selector_not_found", "Selector did not match an indexed object.")
    if len(selected) > MAX_PATCH_TARGETS:
        raise ArtisanRefineError("selection_too_large", "Selection exceeds the local patch limit.")
    if any(item[1] == "paint-region" for item in selected):
        raise ArtisanRefineError(
            "unsupported_selection", "Local curve refinement currently accepts stroke objects only."
        )
    return selected


def _replace_path_data(line: str, path_data: str) -> str:
    return PATH_DATA.sub(lambda match: f'd="{path_data}"', line, count=1)


def _style_signature(line: str) -> str:
    return PATH_DATA.sub('d="<PATH>"', line, count=1)


def _patch_report(core: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = _sha256(canonical)
    return {**core, "patch_sha256": digest, "patch_ref": f"patch:{digest[:12]}"}


def refine_svg(
    *,
    svg_path: str,
    index_path: str,
    profile_path: str,
    selector: str,
    output_dir: str,
) -> dict[str, Any]:
    base_path = Path(svg_path).expanduser()
    if not base_path.is_file() or base_path.suffix.lower() != ".svg":
        raise ArtisanRefineError("invalid_svg", "Base SVG must be one explicit SVG file.")
    try:
        index = load_edit_index(index_path)
        profile = load_style_profile(profile_path)
    except (EditIndexError, ArtisanBriefError) as exc:
        raise ArtisanRefineError(exc.code, str(exc)) from exc
    if index["schema_version"] != 2:
        raise ArtisanRefineError(
            "edit_index_upgrade_required", "Refinement requires edit index v2."
        )
    payload = base_path.read_bytes()
    base_sha256 = _sha256(payload)
    if index["svg_sha256"] != base_sha256:
        raise ArtisanRefineError(
            "svg_index_mismatch", "Edit index does not belong to the supplied base SVG."
        )
    try:
        before_evidence = verify_svg_artifact(base_path)
    except SvgArtifactError as exc:
        raise ArtisanRefineError(exc.code, str(exc)) from exc
    svg_text = payload.decode("utf-8")
    lines = _path_lines(svg_text)
    selected = _selected_objects(index, selector)
    target_ids = {str(item[0]) for item in selected}
    if not target_ids.issubset(lines):
        raise ArtisanRefineError(
            "svg_index_mismatch", "Indexed target is absent from the base SVG."
        )
    replacements: dict[str, str] = {}
    accepted_metrics: dict[str, dict[str, Any]] = {}
    for item in selected:
        shape_id = str(item[0])
        match = PATH_DATA.search(lines[shape_id])
        if match is None or 'fill="none"' not in lines[shape_id]:
            raise ArtisanRefineError(
                "unsupported_selection", "Local curve refinement accepts centerline strokes only."
            )
        geometry = dict(profile["geometry"])
        intent = str(item[1])
        geometry["maximum_mean_deviation_px"] = geometry["maximum_mean_deviation_by_intent_px"].get(
            intent, geometry["maximum_mean_deviation_px"]
        )
        geometry["maximum_deviation_px"] = geometry["maximum_deviation_by_intent_px"].get(
            intent, geometry["maximum_deviation_px"]
        )
        candidate = _refine_path(match.group(1), geometry)
        if candidate is not None:
            candidate_data, metrics = candidate
            replacements[shape_id] = _replace_path_data(lines[shape_id], candidate_data)
            accepted_metrics[shape_id] = metrics
    if not replacements:
        raise ArtisanRefineError(
            "no_safe_refinement",
            "No selected path passed the anchor, fidelity, and topology gates.",
        )
    output = Path(output_dir).expanduser().resolve()
    if output == base_path.parent.resolve():
        raise ArtisanRefineError(
            "unsafe_output", "Output directory must not replace the source set."
        )
    output.mkdir(parents=True, exist_ok=True)
    published = (
        output / "vector.svg",
        output / "artisan_edit_index.json",
        output / "artisan_patch.json",
    )
    if any(path.exists() for path in published):
        raise ArtisanRefineError("output_exists", "Refinement output already exists.")
    output_lines = []
    for line in svg_text.splitlines(keepends=True):
        match = PATH_ID.search(line)
        output_lines.append(replacements.get(match.group(1), line) if match else line)
    refined_payload = "".join(output_lines).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix=".artisan-refine-", dir=output) as temporary:
        staging = Path(temporary)
        staged_svg = staging / "vector.svg"
        staged_svg.write_bytes(refined_payload)
        try:
            after_evidence = verify_svg_artifact(staged_svg)
        except SvgArtifactError as exc:
            raise ArtisanRefineError(exc.code, str(exc)) from exc
        invariant_fields = ("path_count", "subpath_count", "color_count", "paint_count")
        if any(before_evidence[field] != after_evidence[field] for field in invariant_fields):
            raise ArtisanRefineError(
                "appearance_invariant_failed", "Path, subpath, color, or paint count changed."
            )
        final_lines = _path_lines(refined_payload.decode("utf-8"))
        unselected_ids = set(lines) - set(replacements)
        unselected_unchanged = all(
            lines[shape_id] == final_lines[shape_id] for shape_id in unselected_ids
        )
        selected_styles_unchanged = all(
            _style_signature(lines[shape_id]) == _style_signature(final_lines[shape_id])
            for shape_id in replacements
        )
        if not unselected_unchanged or not selected_styles_unchanged:
            raise ArtisanRefineError(
                "patch_scope_failed", "Refinement changed content outside selected path geometry."
            )
        updated_objects: list[list[Any]] = []
        for item in index["objects"]:
            updated = list(item)
            if item[0] in accepted_metrics:
                updated[3] = int(accepted_metrics[item[0]]["anchors_after"])
            updated_objects.append(updated)
        refined_sha256 = _sha256(refined_payload)
        updated_index = build_edit_index(
            structure_ref=index["structure_ref"],
            strategy="local-curvature-refinement-v1",
            svg_sha256=refined_sha256,
            objects=updated_objects,
            parent_edit_ref=index["edit_ref"],
        )
        anchors_before = sum(item["anchors_before"] for item in accepted_metrics.values())
        anchors_after = sum(item["anchors_after"] for item in accepted_metrics.values())
        report_core = {
            "schema_version": 1,
            "base_svg_sha256": base_sha256,
            "output_svg_sha256": refined_sha256,
            "base_edit_ref": index["edit_ref"],
            "output_edit_ref": updated_index["edit_ref"],
            "profile_ref": profile["profile_ref"],
            "selector": selector,
            "selected_object_count": len(selected),
            "accepted_object_count": len(accepted_metrics),
            "target_ids": list(accepted_metrics)[:24],
            "target_names": [item[5] for item in selected if item[0] in accepted_metrics][:24],
            "targets_truncated": len(accepted_metrics) > 24,
            "anchors_before": anchors_before,
            "anchors_after": anchors_after,
            "anchor_reduction_ratio": round(1.0 - anchors_after / anchors_before, 6),
            "maximum_deviation_px": round(
                max(item["maximum_deviation_px"] for item in accepted_metrics.values()), 6
            ),
            "mean_deviation_px": round(
                sum(item["mean_deviation_px"] for item in accepted_metrics.values())
                / len(accepted_metrics),
                6,
            ),
            "self_intersections_before": sum(
                item["self_intersections_before"] for item in accepted_metrics.values()
            ),
            "self_intersections_after": sum(
                item["self_intersections_after"] for item in accepted_metrics.values()
            ),
            "backtracking_before": sum(
                item["backtracking_before"] for item in accepted_metrics.values()
            ),
            "backtracking_after": sum(
                item["backtracking_after"] for item in accepted_metrics.values()
            ),
            "invariants": {
                "endpoints_preserved": True,
                "path_count_preserved": True,
                "subpath_count_preserved": True,
                "colors_preserved": True,
                "paints_preserved": True,
                "unselected_paths_byte_identical": unselected_unchanged,
                "selected_styles_byte_identical": selected_styles_unchanged,
            },
            "local_analysis_only": True,
            "external_ai_calls": 0,
        }
        report = _patch_report(report_core)
        (staging / "artisan_edit_index.json").write_text(
            json.dumps(updated_index, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (staging / "artisan_patch.json").write_text(
            json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        for staged, destination in zip(
            (staged_svg, staging / "artisan_edit_index.json", staging / "artisan_patch.json"),
            published,
        ):
            os.replace(staged, destination)
    return {
        "ok": True,
        "patch_ref": report["patch_ref"],
        "edit_ref": updated_index["edit_ref"],
        "accepted_object_count": len(accepted_metrics),
        "anchors_before": anchors_before,
        "anchors_after": anchors_after,
        "anchor_reduction_ratio": report["anchor_reduction_ratio"],
        "external_ai_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely refine selected Artisan vector curves.")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--selector", required=True)
    parser.add_argument("--output-dir", required=True)
    try:
        args = parser.parse_args(argv)
        result = refine_svg(
            svg_path=args.svg,
            index_path=args.index,
            profile_path=args.profile,
            selector=args.selector,
            output_dir=args.output_dir,
        )
    except ArtisanRefineError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
