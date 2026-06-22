from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CAD_SRC = REPO_ROOT / "cad-mcp-autocad" / "src"
sys.path.insert(0, str(CAD_SRC))

from nlp_processor import NLPProcessor  # noqa: E402


class NLPProcessorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.processor = NLPProcessor()

    def test_missing_color_keeps_cad_default(self) -> None:
        self.assertIsNone(self.processor.extract_color_from_command(None))
        self.assertIsNone(self.processor.extract_color_from_command("画一条线从 (0,0) 到 (1,1)"))

    def test_color_names_and_indices_are_supported(self) -> None:
        self.assertEqual(self.processor.extract_color_from_command("红色圆"), 1)
        self.assertEqual(self.processor.extract_color_from_command("blue line"), 5)
        self.assertEqual(self.processor.extract_color_from_command("30"), 30)

    def test_hatch_command_parses_points_pattern_and_scale(self) -> None:
        parsed = self.processor.parse_command("绘制填充 (0,0), (10,0), (10,10) 图案 ANSI31 比例 2")

        self.assertEqual(parsed["type"], "draw_hatch")
        self.assertEqual(len(parsed["points"]), 3)
        self.assertEqual(parsed["pattern_name"], "ANSI31")
        self.assertEqual(parsed["scale"], 2.0)

    def test_dimension_command_parses_points(self) -> None:
        parsed = self.processor.parse_command("添加标注 (0,0), (10,0), (5,2)")

        self.assertEqual(parsed["type"], "add_dimension")
        self.assertEqual(parsed["start_point"], (0.0, 0.0, 0.0))
        self.assertEqual(parsed["end_point"], (10.0, 0.0, 0.0))
        self.assertEqual(parsed["text_position"], (5.0, 2.0, 0.0))

    def test_text_command_uses_content_label(self) -> None:
        parsed = self.processor.parse_command('添加文本 内容："Hello" 在 (1,2)')

        self.assertEqual(parsed["type"], "draw_text")
        self.assertEqual(parsed["text"], "hello")
        self.assertEqual(parsed["position"], (1.0, 2.0, 0.0))


if __name__ == "__main__":
    unittest.main()
