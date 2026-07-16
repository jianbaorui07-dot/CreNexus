from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
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
from .svg_verify import SvgArtifactError, verify_svg_artifact

PATH_ID = re.compile(r'<path\s+id="(shape-[0-9]{4,})"')
PATH_DATA = re.compile(r'\bd="([^"]*)"')
ATTRIBUTE = re.compile(r'([a-z][a-z-]*)="([^"]*)"')
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_PAINT_TARGETS = 4096


class ArtisanPaintError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PaintObject:
    shape_id: str
    item: list[Any]
    line: str
    role: str
    depth: int
    parent: str
    fill: str
    opacity: str
    path_data: str

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return tuple(int(value) for value in self.item[2])  # type: ignore[return-value]

    @property
    def anchors(self) -> int:
        return int(self.item[3])

    @property
    def subpaths(self) -> int:
        return int(self.item[4])


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _path_lines(svg_text: str) -> dict[str, str]:
    lines: dict[str, str] = {}
    for line in svg_text.splitlines(keepends=True):
        match = PATH_ID.search(line)
        if match:
            lines[match.group(1)] = line
    return lines


def _attributes(line: str) -> dict[str, str]:
    return dict(ATTRIBUTE.findall(line))


def _replace_attribute(line: str, name: str, value: str) -> str:
    return re.sub(rf'\b{re.escape(name)}="[^"]*"', f'{name}="{value}"', line, count=1)


def _subpath_parts(path_data: str) -> list[str]:
    return re.findall(r"M\s.*?(?=\sM\s|$)", path_data.strip())


def _bbox_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    first_right = first[0] + first[2]
    first_bottom = first[1] + first[3]
    second_right = second[0] + second[2]
    second_bottom = second[1] + second[3]
    return (
        first[0] < second_right
        and second[0] < first_right
        and first[1] < second_bottom
        and second[1] < first_bottom
    )


def _bbox_union(objects: list[PaintObject]) -> list[int]:
    minimum_x = min(item.bbox[0] for item in objects)
    minimum_y = min(item.bbox[1] for item in objects)
    maximum_x = max(item.bbox[0] + item.bbox[2] for item in objects)
    maximum_y = max(item.bbox[1] + item.bbox[3] for item in objects)
    return [minimum_x, minimum_y, maximum_x - minimum_x, maximum_y - minimum_y]


def _srgb_channel(value: int) -> float:
    channel = value / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _lab(color: str) -> tuple[float, float, float]:
    red = _srgb_channel(int(color[1:3], 16))
    green = _srgb_channel(int(color[3:5], 16))
    blue = _srgb_channel(int(color[5:7], 16))
    x = (0.4124564 * red + 0.3575761 * green + 0.1804375 * blue) / 0.95047
    y = 0.2126729 * red + 0.7151522 * green + 0.072175 * blue
    z = (0.0193339 * red + 0.119192 * green + 0.9503041 * blue) / 1.08883

    def transform(value: float) -> float:
        return value ** (1.0 / 3.0) if value > 0.008856 else 7.787 * value + 16.0 / 116.0

    transformed_x = transform(x)
    transformed_y = transform(y)
    transformed_z = transform(z)
    return (
        116.0 * transformed_y - 16.0,
        500.0 * (transformed_x - transformed_y),
        200.0 * (transformed_y - transformed_z),
    )


def _delta_e(first: str, second: str) -> float:
    return math.dist(_lab(first), _lab(second))


def _selected_objects(index: dict[str, Any], selector: str) -> list[list[Any]]:
    if INTENT_SELECTOR.fullmatch(selector):
        intent = selector.removeprefix("intent:")
        selected = [item for item in index["objects"] if item[1] == intent]
    elif SHAPE_ID.fullmatch(selector):
        selected = [item for item in index["objects"] if item[0] == selector]
    else:
        raise ArtisanPaintError(
            "invalid_selector", "Selector must be intent:<name> or one stable shape ID."
        )
    if not selected:
        raise ArtisanPaintError("selector_not_found", "Selector did not match an indexed object.")
    if len(selected) > MAX_PAINT_TARGETS:
        raise ArtisanPaintError("selection_too_large", "Selection exceeds the local paint limit.")
    if any(item[1] != "paint-region" for item in selected):
        raise ArtisanPaintError(
            "unsupported_selection", "Paint structure refinement accepts fill objects only."
        )
    return selected


def _paint_objects(
    selected: list[list[Any]],
    lines: dict[str, str],
) -> list[PaintObject]:
    objects: list[PaintObject] = []
    for item in selected:
        shape_id = str(item[0])
        line = lines.get(shape_id)
        if line is None:
            raise ArtisanPaintError("svg_index_mismatch", "Indexed paint is absent from the SVG.")
        attributes = _attributes(line)
        fill = attributes.get("fill", "").lower()
        path_data = attributes.get("d", "")
        required = {"data-role", "data-depth", "data-parent"}
        if (
            not required.issubset(attributes)
            or not HEX_COLOR.fullmatch(fill)
            or attributes.get("stroke") != "none"
            or not path_data
        ):
            raise ArtisanPaintError(
                "unsupported_selection", "Paint structure refinement accepts closed fills only."
            )
        try:
            depth = int(attributes["data-depth"])
        except ValueError as exc:
            raise ArtisanPaintError(
                "unsupported_selection", "Paint structure metadata is invalid."
            ) from exc
        objects.append(
            PaintObject(
                shape_id=shape_id,
                item=item,
                line=line,
                role=attributes["data-role"],
                depth=depth,
                parent=attributes["data-parent"],
                fill=fill,
                opacity=attributes.get("fill-opacity", "1"),
                path_data=path_data,
            )
        )
    return objects


def _palette_map(
    objects: list[PaintObject],
    strategy: str,
    maximum_delta_e: float,
) -> dict[str, str]:
    if strategy == "manual-groups":
        raise ArtisanPaintError(
            "manual_palette_required", "Manual color groups require an explicit future palette map."
        )
    foundation_colors = {item.fill for item in objects if item.role == "foundation"}
    candidates = [
        item for item in objects if item.role != "foundation" and item.fill not in foundation_colors
    ]
    weights: dict[str, int] = {}
    for item in candidates:
        weights[item.fill] = weights.get(item.fill, 0) + max(1, item.bbox[2] * item.bbox[3])
    ordered = sorted(weights, key=lambda color: (-weights[color], color))
    mapping = {item.fill: item.fill for item in objects}
    if strategy == "preserve-palette" or len(ordered) < 2:
        return mapping
    if strategy == "monochrome":
        target = ordered[0]
        mapping.update(dict.fromkeys(ordered, target))
        return mapping
    centers: list[str] = []
    for color in ordered:
        nearest = min(centers, key=lambda center: _delta_e(color, center), default=None)
        if nearest is not None and _delta_e(color, nearest) <= maximum_delta_e:
            mapping[color] = nearest
        else:
            centers.append(color)
    return mapping


def _merge_batches(
    objects: list[PaintObject],
    mapped_colors: dict[str, str],
    parent_ids: set[str],
    *,
    maximum_subpaths: int,
    maximum_anchors: int,
) -> tuple[list[list[PaintObject]], int]:
    grouped: dict[tuple[str, int, str, str, str], list[PaintObject]] = {}
    for item in objects:
        if item.shape_id in parent_ids:
            continue
        key = (item.role, item.depth, item.parent, mapped_colors[item.fill], item.opacity)
        grouped.setdefault(key, []).append(item)
    batches: list[list[PaintObject]] = []
    overlap_rejections = 0
    for key in sorted(grouped):
        key_batches: list[list[PaintObject]] = []
        for item in sorted(grouped[key], key=lambda value: value.shape_id):
            placed = False
            for batch in key_batches:
                overlaps = any(_bbox_overlap(item.bbox, member.bbox) for member in batch)
                if overlaps:
                    overlap_rejections += 1
                    continue
                if (
                    sum(member.subpaths for member in batch) + item.subpaths > maximum_subpaths
                    or sum(member.anchors for member in batch) + item.anchors > maximum_anchors
                ):
                    continue
                batch.append(item)
                placed = True
                break
            if not placed:
                key_batches.append([item])
        batches.extend(batch for batch in key_batches if len(batch) > 1)
    return batches, overlap_rejections


def _report(core: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = _sha256(canonical)
    return {**core, "patch_sha256": digest, "patch_ref": f"patch:{digest[:12]}"}


def refine_paint_structure(
    *,
    svg_path: str,
    index_path: str,
    profile_path: str,
    selector: str,
    output_dir: str,
) -> dict[str, Any]:
    base_path = Path(svg_path).expanduser()
    if not base_path.is_file() or base_path.suffix.lower() != ".svg":
        raise ArtisanPaintError("invalid_svg", "Base SVG must be one explicit SVG file.")
    try:
        index = load_edit_index(index_path)
        profile = load_style_profile(profile_path)
    except (EditIndexError, ArtisanBriefError) as exc:
        raise ArtisanPaintError(exc.code, str(exc)) from exc
    if index["schema_version"] != 2:
        raise ArtisanPaintError(
            "edit_index_upgrade_required", "Paint refinement requires index v2."
        )
    if profile["schema_version"] != 2:
        raise ArtisanPaintError(
            "style_profile_upgrade_required", "Paint refinement requires style profile v2."
        )
    payload = base_path.read_bytes()
    base_sha256 = _sha256(payload)
    if index["svg_sha256"] != base_sha256:
        raise ArtisanPaintError("svg_index_mismatch", "Edit index does not match the base SVG.")
    try:
        before = verify_svg_artifact(base_path)
    except SvgArtifactError as exc:
        raise ArtisanPaintError(exc.code, str(exc)) from exc
    svg_text = payload.decode("utf-8")
    lines = _path_lines(svg_text)
    selected = _selected_objects(index, selector)
    objects = _paint_objects(selected, lines)
    appearance = profile["appearance"]
    paint_profile = appearance["paint"]
    strategy = str(paint_profile["strategy"])
    mapping = _palette_map(objects, strategy, float(paint_profile["delta_e"]))
    all_attributes = [_attributes(line) for line in lines.values()]
    parent_ids = {
        attributes["data-parent"]
        for attributes in all_attributes
        if attributes.get("data-parent") not in {None, "none"}
    }
    batches, overlap_rejections = _merge_batches(
        objects,
        mapping,
        parent_ids,
        maximum_subpaths=int(paint_profile["max_subpaths"]),
        maximum_anchors=int(paint_profile["max_anchors"]),
    )
    removed_to_retained: dict[str, str] = {}
    replacement_lines: dict[str, str] = {}
    batch_by_retained: dict[str, list[PaintObject]] = {}
    for batch in batches:
        retained = batch[0]
        batch_by_retained[retained.shape_id] = batch
        for removed in batch[1:]:
            removed_to_retained[removed.shape_id] = retained.shape_id
    for item in objects:
        if item.shape_id in removed_to_retained:
            continue
        line = item.line
        mapped_color = mapping[item.fill]
        if mapped_color != item.fill:
            line = _replace_attribute(line, "fill", mapped_color)
        batch = batch_by_retained.get(item.shape_id)
        if batch:
            line = _replace_attribute(line, "d", " ".join(member.path_data for member in batch))
        replacement_lines[item.shape_id] = line
    color_changed = any(mapping[item.fill] != item.fill for item in objects)
    selected_count = len(objects)
    block_reduction = len(removed_to_retained) / selected_count if selected_count else 0.0
    if any(mapping[item.fill] != item.fill for item in objects if item.role == "foundation"):
        raise ArtisanPaintError(
            "foundation_color_changed", "Foundation colors must remain unchanged."
        )
    if not color_changed and block_reduction < float(paint_profile["min_block_reduction"]):
        raise ArtisanPaintError(
            "no_safe_paint_refinement", "No selected paint passed block or color reduction gates."
        )
    output = Path(output_dir).expanduser().resolve()
    if output == base_path.parent.resolve():
        raise ArtisanPaintError(
            "unsafe_output", "Output directory must not replace the source set."
        )
    output.mkdir(parents=True, exist_ok=True)
    published = (
        output / "vector.svg",
        output / "artisan_edit_index.json",
        output / "artisan_paint_patch.json",
    )
    if any(path.exists() for path in published):
        raise ArtisanPaintError("output_exists", "Paint refinement output already exists.")
    output_lines: list[str] = []
    for line in svg_text.splitlines(keepends=True):
        match = PATH_ID.search(line)
        if match is None:
            output_lines.append(line)
            continue
        shape_id = match.group(1)
        if shape_id in removed_to_retained:
            continue
        output_lines.append(replacement_lines.get(shape_id, line))
    refined_payload = "".join(output_lines).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix=".artisan-paint-", dir=output) as temporary:
        staging = Path(temporary)
        staged_svg = staging / "vector.svg"
        staged_svg.write_bytes(refined_payload)
        try:
            after = verify_svg_artifact(staged_svg)
        except SvgArtifactError as exc:
            raise ArtisanPaintError(exc.code, str(exc)) from exc
        selected_ids = {item.shape_id for item in objects}
        refined_lines = _path_lines(refined_payload.decode("utf-8"))
        unselected_ids = set(lines) - selected_ids
        unselected_unchanged = all(lines[item] == refined_lines[item] for item in unselected_ids)
        source_geometry = Counter(
            part for item in objects for part in _subpath_parts(item.path_data)
        )
        output_geometry = Counter(
            part
            for shape_id, line in refined_lines.items()
            if shape_id in selected_ids - set(removed_to_retained)
            for part in _subpath_parts(_attributes(line)["d"])
        )
        geometry_preserved = source_geometry == output_geometry
        if not unselected_unchanged or not geometry_preserved:
            raise ArtisanPaintError(
                "paint_scope_failed", "Paint refinement changed unselected or source geometry."
            )
        if (
            before["subpath_count"] != after["subpath_count"]
            or before["anchor_point_count"] != after["anchor_point_count"]
            or before["stroke_path_count"] != after["stroke_path_count"]
            or after["path_count"] > before["path_count"]
            or after["color_count"] > before["color_count"]
            or after["paint_count"] > before["paint_count"]
        ):
            raise ArtisanPaintError(
                "paint_invariant_failed",
                "Geometry, stroke, block, color, or paint invariants failed.",
            )
        if (
            before["path_count"] == after["path_count"]
            and before["color_count"] == after["color_count"]
            and before["paint_count"] == after["paint_count"]
        ):
            raise ArtisanPaintError(
                "no_measurable_paint_reduction",
                "Candidate changed paint values without reducing blocks, colors, or paints.",
            )
        object_by_id = {str(item[0]): list(item) for item in index["objects"]}
        for retained_id, batch in batch_by_retained.items():
            retained = object_by_id[retained_id]
            retained[2] = _bbox_union(batch)
            retained[3] = sum(item.anchors for item in batch)
            retained[4] = sum(item.subpaths for item in batch)
        updated_objects = [
            object_by_id[str(item[0])]
            for item in index["objects"]
            if str(item[0]) not in removed_to_retained
        ]
        refined_sha256 = _sha256(refined_payload)
        updated_index = build_edit_index(
            structure_ref=index["structure_ref"],
            strategy="local-paint-structure-v1",
            svg_sha256=refined_sha256,
            objects=updated_objects,
            parent_edit_ref=index["edit_ref"],
        )
        color_deltas = [
            (_delta_e(item.fill, mapping[item.fill]), max(1, item.bbox[2] * item.bbox[3]))
            for item in objects
        ]
        total_weight = sum(weight for _, weight in color_deltas)
        selected_before = len(objects)
        selected_after = selected_before - len(removed_to_retained)
        report_core = {
            "schema_version": 1,
            "base_svg_sha256": base_sha256,
            "output_svg_sha256": refined_sha256,
            "base_edit_ref": index["edit_ref"],
            "output_edit_ref": updated_index["edit_ref"],
            "profile_ref": profile["profile_ref"],
            "selector": selector,
            "paint_strategy": strategy,
            "maximum_color_delta_e_allowed": paint_profile["delta_e"],
            "selected_blocks_before": selected_before,
            "selected_blocks_after": selected_after,
            "block_reduction_ratio": round(1.0 - selected_after / selected_before, 6),
            "path_count_before": before["path_count"],
            "path_count_after": after["path_count"],
            "color_count_before": before["color_count"],
            "color_count_after": after["color_count"],
            "paint_count_before": before["paint_count"],
            "paint_count_after": after["paint_count"],
            "maximum_color_delta_e": round(
                max((value for value, _ in color_deltas), default=0.0), 6
            ),
            "weighted_mean_color_delta_e": round(
                sum(value * weight for value, weight in color_deltas) / total_weight,
                6,
            ),
            "merged_groups": [[batch[0].shape_id, len(batch)] for batch in batches[:24]],
            "merged_groups_truncated": len(batches) > 24,
            "overlap_merge_rejections": overlap_rejections,
            "palette_map": [[source, target] for source, target in sorted(mapping.items())],
            "invariants": {
                "foundation_color_preserved": all(
                    mapping[item.fill] == item.fill for item in objects if item.role == "foundation"
                ),
                "source_subpaths_byte_preserved": geometry_preserved,
                "subpath_count_preserved": before["subpath_count"] == after["subpath_count"],
                "anchor_count_preserved": before["anchor_point_count"]
                == after["anchor_point_count"],
                "stroke_paths_preserved": before["stroke_path_count"] == after["stroke_path_count"],
                "unselected_paths_byte_identical": unselected_unchanged,
                "no_overlapping_paths_merged": True,
            },
            "local_analysis_only": True,
            "external_ai_calls": 0,
        }
        report = _report(report_core)
        (staging / "artisan_edit_index.json").write_text(
            json.dumps(updated_index, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (staging / "artisan_paint_patch.json").write_text(
            json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        for staged, destination in zip(
            (staged_svg, staging / "artisan_edit_index.json", staging / "artisan_paint_patch.json"),
            published,
        ):
            os.replace(staged, destination)
    return {
        "ok": True,
        "patch_ref": report["patch_ref"],
        "edit_ref": updated_index["edit_ref"],
        "blocks_before": selected_before,
        "blocks_after": selected_after,
        "colors_before": before["color_count"],
        "colors_after": after["color_count"],
        "external_ai_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely reduce Artisan paint blocks and colors.")
    parser.add_argument("--svg", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--selector", default="intent:paint-region")
    parser.add_argument("--output-dir", required=True)
    try:
        args = parser.parse_args(argv)
        result = refine_paint_structure(
            svg_path=args.svg,
            index_path=args.index,
            profile_path=args.profile,
            selector=args.selector,
            output_dir=args.output_dir,
        )
    except ArtisanPaintError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
