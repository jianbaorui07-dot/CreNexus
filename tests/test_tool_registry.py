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

    def test_safe_only_filters_guarded_actions(self) -> None:
        capabilities = list_capabilities(include_guarded=False)
        self.assertTrue(capabilities)
        self.assertTrue(all(item["safe_default"] for item in capabilities))

    def test_bridge_filter_keeps_global_tools(self) -> None:
        capabilities = list_capabilities(bridge="comfyui")
        names = {item["name"] for item in capabilities}
        self.assertIn("starbridge.tools", names)
        self.assertIn("comfyui.system_probe", names)
        self.assertNotIn("photoshop.subject_extract", names)

    def test_capability_summary_is_safe_json(self) -> None:
        payload = capability_summary()
        text = json.dumps(payload, ensure_ascii=False)
        self.assert_no_private_paths(text)
        self.assertEqual(payload["action"], "tools")
        self.assertGreater(payload["capability_count"], 0)

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


if __name__ == "__main__":
    unittest.main()
