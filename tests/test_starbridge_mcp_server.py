from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp import server
from starbridge_mcp.mcp_server import handle_request


class StarBridgeMcpServerTests(unittest.TestCase):
    def test_package_scripts_include_mcp_entrypoints(self) -> None:
        package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        scripts = package["scripts"]
        for name in ("preflight", "starbridge:mcp", "starbridge:tools"):
            with self.subTest(name=name):
                self.assertIn(name, scripts)

    def test_safe_tools_include_expected_names(self) -> None:
        names = {tool["name"] for tool in server.tool_specs(safe_only=True)}
        for name in (
            "starbridge.status",
            "starbridge.tools",
            "comfyui.system_probe",
            "comfyui.workflow_validate",
            "jianying_capcut.draft_probe",
            "photoshop.session_info",
            "illustrator.document_info",
            "autocad_dxf.status",
            "autocad_dxf.validate_cad_plan",
            "autocad_dxf.summarize_plan",
        ):
            with self.subTest(name=name):
                self.assertIn(name, names)

    def test_tool_specs_have_schema_and_safety_flags(self) -> None:
        for tool in server.tool_specs(safe_only=True):
            with self.subTest(name=tool["name"]):
                self.assertTrue(tool["safe"])
                self.assertIn("input_schema", tool)
                self.assertEqual(tool["input_schema"]["type"], "object")

    def test_status_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "--json"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["safe_tool_count"], 5)

    def test_tools_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "tools", "--json", "--safe-only"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(all(tool["safe"] for tool in data["tools"]))

    def test_mcp_tools_list_request(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"])

    def test_mcp_ping_request(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 9, "method": "ping"})
        self.assertEqual(response["id"], 9)
        self.assertTrue(response["result"]["ok"])
        self.assertEqual(response["result"]["service"], "starbridge_mcp")

    def test_mcp_unknown_tool_returns_clear_error_payload(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "missing.tool", "arguments": {}},
            }
        )
        result = response["result"]
        self.assertFalse(result["ok"])
        self.assertIn("未知", result["message"])


if __name__ == "__main__":
    unittest.main()
