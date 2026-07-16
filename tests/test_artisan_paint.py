from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.vectorization.artisan_brief import (
    RECOMMENDED_ANSWERS,
    _compile_style_profile,
    compile_style_profile,
    load_style_profile,
)
from starbridge_mcp.vectorization.artisan_direction import (
    compile_art_direction,
    load_illustrator_map,
)
from starbridge_mcp.vectorization.artisan_edit import build_edit_index, load_edit_index
from starbridge_mcp.vectorization.artisan_paint import ArtisanPaintError, refine_paint_structure
from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact


class ArtisanPaintStructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.svg = self.root / "paint.svg"
        self.svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100">\n'
            '<g id="layer-foundation" data-role="foundation">\n'
            '<path id="shape-0001" data-role="foundation" data-depth="0" '
            'data-parent="none" data-name="基础块面-001" fill="#f5edda" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 0 0 L 100 0 L 100 100 L 0 100 Z"/>\n'
            "</g>\n"
            '<g id="layer-subject" data-role="subject">\n'
            '<path id="shape-0002" data-role="subject" data-depth="1" '
            'data-parent="shape-0001" data-name="基础块面-002" fill="#b94f42" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 10 10 L 30 10 L 30 30 L 10 30 Z"/>\n'
            '<path id="shape-0003" data-role="subject" data-depth="1" '
            'data-parent="shape-0001" data-name="基础块面-003" fill="#b94f42" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 40 10 L 60 10 L 60 30 L 40 30 Z"/>\n'
            '<path id="shape-0004" data-role="subject" data-depth="1" '
            'data-parent="shape-0001" data-name="基础块面-004" fill="#ba5043" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 70 10 L 90 10 L 90 30 L 70 30 Z"/>\n'
            '<path id="shape-0005" data-role="subject" data-depth="1" '
            'data-parent="shape-0001" data-name="基础块面-005" fill="#b94f42" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 15 15 L 25 15 L 25 25 L 15 25 Z"/>\n'
            "</g>\n"
            '<g id="layer-detail" data-role="detail">\n'
            '<path id="shape-0006" data-role="detail" data-depth="1" '
            'data-parent="shape-0001" data-name="细节-001" fill="none" stroke="#2a2320" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" '
            'd="M 10 70 C 35 55 65 85 90 70"/>\n'
            "</g>\n"
            "</svg>\n",
            encoding="utf-8",
        )
        evidence = verify_svg_artifact(self.svg)
        self.index = self.root / "index.json"
        index = build_edit_index(
            structure_ref="artisan:0123456789ab",
            strategy="paint-test",
            svg_sha256=evidence["sha256"],
            objects=[
                ["shape-0001", "paint-region", [0, 0, 100, 100], 4, 1, "基础块面-001"],
                ["shape-0002", "paint-region", [10, 10, 20, 20], 4, 1, "基础块面-002"],
                ["shape-0003", "paint-region", [40, 10, 20, 20], 4, 1, "基础块面-003"],
                ["shape-0004", "paint-region", [70, 10, 20, 20], 4, 1, "基础块面-004"],
                ["shape-0005", "paint-region", [15, 15, 10, 10], 4, 1, "基础块面-005"],
                ["shape-0006", "detail", [10, 55, 80, 30], 2, 1, "细节-001"],
            ],
        )
        self.index.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def profile(self, strategy: str) -> Path:
        answers = {**RECOMMENDED_ANSWERS, "paint_strategy": strategy}
        path = self.root / f"{strategy}.json"
        path.write_text(
            json.dumps(compile_style_profile(answers), ensure_ascii=False), encoding="utf-8"
        )
        return path

    def direction(
        self,
        profile_path: Path,
        *,
        palette_groups: list[list[object]] | None = None,
        object_names: list[list[str]] | None = None,
        layer_names: list[list[str]] | None = None,
        edit_ref: str | None = None,
    ) -> Path:
        profile = load_style_profile(str(profile_path))
        index = load_edit_index(str(self.index))
        direction = compile_art_direction(
            {
                "base_edit_ref": edit_ref or index["edit_ref"],
                "profile_ref": profile["profile_ref"],
                "palette_groups": palette_groups
                if palette_groups is not None
                else [["#b94f42", ["#b94f42", "#ba5043"]]],
                "object_names": object_names
                if object_names is not None
                else [["shape-0004", "朱红装饰"]],
                "layer_names": layer_names
                if layer_names is not None
                else [["subject", "主体色块"]],
            }
        )
        path = self.root / f"{direction['direction_ref'].replace(':', '-')}.json"
        path.write_text(json.dumps(direction, ensure_ascii=False), encoding="utf-8")
        return path

    def test_near_colors_and_non_overlapping_leaf_blocks_are_reduced(self) -> None:
        original_lines = self.svg.read_text(encoding="utf-8").splitlines()
        result = refine_paint_structure(
            svg_path=str(self.svg),
            index_path=str(self.index),
            profile_path=str(self.profile("reduce-near-colors")),
            selector="intent:paint-region",
            output_dir=str(self.root / "reduced"),
        )
        self.assertTrue(result["ok"])
        self.assertEqual((result["blocks_before"], result["blocks_after"]), (5, 3))
        self.assertEqual((result["colors_before"], result["colors_after"]), (4, 3))
        output_svg = self.root / "reduced" / "vector.svg"
        evidence = verify_svg_artifact(output_svg)
        self.assertEqual(evidence["path_count"], 4)
        self.assertEqual(evidence["subpath_count"], 6)
        self.assertEqual(evidence["anchor_point_count"], 22)
        output_lines = output_svg.read_text(encoding="utf-8").splitlines()
        self.assertEqual(original_lines[-3], output_lines[-3])
        report = json.loads(
            (self.root / "reduced" / "artisan_paint_patch.json").read_text(encoding="utf-8")
        )
        report_text = (self.root / "reduced" / "artisan_paint_patch.json").read_text(
            encoding="utf-8"
        )
        self.assertTrue(report["invariants"]["foundation_color_preserved"])
        self.assertTrue(report["invariants"]["source_subpaths_byte_preserved"])
        self.assertTrue(report["invariants"]["unselected_paths_byte_identical"])
        self.assertGreater(report["overlap_merge_rejections"], 0)
        self.assertEqual(report["maximum_color_delta_e_allowed"], 6.0)
        self.assertLessEqual(report["maximum_color_delta_e"], 6.0)
        self.assertLess(len(report_text.encode("utf-8")), 2300)
        self.assertNotIn(str(self.root), report_text)
        self.assertNotIn(self.svg.name, report_text)
        refined_index = load_edit_index(str(self.root / "reduced" / "artisan_edit_index.json"))
        self.assertEqual(len(refined_index["objects"]), 4)
        self.assertEqual(
            refined_index["parent_edit_ref"], load_edit_index(str(self.index))["edit_ref"]
        )
        self.assertEqual(refined_index["svg_sha256"], evidence["sha256"])

    def test_preserve_palette_still_reduces_exact_same_color_blocks(self) -> None:
        result = refine_paint_structure(
            svg_path=str(self.svg),
            index_path=str(self.index),
            profile_path=str(self.profile("preserve-palette")),
            selector="intent:paint-region",
            output_dir=str(self.root / "preserved"),
        )
        self.assertEqual((result["blocks_before"], result["blocks_after"]), (5, 4))
        self.assertEqual((result["colors_before"], result["colors_after"]), (4, 4))
        report = json.loads(
            (self.root / "preserved" / "artisan_paint_patch.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["maximum_color_delta_e"], 0.0)

    def test_manual_palette_and_mismatched_index_fail_closed(self) -> None:
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(self.profile("manual-groups")),
                selector="intent:paint-region",
                output_dir=str(self.root / "manual"),
            )
        self.assertEqual(raised.exception.code, "manual_palette_required")
        self.svg.write_text(self.svg.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(self.profile("preserve-palette")),
                selector="intent:paint-region",
                output_dir=str(self.root / "mismatch"),
            )
        self.assertEqual(raised.exception.code, "svg_index_mismatch")

    def test_explicit_manual_direction_reduces_and_names_design_structure(self) -> None:
        original_lines = self.svg.read_text(encoding="utf-8").splitlines()
        profile = self.profile("manual-groups")
        direction = self.direction(profile)
        result = refine_paint_structure(
            svg_path=str(self.svg),
            index_path=str(self.index),
            profile_path=str(profile),
            direction_path=str(direction),
            selector="intent:paint-region",
            output_dir=str(self.root / "manual-directed"),
        )
        self.assertEqual((result["blocks_before"], result["blocks_after"]), (5, 3))
        self.assertEqual((result["colors_before"], result["colors_after"]), (4, 3))
        self.assertRegex(result["direction_ref"], r"^direction:[0-9a-f]{12}$")
        self.assertRegex(result["illustrator_map_ref"], r"^imap:[0-9a-f]{12}$")
        output = self.root / "manual-directed"
        svg_lines = (output / "vector.svg").read_text(encoding="utf-8").splitlines()
        named_line = next(line for line in svg_lines if 'id="shape-0002"' in line)
        self.assertIn('data-name="朱红装饰"', named_line)
        self.assertEqual(original_lines[-3], svg_lines[-3])
        index = load_edit_index(str(output / "artisan_edit_index.json"))
        shape = next(item for item in index["objects"] if item[0] == "shape-0002")
        self.assertEqual(shape[5], "朱红装饰")
        illustrator_map_path = output / "artisan_illustrator_map.json"
        illustrator_map = load_illustrator_map(str(illustrator_map_path))
        self.assertEqual(illustrator_map["layers"], [["layer-subject", "主体色块"]])
        self.assertEqual(illustrator_map["objects"], [["shape-0002", "朱红装饰"]])
        self.assertTrue(illustrator_map["requires_user_confirmed_illustrator_write"])
        map_text = illustrator_map_path.read_text(encoding="utf-8")
        self.assertLess(len(map_text.encode("utf-8")), 900)
        self.assertNotIn(str(self.root), map_text)
        report_text = (output / "artisan_paint_patch.json").read_text(encoding="utf-8")
        report = json.loads(report_text)
        self.assertIsNone(report["maximum_color_delta_e_allowed"])
        self.assertEqual(report["direction_ref"], result["direction_ref"])
        self.assertEqual(report["illustrator_map_ref"], result["illustrator_map_ref"])
        self.assertLess(len(report_text.encode("utf-8")), 2800)
        self.assertNotIn(str(self.root), report_text)

    def test_manual_direction_binding_foundation_and_name_conflicts_fail_closed(self) -> None:
        profile = self.profile("manual-groups")
        wrong_binding = self.direction(profile, edit_ref="edit:ffffffffffff")
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(profile),
                direction_path=str(wrong_binding),
                selector="intent:paint-region",
                output_dir=str(self.root / "wrong-binding"),
            )
        self.assertEqual(raised.exception.code, "art_direction_binding_mismatch")

        foundation = self.direction(
            profile,
            palette_groups=[["#b94f42", ["#f5edda"]]],
            object_names=[],
            layer_names=[],
        )
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(profile),
                direction_path=str(foundation),
                selector="intent:paint-region",
                output_dir=str(self.root / "foundation"),
            )
        self.assertEqual(raised.exception.code, "manual_foundation_protected")

        conflict = self.direction(
            profile,
            object_names=[["shape-0002", "主色块"], ["shape-0004", "装饰色块"]],
            layer_names=[],
        )
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(profile),
                direction_path=str(conflict),
                selector="intent:paint-region",
                output_dir=str(self.root / "conflict"),
            )
        self.assertEqual(raised.exception.code, "manual_name_conflict")

    def test_explicit_naming_can_publish_without_geometry_or_palette_change(self) -> None:
        profile = self.profile("manual-groups")
        direction = self.direction(
            profile,
            palette_groups=[],
            object_names=[["shape-0004", "点睛色块"]],
            layer_names=[["subject", "主体色块"]],
        )
        result = refine_paint_structure(
            svg_path=str(self.svg),
            index_path=str(self.index),
            profile_path=str(profile),
            direction_path=str(direction),
            selector="shape-0004",
            output_dir=str(self.root / "naming-only"),
        )
        self.assertEqual((result["blocks_before"], result["blocks_after"]), (1, 1))
        self.assertEqual((result["colors_before"], result["colors_after"]), (4, 4))
        output = self.root / "naming-only"
        svg = (output / "vector.svg").read_text(encoding="utf-8")
        self.assertIn('id="shape-0004"', svg)
        self.assertIn('data-name="点睛色块"', svg)
        evidence = verify_svg_artifact(output / "vector.svg")
        self.assertEqual(evidence["path_count"], 6)
        self.assertEqual(evidence["anchor_point_count"], 22)
        mapping = load_illustrator_map(str(output / "artisan_illustrator_map.json"))
        self.assertEqual(mapping["objects"], [["shape-0004", "点睛色块"]])

    def test_art_direction_is_rejected_by_non_manual_strategy(self) -> None:
        profile = self.profile("preserve-palette")
        direction = self.direction(profile)
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(profile),
                direction_path=str(direction),
                selector="intent:paint-region",
                output_dir=str(self.root / "unexpected-direction"),
            )
        self.assertEqual(raised.exception.code, "unexpected_art_direction")

    def test_no_safe_reduction_does_not_publish_a_patch(self) -> None:
        output = self.root / "no-op"
        with self.assertRaises(ArtisanPaintError) as raised:
            refine_paint_structure(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(self.profile("preserve-palette")),
                selector="shape-0001",
                output_dir=str(output),
            )
        self.assertEqual(raised.exception.code, "no_safe_paint_refinement")
        self.assertFalse(output.exists())

    def test_iteration_six_style_profile_remains_readable(self) -> None:
        legacy = _compile_style_profile(RECOMMENDED_ANSWERS, schema_version=1)
        path = self.root / "legacy-style.json"
        path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        loaded = load_style_profile(str(path))
        self.assertEqual(loaded["schema_version"], 1)

    def test_iteration_seven_profile_is_compact_and_explicit(self) -> None:
        profile = compile_style_profile(
            {**RECOMMENDED_ANSWERS, "paint_strategy": "reduce-near-colors"}
        )
        self.assertEqual(profile["schema_version"], 2)
        self.assertEqual(profile["appearance"]["paint"]["strategy"], "reduce-near-colors")
        self.assertEqual(profile["appearance"]["paint"]["delta_e"], 6.0)
        self.assertLess(
            len(json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
            1200,
        )


if __name__ == "__main__":
    unittest.main()
