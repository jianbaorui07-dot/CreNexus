from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "bridge_capability_matrix.py"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

spec = importlib.util.spec_from_file_location("bridge_capability_matrix", SCRIPT_PATH)
bridge_capability_matrix = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(bridge_capability_matrix)


EXPECTED_IDS = {
    "diagramforge",
    "comfyui",
    "blender",
    "cad_autocad",
    "photoshop",
    "illustrator",
    "capcut_jianying",
    "stable_fast_3d",
}


class BridgeCapabilityMatrixTest(unittest.TestCase):
    def test_registry_covers_all_expected_application_bridges(self) -> None:
        registry = bridge_capability_matrix.load_registry()
        bridge_ids = {bridge["bridge_id"] for bridge in registry["bridges"]}

        self.assertEqual(EXPECTED_IDS, bridge_ids)
        self.assertEqual([], bridge_capability_matrix.validate_registry(registry))
        for bridge in registry["bridges"]:
            self.assertIn("capability_categories", bridge)
            self.assertIn("evidence", bridge["capability_categories"])

    def test_markdown_output_mentions_each_application_family(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--markdown"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        for label in (
            "DiagramForge",
            "ComfyUI",
            "Blender",
            "Stable Fast 3D",
            "CAD / AutoCAD",
            "Photoshop",
            "Illustrator",
            "CapCut",
        ):
            self.assertIn(label, completed.stdout)

    def test_check_command_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn("bridge capability matrix passed", completed.stdout)

    def test_write_report_creates_json_and_markdown_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--write-report",
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )

            json_report = report_dir / "bridge_capability_matrix.json"
            markdown_report = report_dir / "bridge_capability_matrix.md"
            self.assertTrue(json_report.exists())
            self.assertTrue(markdown_report.exists())
            self.assertEqual(
                "1.0", json.loads(json_report.read_text(encoding="utf-8"))["schema_version"]
            )
            self.assertIn("ComfyUI", markdown_report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
