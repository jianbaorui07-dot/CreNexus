from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_REPORT_FIELDS = {"bridge_id", "ok", "detected", "errors", "warnings", "safe_to_commit"}


class ProbeReportFormatTest(unittest.TestCase):
    def test_sample_reports_match_probe_contract(self) -> None:
        sample_paths = sorted((REPO_ROOT / "examples").glob("*_bridge/sample_report.example.json"))
        self.assertGreaterEqual(len(sample_paths), 6)
        for sample_path in sample_paths:
            data = json.loads(sample_path.read_text(encoding="utf-8"))
            self.assertEqual(REQUIRED_REPORT_FIELDS, set(data), sample_path)
            self.assertIsInstance(data["bridge_id"], str)
            self.assertIsInstance(data["ok"], bool)
            self.assertIsInstance(data["detected"], dict)
            self.assertIsInstance(data["errors"], list)
            self.assertIsInstance(data["warnings"], list)
            self.assertIs(data["safe_to_commit"], True, sample_path)

    def test_sample_reports_do_not_contain_private_paths(self) -> None:
        for sample_path in (REPO_ROOT / "examples").glob("*_bridge/sample_report.example.json"):
            text = sample_path.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users\\", text)
            self.assertNotIn("E:" + "\\", text)
            self.assertNotIn("D:" + "\\", text)


if __name__ == "__main__":
    unittest.main()
