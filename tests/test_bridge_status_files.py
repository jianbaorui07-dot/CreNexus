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
    "display_name",
    "maturity",
    "platforms",
    "local_dependency",
    "required_env",
    "probe_supported",
    "write_supported",
    "safe_report_supported",
    "last_verified",
    "known_risks",
    "next_steps",
}
VALID_MATURITY = {"stable", "prototype", "planned", "research", "deprecated"}


class BridgeStatusFilesTest(unittest.TestCase):
    def test_expected_bridge_directories_exist(self) -> None:
        for directory in EXPECTED_BRIDGES:
            bridge_dir = REPO_ROOT / "examples" / directory
            self.assertTrue(bridge_dir.exists(), f"{directory} is missing")
            self.assertTrue(
                (bridge_dir / "README.md").exists(), f"{directory}/README.md is missing"
            )
            self.assertTrue(
                (bridge_dir / "bridge.json").exists(), f"{directory}/bridge.json is missing"
            )
            self.assertTrue(
                (bridge_dir / "bridge_status.json").exists(),
                f"{directory}/bridge_status.json is missing",
            )
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
            status_path = REPO_ROOT / "examples" / directory / "bridge_status.json"
            data = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(REQUIRED_FIELDS, set(data), status_path)
            self.assertEqual(bridge_id, data["bridge_id"])
            self.assertIn(data["maturity"], VALID_MATURITY)
            self.assertIn("Windows", data["platforms"], status_path)
            self.assertIsInstance(data["local_dependency"], list)
            self.assertGreater(len(data["local_dependency"]), 0)
            self.assertIsInstance(data["required_env"], list)
            self.assertIsInstance(data["probe_supported"], bool)
            self.assertIsInstance(data["write_supported"], bool)
            self.assertIsInstance(data["safe_report_supported"], bool)
            self.assertIsInstance(data["known_risks"], list)
            self.assertIsInstance(data["next_steps"], list)
            self.assertGreater(len(data["known_risks"]), 0)

    def test_expected_status_levels_are_conservative(self) -> None:
        expected = {
            "comfy_bridge": "prototype",
            "photoshop_bridge": "prototype",
            "cad_bridge": "prototype",
            "blender_bridge": "planned",
            "illustrator_bridge": "planned",
            "capcut_jianying_bridge": "research",
        }
        for directory, maturity in expected.items():
            status_path = REPO_ROOT / "examples" / directory / "bridge_status.json"
            data = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(maturity, data["maturity"], status_path)
            if maturity in {"planned", "research"}:
                self.assertFalse(data["write_supported"], status_path)


if __name__ == "__main__":
    unittest.main()
