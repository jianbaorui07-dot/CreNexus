from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

from starbridge_mcp.mcp_server import handle_request, serve_stdio


REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


def request(message_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_request(payload)
    assert response is not None
    return response


class McpStdioServerTests(unittest.TestCase):
    def assert_no_private_paths(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_initialize_declares_tools_capability(self) -> None:
        response = request(
            1,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        )

        self.assertEqual("2.0", response["jsonrpc"])
        self.assertEqual("2025-06-18", response["result"]["protocolVersion"])
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list_contains_safe_starbridge_tools(self) -> None:
        response = request(2, "tools/list")

        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("starbridge.status", names)
        self.assertIn("starbridge.tools", names)
        self.assertIn("starbridge.safe_roots", names)
        self.assertIn("comfyui.system_probe", names)
        self.assertIn("blender.environment_probe", names)
        self.assertIn("cad_autocad.environment_probe", names)
        self.assertIn("photoshop.session_info", names)
        self.assertIn("illustrator.document_info", names)
        self.assertIn("jianying_capcut.draft_probe", names)
        self.assertIn("autocad_dxf.validate_cad_plan", names)
        self.assertTrue(all("inputSchema" in tool for tool in tools))
        self.assert_no_private_paths(response)

    def test_tools_call_returns_structured_content(self) -> None:
        response = request(
            3,
            "tools/call",
            {"name": "starbridge.tools", "arguments": {"safe_only": True}},
        )

        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual("tools", result["structuredContent"]["action"])
        self.assertTrue(all(item["safe_default"] for item in result["structuredContent"]["capabilities"]))
        self.assertTrue(all("current_status" in item for item in result["structuredContent"]["capabilities"]))
        self.assert_no_private_paths(response)

    def test_safe_roots_tool_returns_repo_relative_boundaries(self) -> None:
        response = request(
            32,
            "tools/call",
            {"name": "starbridge.safe_roots", "arguments": {"bridge": "photoshop"}},
        )
        structured = response["result"]["structuredContent"]

        self.assertTrue(structured["ok"])
        self.assertEqual("safe_roots", structured["action"])
        paths = {item["path"] for item in structured["roots"]}
        self.assertIn("examples/output/photoshop", paths)
        self.assertNotIn(str(REPO_ROOT), json.dumps(structured, ensure_ascii=False))
        self.assert_no_private_paths(response)

    def test_direct_bridge_probe_tools_return_structured_content(self) -> None:
        tool_calls = [
            ("blender.environment_probe", {}),
            ("cad_autocad.environment_probe", {}),
            ("jianying_capcut.draft_probe", {}),
            ("photoshop.session_info", {"probe_com": False}),
            ("illustrator.document_info", {"probe_com": False}),
        ]
        for tool_name, arguments in tool_calls:
            with self.subTest(tool=tool_name):
                response = request(30, "tools/call", {"name": tool_name, "arguments": arguments})
                structured = response["result"]["structuredContent"]

                self.assertIn("ok", structured)
                self.assertIn("bridge", structured)
                self.assertFalse(response["result"]["isError"])
                self.assert_no_private_paths(response)

    def test_comfyui_system_probe_is_mcp_tool_even_when_service_is_down(self) -> None:
        response = request(
            31,
            "tools/call",
            {"name": "comfyui.system_probe", "arguments": {"comfy_url": "http://127.0.0.1:9", "timeout": 1}},
        )
        structured = response["result"]["structuredContent"]

        self.assertEqual("comfyui", structured["bridge"])
        self.assertEqual("system_probe", structured["action"])
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("unavailable", structured["details"]["report"]["status"])
        self.assert_no_private_paths(response)

    def test_dxf_write_requires_confirmation_for_real_write(self) -> None:
        plan = {
            "units": "mm",
            "entities": [{"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10}],
        }
        response = request(
            4,
            "tools/call",
            {
                "name": "autocad_dxf.write_dxf",
                "arguments": {
                    "plan": plan,
                    "output_path": "examples/cad/output/mcp_test.dxf",
                    "dry_run": False,
                },
            },
        )

        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertIn("confirm_write", structured["message"])

    def test_stdio_loop_handles_initialize_and_list(self) -> None:
        input_stream = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n"
        )
        output_stream = io.StringIO()

        exit_code = serve_stdio(input_stream, output_stream)

        self.assertEqual(0, exit_code)
        lines = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual([1, 2], [line["id"] for line in lines])
        self.assertIn("tools", lines[1]["result"])

    def test_module_runs_as_stdio_process(self) -> None:
        initialize = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        tools_list = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.mcp_server"],
            cwd=REPO_ROOT,
            input=f"{initialize}\n{tools_list}\n",
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        lines = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(2, len(lines))
        self.assertEqual(1, lines[0]["id"])
        self.assertEqual(2, lines[1]["id"])
        self.assert_no_private_paths(lines)


if __name__ == "__main__":
    unittest.main()
