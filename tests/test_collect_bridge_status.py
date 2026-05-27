from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "collect_bridge_status.py"


class CollectBridgeStatusTest(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_default_outputs_markdown_table(self) -> None:
        completed = self.run_script()
        self.assertIn("| bridge_id | name | status |", completed.stdout)
        self.assertIn("comfyui", completed.stdout)
        self.assertIn("capcut_jianying", completed.stdout)

    def test_json_output_is_valid(self) -> None:
        completed = self.run_script("--json")
        data = json.loads(completed.stdout)
        bridge_ids = {bridge["bridge_id"] for bridge in data["bridges"]}
        self.assertIn("photoshop", bridge_ids)
        self.assertIn("illustrator", bridge_ids)
        for bridge in data["bridges"]:
            self.assertIn("_path", bridge)
            self.assertTrue(bridge["_path"].endswith("bridge.json"))
            self.assertIn(bridge["status"], {"stable", "experimental", "research", "planned"})

    def test_markdown_flag_outputs_table(self) -> None:
        completed = self.run_script("--markdown")
        self.assertIn("| bridge_id |", completed.stdout)
        self.assertIn("| --- |", completed.stdout)


if __name__ == "__main__":
    unittest.main()
