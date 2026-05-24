from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BRIDGES = {
    "comfy_bridge": "comfyui",
    "photoshop_bridge": "photoshop",
    "cad_bridge": "cad_autocad",
    "blender_bridge": "blender",
    "illustrator_bridge": "illustrator",
    "capcut_jianying_bridge": "capcut_jianying",
}
REQUIRED_FIELDS = {
    "bridge_id",
    "name",
    "status",
    "platform",
    "requires",
    "entrypoints",
    "supported_tasks",
    "unsupported_tasks",
    "safety_notes",
}
VALID_STATUS = {"stable", "experimental", "planned", "research"}


class BridgeStatusFilesTest(unittest.TestCase):
    def test_expected_bridge_directories_exist(self) -> None:
        for directory in EXPECTED_BRIDGES:
            bridge_dir = REPO_ROOT / "examples" / directory
            self.assertTrue(bridge_dir.exists(), f"{directory} is missing")
            self.assertTrue((bridge_dir / "README.md").exists(), f"{directory}/README.md is missing")
            self.assertTrue((bridge_dir / "bridge.json").exists(), f"{directory}/bridge.json is missing")
            self.assertTrue((bridge_dir / "bridge_status.json").exists(), f"{directory}/bridge_status.json is missing")
            self.assertTrue(
                (bridge_dir / "probe.py").exists() or (bridge_dir / "probe.ps1").exists(),
                f"{directory} probe script is missing",
            )
            self.assertTrue(
                (bridge_dir / "sample_report.example.json").exists(),
                f"{directory}/sample_report.example.json is missing",
            )

    def test_bridge_manifest_schema_and_values(self) -> None:
        for directory, bridge_id in EXPECTED_BRIDGES.items():
            status_path = REPO_ROOT / "examples" / directory / "bridge.json"
            data = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(REQUIRED_FIELDS, set(data), status_path)
            self.assertEqual(bridge_id, data["bridge_id"])
            self.assertIn(data["status"], VALID_STATUS)
            self.assertEqual(["Windows"], data["platform"], status_path)
            self.assertIsInstance(data["requires"], list)
            self.assertGreater(len(data["requires"]), 0)
            self.assertIsInstance(data["entrypoints"], dict)
            self.assertIn("probe", data["entrypoints"], status_path)
            self.assertIsInstance(data["supported_tasks"], list)
            self.assertIsInstance(data["unsupported_tasks"], list)
            self.assertIsInstance(data["safety_notes"], list)
            self.assertGreater(len(data["safety_notes"]), 0)

    def test_expected_status_levels_are_conservative(self) -> None:
        expected = {
            "comfy_bridge": "experimental",
            "photoshop_bridge": "experimental",
            "cad_bridge": "experimental",
            "blender_bridge": "planned",
            "illustrator_bridge": "planned",
            "capcut_jianying_bridge": "research",
        }
        for directory, status in expected.items():
            status_path = REPO_ROOT / "examples" / directory / "bridge.json"
            data = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status, data["status"], status_path)
            if status in {"planned", "research"}:
                self.assertNotIn("run", data["entrypoints"], status_path)


if __name__ == "__main__":
    unittest.main()
