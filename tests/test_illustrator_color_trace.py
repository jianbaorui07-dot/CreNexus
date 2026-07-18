from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "examples" / "illustrator_bridge" / "scripts"
QUALITY_SCHEMA = (
    REPO_ROOT
    / "examples"
    / "illustrator_bridge"
    / "protocols"
    / "headless_svg_quality.v1.schema.json"
)


def load_script_module(name: str, filename: str) -> ModuleType:
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load test module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

svg_verifier = load_script_module("svg_artifact_verifier", "svg_artifact_verifier.py")
TRACE_RUNTIME_DISCOVERABLE = all(
    importlib.util.find_spec(name) is not None for name in ("cv2", "numpy", "PIL")
)
trace = (
    load_script_module("trace_photo_preview_for_tests", "trace_photo_preview.py")
    if TRACE_RUNTIME_DISCOVERABLE
    else None
)
HAS_TRACE_RUNTIME = trace is not None and all(
    getattr(trace, name) is not None for name in ("cv2", "np", "Image")
)
if os.environ.get("STARBRIDGE_REQUIRE_TRACE_RUNTIME") == "1" and not HAS_TRACE_RUNTIME:
    raise RuntimeError("illustrator-trace runtime is required for this test job")


class SvgArtifactVerifierTests(unittest.TestCase):
    def test_headless_quality_schema_is_closed_and_sanitized(self) -> None:
        schema = json.loads(QUALITY_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {"in_memory_quantized_target", "explicit_reference_work_rgb"},
            set(schema["properties"]["target_kind"]["enum"]),
        )
        safety = schema["properties"]["safety"]["properties"]
        self.assertFalse(safety["source_path_reported"]["const"])
        self.assertFalse(safety["image_bytes_returned"]["const"])
        self.assertFalse(safety["rasterizes_embedded_image"]["const"])
        self.assertTrue(safety["visual_review_required"]["const"])

    def write_svg(self, directory: Path, body: str) -> Path:
        path = directory / "artifact.svg"
        path.write_text(body, encoding="utf-8")
        return path

    def test_accepts_editable_paths_and_returns_content_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = self.write_svg(
                Path(temporary_dir),
                '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" '
                'viewBox="0 0 64 48"><rect width="64" height="48" fill="#ffffff"/>'
                '<path d="M 2 2 L 62 2 L 62 46 L 2 46 Z M 20 12 L 44 12 L 44 36 '
                'L 20 36 Z" fill="#e63946" fill-rule="evenodd" stroke="none"/></svg>',
            )

            evidence = svg_verifier.verify_svg_artifact(path, expected_width=64, expected_height=48)

        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["path_count"], 1)
        self.assertEqual(evidence["subpath_count"], 2)
        self.assertEqual(evidence["color_count"], 1)
        self.assertEqual(evidence["embedded_raster_count"], 0)
        self.assertEqual(len(evidence["sha256"]), 64)
        self.assertGreater(evidence["bytes"], 0)

    def test_rejects_empty_or_unsafe_svg_outputs(self) -> None:
        cases = {
            "no_paths": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><rect width="10" height="10" fill="#ffffff"/></svg>'
            ),
            "embedded_raster": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><image href="data:image/png;base64,AA=="/></svg>'
            ),
            "script": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><script>noop()</script></svg>'
            ),
            "external_href": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><path href="https://invalid.example/a" '
                'd="M 0 0 L 10 0 L 10 10 Z" fill="#000000"/></svg>'
            ),
            "invalid_view_box": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 0 10"><path d="M 0 0 L 10 0 L 10 10 Z" '
                'fill="#000000"/></svg>'
            ),
            "invalid_path_data": (
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><path d="M 0 0" fill="#000000" '
                'fill-rule="evenodd" stroke="none"/></svg>'
            ),
            "doctype": (
                '<!DOCTYPE svg [<!ENTITY marker "unsafe">]><svg '
                'xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><path d="M 0 0 L 10 0 L 10 10 Z" '
                'fill="#000000" fill-rule="evenodd" stroke="none"/></svg>'
            ),
            "processing_instruction": (
                '<?xml-stylesheet href="https://invalid.example/style.css"?>'
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
                'viewBox="0 0 10 10"><path d="M 0 0 L 10 0 L 10 10 Z" '
                'fill="#000000" fill-rule="evenodd" stroke="none"/></svg>'
            ),
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            directory = Path(temporary_dir)
            for name, body in cases.items():
                with self.subTest(name=name):
                    path = self.write_svg(directory, body)
                    with self.assertRaises(svg_verifier.SvgArtifactError):
                        svg_verifier.verify_svg_artifact(path)

    def test_rejects_utf16_processing_instruction_before_xml_parse(self) -> None:
        body = (
            '<?xml-stylesheet href="https://invalid.example/style.css"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
            'viewBox="0 0 10 10"><path d="M 0 0 L 10 0 L 10 10 Z" '
            'fill="#000000" fill-rule="evenodd" stroke="none"/></svg>'
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "artifact.svg"
            path.write_bytes(body.encode("utf-16"))

            with self.assertRaises(svg_verifier.SvgArtifactError) as rejected:
                svg_verifier.verify_svg_artifact(path)

        self.assertEqual(rejected.exception.code, "unsupported_encoding")


@unittest.skipUnless(HAS_TRACE_RUNTIME, "illustrator-trace optional dependencies not installed")
class ColorTraceClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        assert trace is not None
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.output_root = self.root / "examples" / "output" / "illustrator" / "trace-practice"
        self.output_root.mkdir(parents=True)
        self.repo_root_patch = mock.patch.object(trace, "REPO_ROOT", self.root)
        self.repo_root_patch.start()

    def tearDown(self) -> None:
        self.repo_root_patch.stop()
        self.temporary_dir.cleanup()

    def make_ring_image(self) -> Path:
        source = self.root / "private-name-must-not-leak.png"
        image = trace.Image.new("RGB", (128, 128), "white")
        draw = trace.ImageDraw.Draw(image)
        draw.ellipse((16, 16, 112, 112), fill=(230, 35, 45))
        draw.ellipse((42, 42, 86, 86), fill=(20, 85, 220))
        image.save(source)
        return source

    def trace_args(
        self, source: Path, output_name: str, preset: str = "flat_8"
    ) -> argparse.Namespace:
        return argparse.Namespace(
            input=str(source),
            output_dir=str(self.output_root / output_name),
            presets=preset,
            commit_preset=preset,
            max_dimension=128,
        )

    def trace_argv(self, source: Path, output_name: str, preset: str = "flat_8") -> list[str]:
        return [
            "--input",
            str(source),
            "--output-dir",
            str(self.output_root / output_name),
            "--presets",
            preset,
            "--commit-preset",
            preset,
            "--max-dimension",
            "128",
        ]

    def fill_at(self, svg_path: Path, point: tuple[float, float]) -> str:
        root = ET.parse(svg_path).getroot()
        namespace = {"svg": svg_verifier.SVG_NAMESPACE}
        fill = "#ffffff"
        for path in root.findall("svg:path", namespace):
            parity = 0
            for segment in re.findall(r"M\s+(.+?)\s+Z", path.get("d", "")):
                points = [
                    (float(x), float(y)) for x, y in re.findall(r"(-?\d+)\s+(-?\d+)", segment)
                ]
                contour = trace.np.asarray(points, dtype=trace.np.float32)
                if trace.cv2.pointPolygonTest(contour, point, False) >= 0:
                    parity += 1
            if parity % 2 == 1:
                fill = path.get("fill", fill)
        return fill

    def test_restricted_svg_raster_quality_passes_and_requires_review(self) -> None:
        svg_path = self.root / "quality.svg"
        svg_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
            'viewBox="0 0 16 16"><rect width="16" height="16" fill="#ffffff"/>'
            '<path d="M 2 2 L 13 2 L 13 13 L 2 13 Z" fill="#e6232d" '
            'fill-rule="evenodd" stroke="none"/></svg>',
            encoding="utf-8",
        )
        target = trace.np.full((16, 16, 3), 255, dtype=trace.np.uint8)
        target[2:14, 2:14] = (230, 35, 45)

        passed = trace.measure_svg_raster_quality(
            svg_path,
            target,
            target_kind="in_memory_quantized_target",
        )
        review = trace.measure_svg_raster_quality(
            svg_path,
            trace.np.full_like(target, 255),
            target_kind="explicit_reference_work_rgb",
        )

        self.assertEqual("pass", passed["verdict"])
        self.assertEqual(1.0, passed["similarity"])
        self.assertEqual(1.0, passed["exact_pixel_match_ratio"])
        self.assertEqual("review_required", review["verdict"])
        self.assertEqual("explicit_reference_work_rgb", review["target_kind"])
        self.assertLess(review["similarity"], review["similarity_min"])
        self.assertNotIn(str(svg_path), json.dumps(passed))
        with self.assertRaisesRegex(ValueError, "target_kind"):
            trace.measure_svg_raster_quality(
                svg_path,
                target,
                target_kind="untrusted_target",
            )

    def test_real_color_trace_is_deterministic_topology_safe_and_manifested(self) -> None:
        source = self.make_ring_image()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = trace.main(self.trace_argv(source, "first"))
        first = json.loads(stdout.getvalue())
        second = trace.run_trace(self.trace_args(source, "second"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        first_svg = self.output_root / "first" / "flat_8.svg"
        second_svg = self.output_root / "second" / "flat_8.svg"
        first_evidence = svg_verifier.verify_svg_artifact(first_svg, expected_width=128)
        second_evidence = svg_verifier.verify_svg_artifact(second_svg, expected_width=128)
        self.assertEqual(first_evidence["sha256"], second_evidence["sha256"])
        self.assertEqual(first_evidence["embedded_raster_count"], 0)
        self.assertGreaterEqual(first_evidence["color_count"], 3)

        root = ET.parse(first_svg).getroot()
        paths = root.findall(f"{{{svg_verifier.SVG_NAMESPACE}}}path")
        self.assertTrue(any(path.get("d", "").count("M ") >= 2 for path in paths))
        center = self.fill_at(first_svg, (64.0, 64.0))
        ring = self.fill_at(first_svg, (94.0, 64.0))
        corner = self.fill_at(first_svg, (4.0, 4.0))
        center_rgb = tuple(bytes.fromhex(center.removeprefix("#")))
        ring_rgb = tuple(bytes.fromhex(ring.removeprefix("#")))
        corner_rgb = tuple(bytes.fromhex(corner.removeprefix("#")))
        self.assertGreater(center_rgb[2], max(center_rgb[0], center_rgb[1]))
        self.assertGreater(ring_rgb[0], max(ring_rgb[1], ring_rgb[2]))
        self.assertLess(max(corner_rgb) - min(corner_rgb), 8)

        report = json.loads((self.output_root / "first" / "trace_report.json").read_text())
        serialized_report = json.dumps(report)
        self.assertNotIn(source.name, serialized_report)
        self.assertTrue(report["artifacts"])
        self.assertTrue(all(artifact["verified"] for artifact in first["artifacts"]))
        self.assertTrue(
            all(not Path(artifact["path"]).is_absolute() for artifact in first["artifacts"])
        )
        for artifact in first["artifacts"]:
            published_path = self.root / artifact["path"]
            payload = published_path.read_bytes()
            self.assertEqual(artifact["bytes"], len(payload))
            self.assertEqual(artifact["sha256"], hashlib.sha256(payload).hexdigest())
        preset_svg = next(
            artifact for artifact in first["artifacts"] if artifact["role"] == "editable_svg"
        )
        final_svg = next(
            artifact
            for artifact in first["artifacts"]
            if artifact["role"] == "committed_editable_svg"
        )
        self.assertEqual(preset_svg["sha256"], final_svg["sha256"])
        self.assertEqual(first["final"]["preset"], "flat_8")
        quality = report["presets"][0]["svg_raster_quality"]
        quality_schema = json.loads(QUALITY_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual("starbridge.headless-svg-quality.v1", quality["schema_version"])
        self.assertGreaterEqual(quality["similarity"], 0.95)
        self.assertEqual(set(quality_schema["required"]), set(quality))
        self.assertEqual(
            set(quality_schema["properties"]["safety"]["required"]),
            set(quality["safety"]),
        )
        self.assertEqual(quality, first["final"]["svg_raster_quality"])
        reference_quality = report["presets"][0]["reference_svg_quality"]
        self.assertEqual("explicit_reference_work_rgb", reference_quality["target_kind"])
        self.assertGreaterEqual(reference_quality["similarity"], 0.0)
        self.assertLessEqual(reference_quality["similarity"], 1.0)
        self.assertEqual(reference_quality, first["final"]["reference_svg_quality"])
        second_report = json.loads((self.output_root / "second" / "trace_report.json").read_text())
        self.assertEqual(
            quality,
            second_report["presets"][0]["svg_raster_quality"],
        )
        self.assertEqual(
            reference_quality,
            second_report["presets"][0]["reference_svg_quality"],
        )

    def test_zero_path_generation_fails_without_publishing_partial_artifacts(self) -> None:
        source = self.make_ring_image()
        empty_preset = replace(trace.PRESETS["flat_8"], name="empty", min_area=1_000_000.0)
        output_dir = self.output_root / "failed"

        with (
            mock.patch.dict(trace.PRESETS, {"empty": empty_preset}, clear=False),
            self.assertRaises(svg_verifier.SvgArtifactError) as raised,
        ):
            trace.run_trace(self.trace_args(source, "failed", "empty"))

        self.assertEqual(raised.exception.code, "no_vector_paths")
        self.assertFalse(any(path.is_file() for path in output_dir.rglob("*")))

    def test_publish_failure_restores_previous_artifacts(self) -> None:
        staging_dir = self.output_root / "staging"
        final_dir = self.output_root / "published"
        staging_dir.mkdir()
        final_dir.mkdir()
        staged_first = staging_dir / "first.tmp"
        staged_second = staging_dir / "second.tmp"
        final_first = final_dir / "first.svg"
        final_second = final_dir / "second.png"
        staged_first.write_text("new first", encoding="utf-8")
        staged_second.write_text("new second", encoding="utf-8")
        final_first.write_text("old first", encoding="utf-8")
        final_second.write_text("old second", encoding="utf-8")
        real_replace = trace.os.replace
        failure_injected = False

        def flaky_replace(source: Path, destination: Path) -> None:
            nonlocal failure_injected
            if Path(source) == staged_second and not failure_injected:
                failure_injected = True
                raise OSError("injected publish failure")
            real_replace(source, destination)

        with (
            mock.patch.object(trace.os, "replace", side_effect=flaky_replace),
            self.assertRaises(trace.TraceRunError) as raised,
        ):
            trace.publish_verified_artifacts(
                [(staged_first, final_first), (staged_second, final_second)], staging_dir
            )

        self.assertEqual(raised.exception.code, "artifact_publish_failed")
        self.assertEqual(final_first.read_text(encoding="utf-8"), "old first")
        self.assertEqual(final_second.read_text(encoding="utf-8"), "old second")
        self.assertFalse(any(final_dir.glob(".trace-recovery-*")))

    def test_restore_failure_preserves_durable_recovery_backup(self) -> None:
        staging_dir = self.output_root / "double-failure-staging"
        final_dir = self.output_root / "double-failure-published"
        staging_dir.mkdir()
        final_dir.mkdir()
        staged_first = staging_dir / "first.tmp"
        staged_second = staging_dir / "second.tmp"
        final_first = final_dir / "first.svg"
        final_second = final_dir / "second.png"
        staged_first.write_text("new first", encoding="utf-8")
        staged_second.write_text("new second", encoding="utf-8")
        final_first.write_text("old first", encoding="utf-8")
        final_second.write_text("old second", encoding="utf-8")
        real_replace = trace.os.replace
        publish_failed = False

        def double_failure_replace(source: Path, destination: Path) -> None:
            nonlocal publish_failed
            source = Path(source)
            destination = Path(destination)
            if source == staged_second and not publish_failed:
                publish_failed = True
                raise OSError("injected publish failure")
            if source.parent.name.startswith(".trace-recovery-") and destination == final_first:
                raise OSError("injected restore failure")
            real_replace(source, destination)

        with (
            mock.patch.object(trace.os, "replace", side_effect=double_failure_replace),
            self.assertRaises(trace.TraceRunError) as raised,
        ):
            trace.publish_verified_artifacts(
                [(staged_first, final_first), (staged_second, final_second)], staging_dir
            )

        self.assertEqual(raised.exception.code, "artifact_rollback_failed")
        recovery_dirs = list(final_dir.glob(".trace-recovery-*"))
        self.assertEqual(len(recovery_dirs), 1)
        preserved_backups = list(recovery_dirs[0].iterdir())
        self.assertEqual(len(preserved_backups), 1)
        self.assertEqual(preserved_backups[0].read_text(encoding="utf-8"), "old first")
        self.assertEqual(final_second.read_text(encoding="utf-8"), "old second")
        shutil.rmtree(staging_dir)
        self.assertTrue(preserved_backups[0].is_file())

    def test_reused_output_removes_stale_managed_artifacts(self) -> None:
        source = self.make_ring_image()
        output_dir = self.output_root / "reused"
        first_args = self.trace_args(source, "reused")
        first_args.presets = "flat_8,flat_16"
        trace.run_trace(first_args)
        self.assertTrue((output_dir / "final_trace.svg").is_file())
        self.assertTrue((output_dir / "final_preview.png").is_file())
        self.assertTrue((output_dir / "flat_16.svg").is_file())
        self.assertTrue((output_dir / "flat_16_preview.png").is_file())

        uncommitted_args = self.trace_args(source, "reused")
        uncommitted_args.commit_preset = ""
        result = trace.run_trace(uncommitted_args)

        self.assertIsNone(result["final"])
        self.assertFalse((output_dir / "final_trace.svg").exists())
        self.assertFalse((output_dir / "final_preview.png").exists())
        self.assertFalse((output_dir / "flat_16.svg").exists())
        self.assertFalse((output_dir / "flat_16_preview.png").exists())
        self.assertFalse(any("final_" in artifact["path"] for artifact in result["artifacts"]))

    def test_input_contract_rejects_non_png_jpeg_and_oversized_images(self) -> None:
        disguised_bmp = self.root / "disguised-as-png.png"
        trace.Image.new("RGB", (32, 32), "red").save(disguised_bmp, format="BMP")

        with self.assertRaises(trace.TraceRunError) as unsupported:
            trace.run_trace(self.trace_args(disguised_bmp, "unsupported"))
        self.assertEqual(unsupported.exception.code, "unsupported_input_format")

        source = self.make_ring_image()
        with (
            mock.patch.object(trace, "MAX_SOURCE_PIXELS", 100),
            self.assertRaises(trace.TraceRunError) as oversized,
        ):
            trace.run_trace(self.trace_args(source, "oversized"))
        self.assertEqual(oversized.exception.code, "input_too_large")

        root_output_args = self.trace_args(source, "unused")
        root_output_args.output_dir = str(self.root / "examples" / "output" / "illustrator")
        with self.assertRaises(trace.TraceRunError) as outside_headless_root:
            trace.run_trace(root_output_args)
        self.assertEqual(outside_headless_root.exception.code, "output_outside_sandbox")

    def test_jpeg_exif_orientation_is_applied_before_vectorization(self) -> None:
        source = self.root / "oriented.jpg"
        image = trace.Image.new("RGB", (80, 40), "white")
        exif = image.getexif()
        exif[274] = 6
        image.save(source, format="JPEG", exif=exif)

        rgb, metadata = trace.load_image(str(source), trace.MAX_WORK_DIMENSION)

        self.assertEqual(rgb.shape[:2], (80, 40))
        self.assertEqual(metadata["original_width"], 40)
        self.assertEqual(metadata["original_height"], 80)

    def test_repository_relative_paths_normalize_root_aliases(self) -> None:
        aliased_root = self.root / "lexical-alias" / ".."
        artifact = self.output_root / "alias-test" / "artifact.svg"

        with mock.patch.object(trace, "REPO_ROOT", aliased_root):
            public_path = trace.repo_relative_path(artifact)

        self.assertEqual(
            public_path,
            "examples/output/illustrator/trace-practice/alias-test/artifact.svg",
        )

    def test_cli_failure_is_structured_and_does_not_echo_input_path(self) -> None:
        missing = self.root / "do-not-echo-this-name.png"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = trace.main(
                [
                    "--input",
                    str(missing),
                    "--output-dir",
                    str(self.output_root / "missing"),
                ]
            )

        response = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "input_unavailable")
        self.assertNotIn(str(missing), stdout.getvalue())

        missing_argument_stdout = io.StringIO()
        with contextlib.redirect_stdout(missing_argument_stdout):
            missing_argument_exit = trace.main([])
        missing_argument_response = json.loads(missing_argument_stdout.getvalue())
        self.assertEqual(missing_argument_exit, 1)
        self.assertEqual(missing_argument_response["error"]["code"], "invalid_arguments")

        private_preset = "hidden/source-name.svg"
        unknown_preset_stdout = io.StringIO()
        with contextlib.redirect_stdout(unknown_preset_stdout):
            unknown_preset_exit = trace.main(
                [
                    "--input",
                    str(self.make_ring_image()),
                    "--output-dir",
                    str(self.output_root / "unknown-preset"),
                    "--presets",
                    private_preset,
                ]
            )
        unknown_preset_response = json.loads(unknown_preset_stdout.getvalue())
        self.assertEqual(unknown_preset_exit, 1)
        self.assertEqual(unknown_preset_response["error"]["code"], "unknown_preset")
        self.assertNotIn(private_preset, unknown_preset_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
