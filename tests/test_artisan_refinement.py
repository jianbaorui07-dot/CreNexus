from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.vectorization.artisan_brief import (
    ArtisanBriefError,
    brief_questions,
    compile_style_profile,
    load_style_profile,
)
from starbridge_mcp.vectorization.artisan_edit import build_edit_index, load_edit_index
from starbridge_mcp.vectorization.artisan_refine import ArtisanRefineError, refine_svg
from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact


class ArtisanBriefAndRefinementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.svg = self.root / "base.svg"
        self.svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100">\n'
            '<g id="layer-foundation" data-role="foundation">\n'
            '<path id="shape-0001" data-role="foundation" data-depth="0" '
            'data-parent="none" data-name="基础块面-001" fill="#fff9e8" '
            'fill-rule="evenodd" stroke="none" d="M 0 0 L 100 0 L 100 100 L 0 100 Z"/>\n'
            "</g>\n"
            '<g id="layer-detail" data-role="detail">\n'
            '<path id="shape-0002" data-role="detail" data-depth="0" '
            'data-parent="none" data-name="细节-001" fill="none" stroke="#b54b3d" '
            'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" '
            'd="M 5 50 L 15 50 L 25 50 L 35 50 L 45 50 L 55 50 L 65 50 '
            'L 75 50 L 85 50 L 95 50"/>\n'
            "</g>\n"
            "</svg>\n",
            encoding="utf-8",
        )
        evidence = verify_svg_artifact(self.svg)
        self.index = self.root / "index.json"
        index = build_edit_index(
            structure_ref="artisan:0123456789ab",
            strategy="test",
            svg_sha256=evidence["sha256"],
            objects=[
                ["shape-0001", "paint-region", [0, 0, 100, 100], 4, 1, "基础块面-001"],
                ["shape-0002", "detail", [5, 50, 90, 0], 10, 1, "细节-001"],
            ],
        )
        self.index.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        self.profile = self.root / "profile.json"
        profile = compile_style_profile(brief_questions()["recommended_answers"])
        self.profile.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_questions_compile_to_deterministic_local_prior(self) -> None:
        questions = brief_questions()
        first = compile_style_profile(questions["recommended_answers"])
        second = compile_style_profile(questions["recommended_answers"])
        self.assertEqual(first, second)
        self.assertRegex(first["profile_ref"], r"^style:[0-9a-f]{12}$")
        self.assertTrue(first["calibration"]["local_precalibration"])
        self.assertFalse(first["calibration"]["model_training"])
        self.assertEqual(first["calibration"]["external_ai_calls"], 0)
        self.assertLess(len(json.dumps(first, ensure_ascii=False)), 1200)

    def test_invalid_or_tampered_profile_is_rejected(self) -> None:
        with self.assertRaises(ArtisanBriefError):
            compile_style_profile({"primary_goal": "art-detail"})
        value = json.loads(self.profile.read_text(encoding="utf-8"))
        value["geometry"]["maximum_deviation_px"] = 99
        self.profile.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ArtisanBriefError) as raised:
            load_style_profile(str(self.profile))
        self.assertEqual(raised.exception.code, "style_profile_integrity_failed")

    def test_legacy_edit_index_remains_readable(self) -> None:
        core = {
            "schema_version": 1,
            "structure_ref": "artisan:0123456789ab",
            "strategy": "legacy",
            "selectors": [["intent:detail", 1, 2, 1]],
            "objects": [["shape-0002", "detail", [5, 50, 90, 0], 2, 1]],
            "edit_reference_format": "<edit_ref> <intent:selector|shape-id> <change>",
        }
        digest = hashlib.sha256(
            json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        legacy = {
            **core,
            "edit_index_sha256": digest,
            "edit_ref": f"edit:{digest[:12]}",
            "local_analysis_only": True,
            "external_ai_calls": 0,
        }
        path = self.root / "legacy.json"
        path.write_text(json.dumps(legacy), encoding="utf-8")
        self.assertEqual(load_edit_index(str(path))["schema_version"], 1)

    def test_refinement_reduces_anchors_and_preserves_scope(self) -> None:
        source_lines = self.svg.read_text(encoding="utf-8").splitlines()
        result = refine_svg(
            svg_path=str(self.svg),
            index_path=str(self.index),
            profile_path=str(self.profile),
            selector="intent:detail",
            output_dir=str(self.root / "refined"),
        )
        self.assertTrue(result["ok"])
        self.assertLess(result["anchors_after"], result["anchors_before"])
        output_svg = self.root / "refined" / "vector.svg"
        evidence = verify_svg_artifact(output_svg)
        self.assertEqual(evidence["path_count"], 2)
        output_lines = output_svg.read_text(encoding="utf-8").splitlines()
        self.assertEqual(source_lines[2], output_lines[2])
        report = json.loads(
            (self.root / "refined" / "artisan_patch.json").read_text(encoding="utf-8")
        )
        self.assertTrue(report["invariants"]["unselected_paths_byte_identical"])
        self.assertTrue(report["invariants"]["selected_styles_byte_identical"])
        self.assertEqual(report["self_intersections_after"], 0)
        self.assertEqual(report["backtracking_after"], 0)
        refined_index = load_edit_index(str(self.root / "refined" / "artisan_edit_index.json"))
        self.assertEqual(refined_index["svg_sha256"], evidence["sha256"])
        self.assertEqual(
            refined_index["parent_edit_ref"], load_edit_index(str(self.index))["edit_ref"]
        )
        self.assertEqual(refined_index["objects"][1][5], "细节-001")

    def test_wrong_svg_index_pair_and_paint_selection_are_rejected(self) -> None:
        self.svg.write_text(self.svg.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ArtisanRefineError) as raised:
            refine_svg(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(self.profile),
                selector="intent:detail",
                output_dir=str(self.root / "wrong"),
            )
        self.assertEqual(raised.exception.code, "svg_index_mismatch")

        # Restore the exact indexed bytes before checking the type gate.
        self.svg.write_text(self.svg.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
        with self.assertRaises(ArtisanRefineError) as raised:
            refine_svg(
                svg_path=str(self.svg),
                index_path=str(self.index),
                profile_path=str(self.profile),
                selector="intent:paint-region",
                output_dir=str(self.root / "paint"),
            )
        self.assertEqual(raised.exception.code, "unsupported_selection")


if __name__ == "__main__":
    unittest.main()
