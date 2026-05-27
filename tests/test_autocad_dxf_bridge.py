from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.bridges.autocad_dxf import (
    create_dxf_plan,
    status,
    summarize_plan,
    validate_cad_plan,
    write_dxf,
)


BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


def minimal_plan() -> dict:
    return {
        "units": "mm",
        "layers": [{"name": "OUTLINE", "color": 7}, {"name": "TEXT", "color": 2}],
        "entities": [
            {"type": "rectangle", "layer": "OUTLINE", "x": 0, "y": 0, "width": 1000, "height": 500},
            {"type": "line", "layer": "OUTLINE", "start": [0, 0], "end": [1000, 500]},
            {"type": "circle", "layer": "OUTLINE", "center": [500, 250], "radius": 80},
            {"type": "polyline", "layer": "OUTLINE", "points": [[0, 0], [100, 0], [100, 100]]},
            {"type": "text", "layer": "TEXT", "position": [20, 620], "height": 120, "value": "demo"},
        ],
        "output": "demo.dxf",
    }


class AutoCadDxfBridgeTests(unittest.TestCase):
    def assert_schema(self, result: dict, action: str) -> None:
        self.assertEqual({"ok", "bridge", "action", "message", "details", "warnings", "next_steps"}, set(result))
        self.assertEqual("autocad_dxf", result["bridge"])
        self.assertEqual(action, result["action"])
        text = json.dumps(result, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_status_does_not_require_autocad_or_ezdxf(self) -> None:
        result = status()
        self.assert_schema(result, "status")
        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["requires_autocad"])

    def test_validate_cad_plan_rejects_invalid_inputs(self) -> None:
        for bad_plan in ("not a dict", {}, {"units": "mm"}, {"units": "mm", "entities": [{"type": "unknown"}]}):
            with self.subTest(plan=bad_plan):
                result = validate_cad_plan(bad_plan)
                self.assert_schema(result, "validate_cad_plan")
                self.assertFalse(result["ok"])

    def test_validate_cad_plan_accepts_legal_minimal_plan(self) -> None:
        result = validate_cad_plan(minimal_plan())
        self.assert_schema(result, "validate_cad_plan")
        self.assertTrue(result["ok"])
        self.assertEqual(5, result["details"]["entity_count"])

    def test_create_dxf_plan_accepts_prompt_and_spec(self) -> None:
        prompt_result = create_dxf_plan("生成一个矩形边框和标题文字")
        self.assert_schema(prompt_result, "create_dxf_plan")
        self.assertTrue(prompt_result["ok"])

        spec_result = create_dxf_plan(minimal_plan())
        self.assert_schema(spec_result, "create_dxf_plan")
        self.assertTrue(spec_result["ok"])

    def test_summarize_plan_counts_entities(self) -> None:
        result = summarize_plan(minimal_plan())
        self.assert_schema(result, "summarize_plan")
        self.assertTrue(result["ok"])
        self.assertEqual(5, result["details"]["entity_count"])
        self.assertEqual(1, result["details"]["entity_types"]["line"])
        self.assertEqual(1, result["details"]["entity_types"]["rectangle"])

    def test_write_dxf_dry_run_does_not_write_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dry_run.dxf"
            result = write_dxf(minimal_plan(), output, dry_run=True)
            self.assert_schema(result, "write_dxf")
            self.assertTrue(result["ok"])
            self.assertFalse(output.exists())

    def test_write_dxf_rejects_output_outside_examples_cad_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "blocked.dxf"
            result = write_dxf(minimal_plan(), output, dry_run=False)
            self.assert_schema(result, "write_dxf")
            self.assertFalse(result["ok"])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
