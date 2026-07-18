from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from starbridge_mcp.vectorization import (
    RunConfig,
    VectorizationError,
    cli,
    engine,
    run_vectorization,
)
from starbridge_mcp.vectorization.svg_verify import SvgArtifactError, verify_svg_artifact

HAS_DESIGN_RUNTIME = all(importlib.util.find_spec(name) is not None for name in ("cv2", "numpy"))


class VectorizationModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.output_root = self.root / "examples" / "output" / "vectorization"
        self.repo_patch = mock.patch.object(engine, "REPO_ROOT", self.root)
        self.output_patch = mock.patch.object(engine, "OUTPUT_ROOT", self.output_root)
        self.repo_patch.start()
        self.output_patch.start()

    def tearDown(self) -> None:
        self.output_patch.stop()
        self.repo_patch.stop()
        self.temporary_dir.cleanup()

    def make_exact_source(self) -> Path:
        source = self.root / "private-customer-name.png"
        image = Image.new("RGBA", (5, 4), (0, 0, 0, 0))
        image.putdata(
            [
                (255, 0, 0, 255),
                (255, 0, 0, 255),
                (0, 0, 255, 128),
                (0, 0, 255, 128),
                (0, 0, 0, 0),
            ]
            * 3
            + [(255, 255, 255, 255)] * 5
        )
        image.save(source)
        return source

    def test_exact_mode_vertically_merges_runs_and_proves_pixel_match(self) -> None:
        source = self.make_exact_source()

        result = run_vectorization(
            RunConfig(input_path=str(source), mode="exact", reference_id="exact-case")
        )

        output = self.output_root / "exact-case" / "exact"
        svg_text = (output / "vector.svg").read_text(encoding="utf-8")
        report_text = (output / "vector_report.json").read_text(encoding="utf-8")
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"]["key"], "exact")
        self.assertTrue(result["exact_validation"]["pixel_match"])
        self.assertEqual(result["exact_validation"]["different_pixel_count"], 0)
        self.assertEqual(result["exact_validation"]["maximum_channel_difference"], 0)
        self.assertEqual(result["vector"]["subpaths"], 4)
        self.assertNotIn("<image", svg_text)
        self.assertNotIn("data:image", svg_text)
        self.assertNotIn(source.name, report_text)
        with Image.open(output / "preview.png") as preview, Image.open(source) as original:
            self.assertEqual(preview.convert("RGBA").tobytes(), original.convert("RGBA").tobytes())

    def test_default_cli_mode_is_smart_and_balanced_is_an_alias(self) -> None:
        parsed = cli.parse_args(["--input", "placeholder.png"])
        self.assertEqual(parsed.mode, "smart")
        self.assertFalse(parsed.compact)
        self.assertEqual(
            engine._configured(RunConfig("placeholder.png", mode="balanced")).mode, "smart"
        )

    def test_svg_verifier_accepts_safe_cubic_paths_and_counts_real_anchors(self) -> None:
        path = self.root / "safe-curves.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100"><path fill="#e63946" fill-rule="evenodd" '
            'stroke="none" d="M 50 10 C 72 10 90 28 90 50 C 90 72 72 90 50 90 '
            'C 28 90 10 72 10 50 C 10 28 28 10 50 10 Z"/></svg>\n',
            encoding="utf-8",
        )

        evidence = verify_svg_artifact(path, expected_width=100, expected_height=100)

        self.assertEqual(evidence["anchor_point_count"], 4)
        self.assertEqual(evidence["control_point_count"], 8)
        self.assertEqual(evidence["curve_segment_count"], 4)
        self.assertEqual(evidence["line_segment_count"], 0)

        unsafe = self.root / "unsafe-curves.svg"
        unsafe.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100"><path fill="#e63946" fill-rule="evenodd" '
            'stroke="none" d="M 10 10 c 10 0 20 10 20 20 L 10 80 Z"/></svg>',
            encoding="utf-8",
        )
        with self.assertRaises(SvgArtifactError):
            verify_svg_artifact(unsafe)

    def test_rejects_outside_output_without_creating_artifacts(self) -> None:
        source = self.make_exact_source()
        outside = self.root / "outside"

        with self.assertRaises(VectorizationError) as raised:
            run_vectorization(
                RunConfig(
                    input_path=str(source),
                    mode="exact",
                    reference_id="outside-case",
                    output_dir=str(outside),
                )
            )

        self.assertEqual(raised.exception.code, "output_outside_sandbox")
        self.assertFalse(outside.exists())

    def test_trusted_absolute_output_root_keeps_artifacts_inside_app_data(self) -> None:
        source = self.make_exact_source()
        app_output_root = (self.root / "local-app-data" / "vectorization").resolve()

        result = run_vectorization(
            RunConfig(
                input_path=str(source),
                mode="exact",
                reference_id="desktop-safe-root",
                output_root=str(app_output_root),
            )
        )

        expected = app_output_root / "desktop-safe-root" / "exact"
        self.assertTrue(result["ok"])
        self.assertTrue((expected / "vector.svg").is_file())
        self.assertFalse(self.output_root.exists())

    def test_trusted_output_root_must_be_absolute(self) -> None:
        source = self.make_exact_source()

        with self.assertRaises(VectorizationError) as raised:
            run_vectorization(
                RunConfig(
                    input_path=str(source),
                    mode="exact",
                    reference_id="relative-root",
                    output_root="relative/output",
                )
            )

        self.assertEqual("invalid_output_root", raised.exception.code)

    def test_cli_failure_is_structured_and_does_not_echo_private_input(self) -> None:
        private_path = self.root / "do-not-echo-this-name.png"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(["--input", str(private_path), "--mode", "smart"])

        response = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(response["error"]["code"], "unsupported_input")
        self.assertNotIn(private_path.name, stdout.getvalue())

    def test_compact_cli_returns_edit_refs_without_repeating_full_report(self) -> None:
        source = self.make_exact_source()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--input",
                    str(source),
                    "--mode",
                    "exact",
                    "--reference-id",
                    "compact-case",
                    "--compact",
                ]
            )

        response = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(response["mode"], "exact")
        self.assertTrue(response["validation"]["svg_verified"])
        self.assertIn("output_dir", response)
        self.assertNotIn("source", response)
        self.assertNotIn("purpose_zh", stdout.getvalue())
        self.assertLess(len(stdout.getvalue()), 1800)


@unittest.skipUnless(HAS_DESIGN_RUNTIME, "smart-vector optional dependencies not installed")
class DesignVectorizationModeTests(VectorizationModeTests):
    def make_design_source(self) -> Path:
        source = self.root / "private-design-source.png"
        image = Image.new("RGBA", (160, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 151, 111), radius=18, fill=(245, 238, 220, 255))
        draw.ellipse((24, 18, 136, 108), fill=(218, 58, 45, 255))
        draw.ellipse((48, 34, 112, 96), fill=(25, 92, 210, 220))
        draw.ellipse((68, 53, 92, 77), fill=(245, 238, 220, 255))
        for index in range(24):
            x = 12 + (index * 23) % 135
            y = 12 + (index * 37) % 95
            color = ((index * 47) % 255, (index * 79) % 255, (index * 31) % 255, 255)
            draw.rectangle((x, y, x + 2, y + 2), fill=color)
        image.save(source)
        return source

    def make_line_art_source(self) -> Path:
        source = self.root / "private-line-art-source.png"
        image = Image.new("RGBA", (240, 180), (244, 230, 194, 255))
        draw = ImageDraw.Draw(image)
        ink = (188, 84, 57, 255)
        for inset in range(16, 66, 8):
            draw.ellipse((inset, inset // 2, 240 - inset, 180 - inset // 2), outline=ink, width=2)
        for offset in range(0, 120, 12):
            draw.arc((30 + offset // 3, 35, 130 + offset // 3, 145), 25, 325, fill=ink, width=2)
        draw.rounded_rectangle((88, 57, 152, 123), radius=14, outline=ink, width=3)
        image.save(source)
        return source

    def test_smart_and_lightweight_generate_distinct_verified_outputs(self) -> None:
        source = self.make_design_source()

        smart = run_vectorization(
            RunConfig(input_path=str(source), mode="smart", reference_id="smart-case")
        )
        lightweight = run_vectorization(
            RunConfig(input_path=str(source), mode="lightweight", reference_id="light-case")
        )

        self.assertTrue(smart["mode"]["default"])
        self.assertFalse(lightweight["mode"]["default"])
        self.assertEqual(smart["mode"]["label_zh"], "智能矢量")
        self.assertEqual(lightweight["mode"]["label_zh"], "轻量矢量")
        self.assertLessEqual(lightweight["vector"]["color_count"], 8)
        self.assertLessEqual(lightweight["vector"]["subpaths"], smart["vector"]["subpaths"])
        self.assertLessEqual(lightweight["vector"]["points"], smart["vector"]["points"])
        for reference, mode in (("smart-case", "smart"), ("light-case", "lightweight")):
            output = self.output_root / reference / mode
            svg = (output / "vector.svg").read_text(encoding="utf-8")
            self.assertNotIn("<image", svg)
            self.assertNotIn("base64", svg)
            self.assertTrue((output / "preview.png").is_file())
            self.assertTrue((output / "parameters.json").is_file())
            self.assertTrue((output / "vector_report.md").is_file())

    def test_path_limit_stops_before_target_artifacts_are_published(self) -> None:
        source = self.make_design_source()
        target = self.output_root / "limited" / "smart"

        with self.assertRaises(VectorizationError) as raised:
            run_vectorization(
                RunConfig(
                    input_path=str(source),
                    mode="smart",
                    reference_id="limited",
                    max_subpaths=1,
                )
            )

        self.assertEqual(raised.exception.code, "vector_too_complex")
        self.assertFalse(target.exists())

    def test_artisan_mode_uses_cubic_curves_and_reduces_anchor_count(self) -> None:
        source = self.make_design_source()

        artisan = run_vectorization(
            RunConfig(input_path=str(source), mode="artisan", reference_id="artisan-case")
        )

        output = self.output_root / "artisan-case" / "artisan"
        svg = (output / "vector.svg").read_text(encoding="utf-8")
        self.assertEqual(artisan["mode"]["label_zh"], "匠心矢量")
        self.assertGreater(artisan["vector"]["curve_segments"], 0)
        self.assertGreater(artisan["vector"]["control_points"], 0)
        self.assertGreater(artisan["vector"]["anchor_reduction_ratio"], 0)
        self.assertLess(
            artisan["vector"]["points"],
            artisan["vector"]["baseline_polygon_anchors"],
        )
        self.assertLessEqual(
            artisan["vector"]["maximum_contour_error_px"],
            artisan["vector"]["curve_error_tolerance_px"],
        )
        self.assertIn(" C ", svg)
        self.assertNotIn("<image", svg)
        self.assertNotIn("base64", svg)

    def test_artisan_junction_continuation_pairs_straight_tangents(self) -> None:
        import numpy as np

        from starbridge_mcp.vectorization.artisan_strokes import _path_extent, _stitch_paths

        paths = [
            [(5.0, 0.0), (5.0, 5.0)],
            [(5.0, 5.0), (5.0, 10.0)],
            [(0.0, 5.0), (5.0, 5.0)],
            [(5.0, 5.0), (10.0, 5.0)],
        ]
        distance = np.ones((11, 11), dtype=np.float32)

        stitched, metrics = _stitch_paths(paths, distance, 11, 11)

        self.assertEqual(len(stitched), 2)
        self.assertEqual(metrics["continuation_pairs"], 2)
        self.assertEqual(metrics["continuation_maximum_deviation_degrees"], 0.0)
        self.assertEqual(sorted(len(path) for path in stitched), [3, 3])
        self.assertEqual(sum(_path_extent(path) for path in stitched), 20.0)

    def test_artisan_geometric_intent_profiles_are_deterministic(self) -> None:
        from starbridge_mcp.vectorization.artisan_strokes import _classify_path_intent

        self.assertEqual(_classify_path_intent([(0.0, 0.0), (0.0, 2.0)]), "micro-detail")
        self.assertEqual(
            _classify_path_intent([(0.0, 0.0), (0.0, 30.0), (0.0, 60.0)]),
            "flow-contour",
        )
        self.assertEqual(
            _classify_path_intent(
                [(0.0, 0.0), (0.0, 12.0), (12.0, 12.0), (12.0, 0.0), (0.0, 0.0)],
                closed=True,
            ),
            "ornament",
        )
        self.assertEqual(_classify_path_intent([(0.0, 0.0), (3.0, 5.0)]), "detail")

    def test_artisan_semantic_quality_gate_requires_savings_and_fidelity(self) -> None:
        from starbridge_mcp.vectorization.artisan_strokes import _semantic_rejection_reasons

        baseline = {
            "subpaths": 100,
            "anchors": 300,
            "control_points": 500,
            "batches": 10,
            "precision": 0.80,
            "recall": 0.94,
            "dice": 0.86,
        }
        candidate = {
            "subpaths": 90,
            "anchors": 260,
            "control_points": 440,
            "batches": 9,
            "precision": 0.798,
            "recall": 0.932,
            "dice": 0.857,
            "semantic_intent_counts": {
                "flow-contour": 20,
                "ornament": 40,
                "detail": 30,
                "micro-detail": 0,
            },
        }

        self.assertEqual(
            _semantic_rejection_reasons(baseline, candidate, continuation_used=True), []
        )
        candidate["recall"] = 0.92
        self.assertIn(
            "semantic_recall_regression_over_0_01",
            _semantic_rejection_reasons(baseline, candidate, continuation_used=True),
        )

    def test_artisan_line_art_builds_quality_gated_centerlines_and_stable_reference(
        self,
    ) -> None:
        source = self.make_line_art_source()

        first = run_vectorization(
            RunConfig(input_path=str(source), mode="artisan", reference_id="line-art-one")
        )
        second = run_vectorization(
            RunConfig(input_path=str(source), mode="artisan", reference_id="line-art-two")
        )

        output = self.output_root / "line-art-one" / "artisan"
        structure = json.loads((output / "artisan_structure.json").read_text(encoding="utf-8"))
        edit_index = json.loads((output / "artisan_edit_index.json").read_text(encoding="utf-8"))
        svg = (output / "vector.svg").read_text(encoding="utf-8")
        vector = first["vector"]
        self.assertTrue(vector["line_art_adaptation"])
        self.assertTrue(vector["centerline_candidate_used"])
        self.assertGreater(vector["stroke_shape_count"], 0)
        self.assertEqual(vector["knockout_shape_count"], 0)
        self.assertLess(vector["centerline_candidate_anchors"], vector["outline_fill_anchors"])
        self.assertGreaterEqual(vector["centerline_precision"], 0.6)
        self.assertGreaterEqual(vector["centerline_recall"], 0.9)
        self.assertGreaterEqual(vector["centerline_dice"], 0.72)
        self.assertTrue(vector["continuation_candidate_used"])
        self.assertEqual(vector["structure_strategy"], "curve-continuation-v2")
        self.assertLess(
            vector["continuation_candidate_subpaths"],
            vector["continuation_baseline_subpaths"],
        )
        self.assertLess(
            vector["continuation_candidate_anchors"],
            vector["continuation_baseline_anchors"],
        )
        self.assertLessEqual(
            vector["continuation_candidate_batches"],
            vector["continuation_baseline_batches"],
        )
        self.assertGreaterEqual(vector["continuation_path_reduction_ratio"], 0.15)
        self.assertGreaterEqual(vector["continuation_anchor_reduction_ratio"], 0.03)
        self.assertGreaterEqual(vector["continuation_batch_reduction_ratio"], 0.0)
        self.assertGreater(
            vector["continuation_candidate_mean_path_length_px"],
            vector["continuation_baseline_mean_path_length_px"],
        )
        self.assertGreater(vector["continuation_mean_path_length_gain_ratio"], 0.0)
        self.assertEqual(vector["continuation_length_preservation_ratio"], 1.0)
        self.assertGreaterEqual(vector["continuation_precision_delta"], -0.01)
        self.assertGreaterEqual(vector["continuation_recall_delta"], -0.015)
        self.assertGreaterEqual(vector["continuation_dice_delta"], -0.01)
        self.assertLessEqual(vector["maximum_subpaths_per_shape"], 96)
        self.assertLessEqual(vector["maximum_contour_error_px"], vector["curve_error_tolerance_px"])
        self.assertLessEqual(
            vector["maximum_compound_area_error_ratio"],
            vector["compound_area_error_tolerance_ratio"],
        )
        self.assertEqual(first["artisan_structure"]["external_ai_calls"], 0)
        self.assertEqual(
            first["artisan_structure"]["structure_ref"],
            second["artisan_structure"]["structure_ref"],
        )
        self.assertRegex(first["artisan_structure"]["structure_ref"], r"^artisan:[0-9a-f]{12}$")
        self.assertTrue(structure["interaction_contract"]["stable_shape_ids"])
        self.assertTrue(structure["interaction_contract"]["stable_intent_selectors"])
        self.assertEqual(structure["interaction_contract"]["external_ai_calls"], 0)
        self.assertEqual(
            structure["interaction_contract"]["preferred_reference"],
            "intent-selector-or-shape-id",
        )
        self.assertEqual(structure["schema_version"], 3)
        self.assertEqual(edit_index["schema_version"], 2)
        self.assertEqual(edit_index["svg_sha256"], first["artifacts"][0]["sha256"])
        self.assertIsNone(edit_index["parent_edit_ref"])
        self.assertRegex(edit_index["edit_ref"], r"^edit:[0-9a-f]{12}$")
        self.assertEqual(first["artisan_structure"]["edit_ref"], edit_index["edit_ref"])
        self.assertEqual(
            first["artisan_structure"]["edit_ref"],
            second["artisan_structure"]["edit_ref"],
        )
        self.assertTrue(first["artisan_structure"]["intent_selectors"])
        self.assertEqual(len(edit_index["objects"]), vector["shape_count"])
        self.assertTrue(all(len(item) == 6 and item[5] for item in edit_index["objects"]))
        self.assertEqual(len(structure["shapes"]), vector["shape_count"])
        self.assertEqual(
            sum(item["shape_count"] for item in structure["layers"]),
            vector["shape_count"],
        )
        self.assertIn('<g id="layer-foundation" data-role="foundation">', svg)
        self.assertIn('data-name="', svg)
        self.assertIn('fill="none" stroke="#', svg)
        self.assertIn('stroke-linecap="round" stroke-linejoin="round"', svg)
        self.assertNotIn(source.name, json.dumps(structure, ensure_ascii=False))
        self.assertNotIn(source.name, json.dumps(edit_index, ensure_ascii=False))

        from starbridge_mcp.vectorization import artisan_edit

        selector = first["artisan_structure"]["intent_selectors"][0]
        scope = artisan_edit.inspect_edit_index(str(output / "artisan_edit_index.json"), selector)
        self.assertTrue(scope["ok"])
        self.assertEqual(scope["edit_ref"], edit_index["edit_ref"])
        self.assertGreater(scope["object_count"], 0)
        self.assertNotIn(str(output), json.dumps(scope, ensure_ascii=False))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = artisan_edit.main(
                [
                    "--index",
                    str(output / "artisan_edit_index.json"),
                    "--selector",
                    selector,
                    "--object-limit",
                    "4",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertLess(len(stdout.getvalue()), 1200)
        self.assertNotIn(str(output), stdout.getvalue())
        tampered = self.root / "tampered-edit-index.json"
        edit_index["objects"][0][3] += 1
        tampered.write_text(json.dumps(edit_index), encoding="utf-8")
        with self.assertRaises(artisan_edit.EditIndexError) as raised:
            artisan_edit.inspect_edit_index(str(tampered), selector)
        self.assertEqual(raised.exception.code, "edit_index_integrity_failed")

    def test_artisan_centerline_quality_gate_retains_outline_fallback(self) -> None:
        source = self.make_line_art_source()
        rejected_metrics = {
            "skeleton_pixels": 0,
            "junction_pixels": 0,
            "junction_clusters": 0,
            "thinning_rounds": 0,
            "centerline_raw_paths": 0,
            "centerline_subpaths": 0,
            "centerline_batches": 0,
            "centerline_raw_anchors": 0,
            "centerline_anchors": 0,
            "centerline_simplify_epsilon": 1.0,
            "centerline_precision": 0.0,
            "centerline_recall": 0.0,
            "centerline_dice": 0.0,
            "centerline_min_stroke_width": 0.0,
            "centerline_max_stroke_width": 0.0,
        }

        with mock.patch(
            "starbridge_mcp.vectorization.artisan_strokes.trace_centerline_batches",
            return_value=((), rejected_metrics),
        ):
            result = run_vectorization(
                RunConfig(input_path=str(source), mode="artisan", reference_id="fallback")
            )

        vector = result["vector"]
        self.assertFalse(vector["centerline_candidate_used"])
        self.assertIn("no_centerline_paths", vector["centerline_rejection_reasons"])
        self.assertEqual(vector["stroke_shape_count"], 0)
        self.assertGreater(vector["knockout_shape_count"], 0)

    def test_artisan_continuation_gate_retains_iteration_three_centerlines(self) -> None:
        source = self.make_line_art_source()

        def no_continuation(paths, *_args, **_kwargs):
            return paths, {
                "continuation_junctions_considered": 0,
                "continuation_eligible_pairs": 0,
                "continuation_pairs": 0,
                "continuation_maximum_deviation_degrees": 0.0,
                "continuation_mean_deviation_degrees": 0.0,
                "continuation_maximum_width_difference_px": 0.0,
                "continuation_deviation_limit_degrees": 38.0,
                "continuation_width_difference_limit_px": 1.5,
            }

        with mock.patch(
            "starbridge_mcp.vectorization.artisan_strokes._stitch_paths",
            side_effect=no_continuation,
        ):
            result = run_vectorization(
                RunConfig(
                    input_path=str(source),
                    mode="artisan",
                    reference_id="continuation-fallback",
                )
            )

        vector = result["vector"]
        self.assertTrue(vector["centerline_candidate_used"])
        self.assertFalse(vector["continuation_candidate_used"])
        self.assertEqual(vector["structure_strategy"], "centerline-stroke-v1")
        self.assertIn(
            "path_reduction_below_15_percent",
            vector["continuation_rejection_reasons"],
        )
        self.assertGreater(vector["stroke_shape_count"], 0)
        self.assertEqual(vector["knockout_shape_count"], 0)

    def test_svg_verifier_accepts_open_round_centerlines_and_rejects_unsafe_style(
        self,
    ) -> None:
        path = self.root / "centerline.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100">'
            '<g id="layer-subject" data-role="subject">'
            '<path id="shape-0001" data-role="subject" data-depth="0" '
            'data-parent="none" fill="none" stroke="#bc5439" stroke-width="2.5" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'd="M 10 20 C 30 10 50 30 70 20 L 90 40"/></g></svg>',
            encoding="utf-8",
        )

        evidence = verify_svg_artifact(path, expected_width=100, expected_height=100)

        self.assertEqual(evidence["stroke_path_count"], 1)
        self.assertEqual(evidence["stroke_subpath_count"], 1)
        self.assertEqual(evidence["anchor_point_count"], 3)
        self.assertEqual(evidence["control_point_count"], 2)

        for replacement in ('stroke-width="0"', 'stroke-linecap="square"'):
            unsafe = self.root / f"unsafe-{replacement.split('=')[0]}.svg"
            unsafe.write_text(
                path.read_text(encoding="utf-8").replace(
                    'stroke-width="2.5"'
                    if replacement.startswith("stroke-width")
                    else 'stroke-linecap="round"',
                    replacement,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(SvgArtifactError):
                verify_svg_artifact(unsafe)

        unsafe_name = self.root / "unsafe-designer-name.svg"
        unsafe_name.write_text(
            path.read_text(encoding="utf-8").replace(
                'data-parent="none"', 'data-parent="none" data-name="细节:script"'
            ),
            encoding="utf-8",
        )
        with self.assertRaises(SvgArtifactError) as raised:
            verify_svg_artifact(unsafe_name)
        self.assertEqual(raised.exception.code, "invalid_designer_name")

    def test_svg_verifier_validates_structured_parent_references(self) -> None:
        path = self.root / "structured.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100">'
            '<g id="layer-foundation" data-role="foundation">'
            '<path id="shape-0001" data-role="foundation" data-depth="0" '
            'data-parent="none" fill="#f4e6c2" fill-rule="evenodd" stroke="none" '
            'd="M 0 0 L 100 0 L 100 100 L 0 100 Z"/></g>'
            '<g id="layer-subject" data-role="subject">'
            '<path id="shape-0002" data-role="subject" data-depth="1" '
            'data-parent="shape-0001" fill="#bc5439" fill-rule="evenodd" stroke="none" '
            'd="M 20 20 L 80 20 L 80 80 L 20 80 Z"/></g></svg>',
            encoding="utf-8",
        )

        evidence = verify_svg_artifact(path, expected_width=100, expected_height=100)

        self.assertEqual(evidence["layer_count"], 2)
        self.assertEqual(evidence["structured_path_count"], 2)
        self.assertEqual(evidence["nested_path_count"], 1)
        self.assertEqual(evidence["maximum_structure_depth"], 1)
        self.assertEqual(evidence["semantic_role_counts"]["subject"], 1)

        unsafe = self.root / "structured-unsafe.svg"
        unsafe.write_text(
            path.read_text(encoding="utf-8").replace(
                'data-parent="shape-0001"', 'data-parent="shape-9999"'
            ),
            encoding="utf-8",
        )
        with self.assertRaises(SvgArtifactError):
            verify_svg_artifact(unsafe)


if __name__ == "__main__":
    unittest.main()
