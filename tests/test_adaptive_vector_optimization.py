from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from PIL import Image, ImageDraw

from starbridge_mcp.vectorization import RunConfig, VectorizationError, cli, engine
from starbridge_mcp.vectorization.adaptive_optimize import (
    QUALITY_PRESETS,
    AdaptiveOptimizationError,
    AdaptiveOptions,
    evaluate_svg_candidate,
    pareto_candidate_ids,
    resource_limit_bytes,
    select_passing_candidate,
    validated_options,
)
from starbridge_mcp.vectorization.artisan import trace_artisan_scene
from starbridge_mcp.vectorization.presets import PRESETS
from starbridge_mcp.vectorization.svg_render import render_verified_svg
from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact


class AdaptiveQualityUnitTests(unittest.TestCase):
    def test_regular_geometry_uses_theoretical_minimum_closed_anchors(self) -> None:
        circle = np.zeros((100, 120), dtype=np.int32)
        cv2.circle(circle, (60, 50), 30, 1, -1)
        circle_scene, _ = trace_artisan_scene(circle, PRESETS["artisan"])
        circle_shape = next(shape for shape in circle_scene.shapes if shape.label == 1)
        self.assertEqual(circle_shape.anchors, 4)
        self.assertEqual(circle_shape.curve_segments, 4)

        rectangle = np.zeros((100, 120), dtype=np.int32)
        cv2.rectangle(rectangle, (20, 20), (100, 80), 1, -1)
        rectangle_scene, _ = trace_artisan_scene(rectangle, PRESETS["artisan"])
        rectangle_shape = next(shape for shape in rectangle_scene.shapes if shape.label == 1)
        self.assertEqual(rectangle_shape.anchors, 4)
        self.assertEqual(rectangle_shape.corner_anchors, 4)

        hole = np.zeros((100, 120), dtype=np.int32)
        cv2.rectangle(hole, (15, 15), (105, 85), 1, -1)
        cv2.rectangle(hole, (40, 35), (80, 65), 0, -1)
        hole_scene, _ = trace_artisan_scene(hole, PRESETS["artisan"])
        compound = next(shape for shape in hole_scene.shapes if shape.label == 1)
        self.assertEqual(compound.anchors, 8)
        self.assertEqual(compound.hole_count, 1)

    def test_cli_parses_all_advanced_compatibility_fields(self) -> None:
        parsed = cli.parse_args(
            [
                "--input",
                "placeholder.png",
                "--mode",
                "artisan",
                "--quality-preset",
                "minimal",
                "--target-difference",
                "24.5",
                "--anchor-budget",
                "1200",
                "--resource-budget",
                "high",
                "--detail-protection",
                "0.9",
                "--compact",
            ]
        )
        config = cli.config_from_args(parsed)
        self.assertEqual(config.quality_preset, "minimal")
        self.assertEqual(config.target_difference, 24.5)
        self.assertEqual(config.anchor_budget, 1200)
        self.assertEqual(config.resource_budget, "high")
        self.assertEqual(config.detail_protection, 0.9)
        self.assertTrue(config.compact)

    def test_presets_match_product_quality_gates_and_allow_target_override(self) -> None:
        high = QUALITY_PRESETS["high-fidelity"]
        balanced = QUALITY_PRESETS["balanced"]
        minimal = QUALITY_PRESETS["minimal"]
        self.assertEqual(
            (high.maximum_difference_percent, high.maximum_normalized_mae, high.minimum_edge_dice),
            (15.0, 0.06, 0.92),
        )
        self.assertEqual(
            (
                balanced.maximum_difference_percent,
                balanced.maximum_normalized_mae,
                balanced.minimum_edge_dice,
            ),
            (20.0, 0.08, 0.88),
        )
        self.assertEqual(
            (
                minimal.maximum_difference_percent,
                minimal.maximum_normalized_mae,
                minimal.minimum_edge_dice,
            ),
            (25.0, 0.10, 0.84),
        )
        options, overridden = validated_options(
            AdaptiveOptions(target_difference=9.5, anchor_budget="1200")
        )
        self.assertEqual(overridden.maximum_difference_percent, 9.5)
        self.assertEqual(options.anchor_budget, 1200)

    def test_invalid_advanced_parameters_are_rejected(self) -> None:
        for options, code in (
            (AdaptiveOptions(target_difference=4.9), "invalid_target_difference"),
            (AdaptiveOptions(anchor_budget=999), "invalid_anchor_budget"),
            (AdaptiveOptions(anchor_budget=120_001), "invalid_anchor_budget"),
            (AdaptiveOptions(resource_budget="cloud"), "invalid_resource_budget"),
            (AdaptiveOptions(detail_protection=1.1), "invalid_detail_protection"),
        ):
            with self.subTest(code=code), self.assertRaises(AdaptiveOptimizationError) as raised:
                validated_options(options)
            self.assertEqual(raised.exception.code, code)

    def test_auto_resource_budget_is_25_percent_with_a_1_5_gib_ceiling(self) -> None:
        gib = 1024 * 1024 * 1024
        self.assertEqual(resource_limit_bytes("auto", 4 * gib), 1 * gib)
        self.assertEqual(resource_limit_bytes("auto", 16 * gib), round(1.5 * gib))

    def test_pareto_frontier_and_passing_sort_dimensions_are_deterministic(self) -> None:
        def candidate(identifier: str, difference: float, anchors: int, size: int) -> dict:
            return {
                "candidate_id": identifier,
                "final_render_metrics": {
                    "difference_percent": difference,
                    "normalized_mae": difference / 100,
                    "edge_dice": 1 - difference / 100,
                },
                "vector": {"anchors": anchors, "subpaths": 1, "bytes": size},
            }

        candidates = [
            candidate("quality", 2.0, 12, 300),
            candidate("small", 4.0, 6, 200),
            candidate("dominated", 5.0, 14, 400),
        ]
        self.assertEqual(pareto_candidate_ids(candidates), ["quality", "small"])

    def test_quality_gate_takes_priority_over_a_manual_or_baseline_anchor_target(self) -> None:
        baseline = {
            "candidate_id": "baseline",
            "status": "preview-only",
            "vector": {"anchors": 100, "subpaths": 2, "bytes": 400},
            "elapsed_seconds": 1.0,
        }
        passing = {
            "candidate_id": "repaired",
            "status": "pass",
            "vector": {"anchors": 110, "subpaths": 2, "bytes": 420},
            "elapsed_seconds": 1.2,
        }
        self.assertIs(select_passing_candidate([baseline, passing], baseline), passing)
        baseline["status"] = "pass"
        self.assertIs(select_passing_candidate([baseline, passing], baseline), baseline)


class FinalSvgRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def _write_primitive_svg(self) -> Path:
        path = self.root / "primitives.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="100" '
            'viewBox="0 0 120 100">\n'
            '<path fill="#e63946" fill-rule="evenodd" stroke="none" '
            'd="M 35 10 C 48.807 10 60 21.193 60 35 C 60 48.807 48.807 60 35 60 '
            'C 21.193 60 10 48.807 10 35 C 10 21.193 21.193 10 35 10 Z"/>\n'
            '<path fill="#457b9d" fill-rule="evenodd" stroke="none" '
            'd="M 70 10 L 115 10 L 115 60 L 70 60 Z M 82 22 L 82 48 L 103 48 L 103 22 Z"/>\n'
            '<path fill="none" stroke="#1d3557" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'd="M 10 80 C 28 62 42 98 60 80 C 78 62 92 98 110 80"/>\n'
            "</svg>\n",
            encoding="utf-8",
        )
        return path

    def test_circle_rectangle_hole_and_open_s_curve_use_minimal_topology(self) -> None:
        svg = self._write_primitive_svg()
        evidence = verify_svg_artifact(svg, expected_width=120, expected_height=100)
        self.assertEqual(evidence["path_count"], 3)
        self.assertEqual(evidence["subpath_count"], 4)
        self.assertEqual(evidence["anchor_point_count"], 15)
        self.assertEqual(evidence["curve_segment_count"], 6)
        self.assertEqual(evidence["embedded_raster_count"], 0)
        self.assertEqual(evidence["external_reference_count"], 0)

        render = self.root / "render.png"
        render_verified_svg(
            svg,
            render,
            expected_width=120,
            expected_height=100,
            output_width=240,
            output_height=200,
        )
        with Image.open(render) as image:
            self.assertEqual(image.size, (240, 200))
            self.assertEqual(image.convert("RGBA").getpixel((184, 70))[3], 0)

    def test_final_render_evaluation_is_cached_and_uses_all_three_visual_gates(self) -> None:
        svg = self._write_primitive_svg()
        reference = self.root / "reference.png"
        render_verified_svg(svg, reference, expected_width=120, expected_height=100)
        with Image.open(reference) as opened:
            image = opened.convert("RGBA")
        cache = self.root / "cache"
        first = evaluate_svg_candidate(
            candidate_id="first",
            reference=image,
            source_sha256="0" * 64,
            svg_path=svg,
            render_path=self.root / "first.png",
            cache_dir=cache,
            thresholds=QUALITY_PRESETS["high-fidelity"],
            detail_protection=0.75,
            resource_limit=512 * 1024 * 1024,
            expected_svg_width=120,
            expected_svg_height=100,
        )
        second = evaluate_svg_candidate(
            candidate_id="second",
            reference=image,
            source_sha256="0" * 64,
            svg_path=svg,
            render_path=self.root / "second.png",
            cache_dir=cache,
            thresholds=QUALITY_PRESETS["high-fidelity"],
            detail_protection=0.75,
            resource_limit=512 * 1024 * 1024,
            expected_svg_width=120,
            expected_svg_height=100,
        )
        self.assertEqual(first["status"], "pass")
        self.assertTrue(all(first["gates"].values()))
        self.assertEqual(first["final_render_metrics"]["difference_percent"], 0.0)
        self.assertEqual(first["final_render_metrics"]["normalized_mae"], 0.0)
        self.assertEqual(first["final_render_metrics"]["edge_dice"], 1.0)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        analysis_entries = list((cache / "reference").rglob("*.npz"))
        self.assertEqual(len(analysis_entries), 1)
        with np.load(analysis_entries[0], allow_pickle=False) as cached:
            self.assertEqual(
                set(cached.files),
                {
                    "pyramid_rgb",
                    "pyramid_alpha",
                    "edges",
                    "distance_field",
                    "color_groups",
                },
            )

    def test_renderer_serializes_straight_alpha_for_translucent_paints(self) -> None:
        svg = self.root / "alpha.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" '
            'viewBox="0 0 20 20"><path fill="#ff0000" fill-opacity="0.5" '
            'fill-rule="evenodd" stroke="none" d="M 0 0 L 20 0 L 20 20 L 0 20 Z"/></svg>',
            encoding="utf-8",
        )
        rendered = self.root / "alpha.png"
        render_verified_svg(svg, rendered, expected_width=20, expected_height=20)
        with Image.open(rendered) as image:
            red, green, blue, alpha = image.convert("RGBA").getpixel((10, 10))
        self.assertGreaterEqual(red, 254)
        self.assertEqual((green, blue), (0, 0))
        self.assertIn(alpha, {127, 128})


class AdaptiveEngineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.output_root = self.root / "examples" / "output" / "vectorization"
        self.repo_patch = mock.patch.object(engine, "REPO_ROOT", self.root)
        self.output_patch = mock.patch.object(engine, "OUTPUT_ROOT", self.output_root)
        self.repo_patch.start()
        self.output_patch.start()
        self.source = self.root / "private-artwork-name.png"
        image = Image.new("RGBA", (128, 96), (244, 236, 214, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((12, 10, 116, 88), fill=(204, 55, 48, 255))
        draw.rounded_rectangle((35, 24, 93, 76), radius=12, fill=(35, 91, 180, 255))
        draw.ellipse((52, 36, 76, 64), fill=(244, 236, 214, 255))
        image.save(self.source)

    def tearDown(self) -> None:
        self.output_patch.stop()
        self.repo_patch.stop()
        self.temporary_dir.cleanup()

    def test_artisan_keeps_baseline_and_reports_final_svg_render_evidence(self) -> None:
        result = engine.run_vectorization(
            RunConfig(
                input_path=str(self.source),
                mode="artisan",
                reference_id="adaptive",
                auto_minimize_anchors=False,
            )
        )
        output = self.output_root / "adaptive" / "artisan"
        optimization = result["adaptive_optimization"]
        self.assertEqual(optimization["candidate_count"], 1)
        self.assertEqual(optimization["external_ai_calls"], 0)
        self.assertLessEqual(optimization["anchors"]["after"], optimization["anchors"]["before"])
        self.assertIn("difference_percent", optimization["final_render_metrics"])
        self.assertIn("normalized_mae", optimization["final_render_metrics"])
        self.assertIn("edge_dice", optimization["final_render_metrics"])
        self.assertRegex(optimization["quality_ref"], r"^quality:[0-9a-f]{12}$")
        self.assertRegex(optimization["patch_ref"], r"^patch:[0-9a-f]{12}$")
        self.assertTrue((output / "artisan_baseline.svg").is_file())
        self.assertTrue((output / "svg_render.png").is_file())
        self.assertTrue((output / "adaptive_optimization.json").is_file())
        svg_text = (output / "vector.svg").read_text(encoding="utf-8")
        self.assertNotIn("<image", svg_text)
        self.assertNotIn("base64", svg_text)
        self.assertNotIn("http://", svg_text.replace('xmlns="http://www.w3.org/2000/svg"', ""))

    def test_compact_artisan_result_stays_below_2kb_and_contains_no_private_source(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--input",
                    str(self.source),
                    "--mode",
                    "artisan",
                    "--reference-id",
                    "compact-adaptive",
                    "--no-auto-minimize-anchors",
                    "--compact",
                ]
            )
        payload = stdout.getvalue()
        result = json.loads(payload)
        self.assertEqual(exit_code, 0)
        self.assertLess(len(payload.encode("utf-8")), 2048)
        self.assertNotIn(self.source.name, payload)
        self.assertNotIn(str(self.root), payload)
        self.assertRegex(result["optimization"]["quality_ref"], r"^quality:")
        self.assertLessEqual(len(result["optimization"]["error_hotspots"]), 5)

    def test_resource_limit_stops_without_overwriting_an_existing_result(self) -> None:
        target = self.output_root / "resource-case" / "artisan"
        target.mkdir(parents=True)
        old_svg = target / "vector.svg"
        old_svg.write_text("old-result", encoding="utf-8")
        with (
            mock.patch(
                "starbridge_mcp.vectorization.adaptive_optimize.resource_limit_bytes",
                return_value=1,
            ),
            self.assertRaises(VectorizationError) as raised,
        ):
            engine.run_vectorization(
                RunConfig(
                    input_path=str(self.source),
                    mode="artisan",
                    reference_id="resource-case",
                )
            )
        self.assertEqual(raised.exception.code, "resource_limit")
        self.assertEqual(old_svg.read_text(encoding="utf-8"), "old-result")
        self.assertEqual(list(target.iterdir()), [old_svg])

    def test_exact_output_is_unchanged_by_artisan_only_options(self) -> None:
        first = engine.run_vectorization(
            RunConfig(input_path=str(self.source), mode="exact", reference_id="exact-one")
        )
        second = engine.run_vectorization(
            RunConfig(
                input_path=str(self.source),
                mode="exact",
                reference_id="exact-two",
                quality_preset="minimal",
                target_difference=25,
                anchor_budget=1000,
                resource_budget="low",
                auto_minimize_anchors=False,
            )
        )
        first_svg = self.output_root / "exact-one" / "exact" / "vector.svg"
        second_svg = self.output_root / "exact-two" / "exact" / "vector.svg"
        self.assertEqual(first_svg.read_bytes(), second_svg.read_bytes())
        self.assertEqual(first["parameters"], second["parameters"])
        self.assertNotIn("adaptive_optimization", first)
        self.assertNotIn("adaptive_optimization", second)


if __name__ == "__main__":
    unittest.main()
