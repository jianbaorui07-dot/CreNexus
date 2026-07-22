from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from starbridge_mcp.core.tool_registry import CAPABILITIES, capability_summary, list_capabilities

REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


class ToolRegistryTests(unittest.TestCase):
    def assert_no_private_paths(self, text: str) -> None:
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_registry_has_safe_and_guarded_capabilities(self) -> None:
        self.assertGreaterEqual(len(CAPABILITIES), 10)
        risks = {capability.risk_level for capability in CAPABILITIES}
        self.assertIn("safe_read_only", risks)
        self.assertIn("guarded_local_write", risks)
        self.assertTrue(any(capability.source_projects for capability in CAPABILITIES))

    def test_registry_lists_stable_experimental_and_planned_statuses(self) -> None:
        capabilities = list_capabilities()
        statuses = {item["current_status"] for item in capabilities}
        self.assertIn("stable", statuses)
        self.assertIn("experimental", statuses)
        self.assertIn("planned", statuses)

    def test_safe_only_filters_guarded_actions(self) -> None:
        capabilities = list_capabilities(include_guarded=False)
        self.assertTrue(capabilities)
        self.assertTrue(all(item["safe_default"] for item in capabilities))

    def test_bridge_filter_keeps_global_tools(self) -> None:
        capabilities = list_capabilities(bridge="comfyui")
        names = {item["name"] for item in capabilities}
        self.assertIn("starbridge.tools", names)
        self.assertIn("starbridge.safe_roots", names)
        self.assertIn("starbridge.evidence_init", names)
        self.assertIn("starbridge.job_status", names)
        self.assertIn("comfyui.system_probe", names)
        self.assertIn("comfyui.queue_snapshot", names)
        self.assertNotIn("photoshop.subject_extract", names)

    def test_diagramforge_bridge_filter_exposes_native_tools(self) -> None:
        capabilities = list_capabilities(bridge="diagramforge", include_guarded=False)
        names = {item["name"] for item in capabilities}

        self.assertIn("drawio.probe", names)
        self.assertIn("drawio.plan", names)
        self.assertIn("drawio.handoff.plan", names)
        self.assertNotIn("drawio.create", names)

    def test_capability_summary_is_safe_json(self) -> None:
        payload = capability_summary()
        text = json.dumps(payload, ensure_ascii=False)
        self.assert_no_private_paths(text)
        self.assertEqual(payload["action"], "tools")
        self.assertEqual("starbridge.capabilities.v2", payload["manifest_version"])
        self.assertGreater(payload["capability_count"], 0)
        self.assertIn("bridge_categories", payload)
        self.assertIn("bridge_overview", payload)
        self.assertIn("planner_hints", payload)
        self.assertIn("evidence_init", payload["bridge_categories"]["all"])
        self.assertIn("safe_roots", payload["bridge_categories"]["all"])
        self.assertIn("starbridge.recipe_evidence", payload["planner_hints"]["evidence_tools"])

    def test_capability_summary_includes_bridge_overview(self) -> None:
        payload = capability_summary(bridge="photoshop")
        overview = payload["bridge_overview"]

        self.assertIn("all", overview)
        self.assertIn("photoshop", overview)
        self.assertGreater(overview["photoshop"]["tool_count"], 0)
        self.assertGreater(overview["photoshop"]["safe_default_tool_count"], 0)
        self.assertGreater(overview["photoshop"]["guarded_tool_count"], 0)
        self.assertIn("photoshop.recipe_plan", overview["photoshop"]["safe_tools"])
        self.assertIn("photoshop.recipe_run", overview["photoshop"]["guarded_tools"])

    def test_server_tools_action_outputs_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "tools", "--json", "--safe-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_no_private_paths(completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["action"], "tools")
        self.assertTrue(all(item["safe_default"] for item in payload["capabilities"]))
        names = {item["name"] for item in payload["capabilities"]}
        self.assertIn("starbridge.evidence_init", names)
        self.assertIn("starbridge.evidence_validate", names)
        self.assertIn("starbridge.job_status", names)
        self.assertIn("starbridge.operation_context", names)
        self.assertIn("starbridge.recipe_evidence", names)
        self.assertIn("comfyui.queue_snapshot", names)

    def test_photoshop_recipe_capabilities_are_registered(self) -> None:
        capabilities = list_capabilities(bridge="photoshop")
        by_name = {item["name"]: item for item in capabilities}

        for name in (
            "photoshop.recipe_list",
            "photoshop.recipe_plan",
            "photoshop.recipe_validate",
            "photoshop.recipe_run",
            "photoshop.recipe_debug",
        ):
            with self.subTest(tool=name):
                self.assertIn(name, by_name)

        self.assertTrue(by_name["photoshop.recipe_plan"]["safe_default"])
        self.assertFalse(by_name["photoshop.recipe_run"]["safe_default"])
        self.assertEqual("guarded_local_write", by_name["photoshop.recipe_run"]["risk_level"])

    def test_deepened_bridge_capabilities_are_safe_default(self) -> None:
        for bridge, expected in {
            "blender": "blender.scene_plan",
            "illustrator": "illustrator.preflight",
            "jianying_capcut": "jianying_capcut.draft_structure",
        }.items():
            with self.subTest(bridge=bridge):
                capabilities = list_capabilities(bridge=bridge, include_guarded=False)
                by_name = {item["name"]: item for item in capabilities}
                self.assertIn(expected, by_name)
                self.assertTrue(by_name[expected]["safe_default"])
                self.assertEqual("safe_read_only", by_name[expected]["risk_level"])

        blender_capabilities = list_capabilities(bridge="blender", include_guarded=False)
        blender_by_name = {item["name"]: item for item in blender_capabilities}
        self.assertIn("blender.reference_reconstruction_plan", blender_by_name)
        self.assertTrue(blender_by_name["blender.reference_reconstruction_plan"]["safe_default"])
        self.assertEqual(
            "safe_read_only",
            blender_by_name["blender.reference_reconstruction_plan"]["risk_level"],
        )


if __name__ == "__main__":
    unittest.main()
