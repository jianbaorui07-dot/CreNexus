from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".codex" / "skills" / "starbridge-smart-vector-refinement"
QUALITY_RUNTIME_AVAILABLE = all(
    importlib.util.find_spec(name) is not None for name in ("cv2", "numpy", "PIL")
)


def load_generator():
    path = SKILL_ROOT / "scripts" / "trace_curve_candidate.py"
    spec = importlib.util.spec_from_file_location("smart_vector_trace_candidate", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load curve candidate generator.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_evaluator():
    path = SKILL_ROOT / "scripts" / "evaluate_candidate.py"
    spec = importlib.util.spec_from_file_location("smart_vector_evaluate_candidate", path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load curve candidate evaluator.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SmartVectorRefinementSkillTests(unittest.TestCase):
    def test_skill_metadata_and_resources_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        quality = (SKILL_ROOT / "references" / "quality-gates.md").read_text(encoding="utf-8")
        self.assertIn("name: starbridge-smart-vector-refinement", skill)
        self.assertIn("actual SVG-render score", skill)
        self.assertIn("difference_percent", quality)
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "scripts" / "evaluate_candidate.py").is_file())

    def test_vtracer_normalization_flattens_translation_and_passes_verifier(self) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw.svg"
            output = root / "vector.svg"
            raw.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
                '<path d="M 0 0 C 4 0 8 0 8 4 C 8 8 4 8 0 8 C 0 4 0 2 0 0 Z" '
                'fill="#aa5533" transform="translate(2,3)"/></svg>',
                encoding="utf-8",
            )

            result = generator.normalize_vtracer_svg(raw, output)
            evidence = verify_svg_artifact(output, expected_width=20, expected_height=20)

            self.assertEqual(result["path_count"], 1)
            self.assertNotIn("transform", output.read_text(encoding="utf-8"))
            self.assertEqual(evidence["embedded_raster_count"], 0)
            self.assertEqual(evidence["external_reference_count"], 0)
            self.assertGreater(evidence["curve_segment_count"], 0)

    @unittest.skipUnless(QUALITY_RUNTIME_AVAILABLE, "vector quality runtime is optional")
    def test_actual_render_evaluator_reports_passing_metrics(self) -> None:
        from PIL import Image

        evaluator = load_evaluator()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "reference.png"
            rendered = root / "rendered.png"
            svg = root / "vector.svg"
            Image.new("RGB", (16, 16), "#aa5533").save(reference)
            Image.new("RGB", (16, 16), "#aa5533").save(rendered)
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
                'viewBox="0 0 16 16"><path fill="#aa5533" fill-rule="evenodd" '
                'stroke="none" d="M 0 0 C 8 0 16 0 16 8 C 16 16 8 16 0 16 '
                'C 0 8 0 4 0 0 Z"/></svg>',
                encoding="utf-8",
            )

            report = evaluator.evaluate_candidate(
                candidate_id="public-test",
                reference_path=reference,
                rendered_path=rendered,
                svg_path=svg,
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["visual"]["difference_percent"], 0.0)
            self.assertEqual(report["vector"]["embedded_rasters"], 0)
            self.assertTrue(all(report["gates"].values()))


if __name__ == "__main__":
    unittest.main()
