from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "starbridge-version-coordinator"
SERVER_PATH = PLUGIN_ROOT / "scripts" / "version_coordinator_mcp.py"


def load_server():
    spec = importlib.util.spec_from_file_location("starbridge_version_coordinator", SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = load_server()


class VersionCoordinatorPluginTests(unittest.TestCase):
    def test_plugin_manifest_and_mcp_are_self_contained(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text("utf-8"))
        mcp = json.loads((PLUGIN_ROOT / ".mcp.json").read_text("utf-8"))

        self.assertEqual("starbridge-version-coordinator", manifest["name"])
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)
        server = mcp["mcpServers"]["starbridge-version-coordinator"]
        self.assertEqual("python", server["command"])
        self.assertEqual(".", server["cwd"])
        self.assertEqual(["./scripts/version_coordinator_mcp.py"], server["args"])

    def test_adobe_versions_are_probe_routed_without_a_whitelist(self) -> None:
        plan = SERVER.build_plan(
            {
                "software_versions": {
                    "photoshop": "25.0",
                    "illustrator": "29.9",
                },
                "requested_software": ["photoshop", "illustrator"],
            }
        )
        routes = {item["id"]: item for item in plan["software"]}

        self.assertEqual("uxp-node-proxy", routes["photoshop"]["route"])
        self.assertEqual("uxp-node-proxy-v2", routes["illustrator"]["route"])
        self.assertEqual("probe_required", routes["illustrator"]["eligibility"])
        self.assertEqual(
            "capability-probe-not-version-whitelist",
            routes["illustrator"]["compatibility_policy"],
        )
        self.assertFalse(plan["safety"]["writes_configuration"])

    def test_unknown_versions_require_probe_and_never_include_paths(self) -> None:
        plan = SERVER.build_plan(
            {
                "requested_software": ["ps", "ai", "cad", "blender", "comfy", "capcut"],
                "starbridge_generation": "v7",
            }
        )
        encoded = json.dumps(plan, ensure_ascii=False)

        self.assertTrue(all(item["version"] == "unknown" for item in plan["software"]))
        self.assertNotIn("C:\\Users\\", encoded)
        self.assertNotIn("/Users/", encoded)
        self.assertNotIn("/home/", encoded)

    def test_customer_workflow_is_exact_first_and_never_uses_image_trace(self) -> None:
        plan = SERVER.build_plan({"requested_software": ["illustrator"]})
        workflow = plan["customer_workflow"]

        self.assertEqual("exact-pixel-first-then-drawn-vector", workflow["policy"])
        self.assertFalse(workflow["image_trace_allowed"])
        self.assertEqual(
            ["pixel-level-print", "drawn-vector"],
            [stage["id"] for stage in workflow["stages"]],
        )
        self.assertFalse(plan["safety"]["uses_image_trace"])

        rule_files = [
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "exact-pixel-vectorization.md",
            PLUGIN_ROOT / "skills" / "starbridge-version-coordination" / "SKILL.md",
        ]
        for path in rule_files:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("精确重建", text)
                self.assertTrue("Image Trace" in text or "图像描摹" in text)

    def test_migration_is_additive_and_preserves_previous_outputs(self) -> None:
        migration = SERVER.build_migration("v5", "v9")

        self.assertEqual(["v6", "v7", "v8", "v9"], [step["to"] for step in migration["steps"]])
        self.assertTrue(all(step["preserve_previous_outputs"] for step in migration["steps"]))
        self.assertTrue(
            all(not step["requires_customer_asset_reupload"] for step in migration["steps"])
        )

    def test_versions_reject_paths_or_free_form_text(self) -> None:
        with self.assertRaises(SERVER.CoordinatorError):
            SERVER.build_plan({"software_versions": {"photoshop": "C:\\Program Files\\Adobe"}})

    def test_mcp_stdio_lists_and_calls_tools(self) -> None:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "starbridge_config.plan",
                    "arguments": {"software_versions": {"photoshop": "25.5"}},
                },
            },
        ]
        completed = subprocess.run(
            [sys.executable, str(SERVER_PATH)],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        responses = [json.loads(line) for line in completed.stdout.splitlines()]

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(3, len(responses))
        self.assertEqual(3, len(responses[1]["result"]["tools"]))
        self.assertFalse(responses[2]["result"]["isError"])
        self.assertEqual("plan", responses[2]["result"]["structuredContent"]["action"])

    def test_marketplace_entry_has_required_policy(self) -> None:
        marketplace = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text("utf-8")
        )
        entry = marketplace["plugins"][0]

        self.assertEqual("starbridge-version-coordinator", entry["name"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])
        self.assertEqual("Productivity", entry["category"])


if __name__ == "__main__":
    unittest.main()
