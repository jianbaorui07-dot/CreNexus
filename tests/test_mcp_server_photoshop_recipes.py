from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.mcp_server import handle_request


REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", str(REPO_ROOT))


def request(message_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_request(payload)
    assert response is not None
    return response


class PhotoshopRecipeMcpTests(unittest.TestCase):
    def assert_no_private_paths(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_tools_list_contains_photoshop_recipe_tools(self) -> None:
        response = request(1, "tools/list")
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertTrue(
            {
                "photoshop.recipe_list",
                "photoshop.recipe_plan",
                "photoshop.recipe_validate",
                "photoshop.recipe_run",
                "photoshop.recipe_debug",
            }.issubset(names)
        )

    def test_recipe_run_dry_run_does_not_start_photoshop(self) -> None:
        with patch("starbridge_mcp.mcp_server.subprocess.run", side_effect=AssertionError("subprocess.run should not be called")):
            response = request(
                2,
                "tools/call",
                {"name": "photoshop.recipe_run", "arguments": {"dry_run": True}},
            )

        structured = response["result"]["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertTrue(structured["dry_run"])
        self.assertEqual("recipe_run", structured["action"])

    def test_recipe_run_real_execution_requires_confirm_write(self) -> None:
        response = request(
            3,
            "tools/call",
            {"name": "photoshop.recipe_run", "arguments": {"dry_run": False}},
        )

        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertIn("confirm_write", structured["message"])

    def test_recipe_plan_rejects_output_dir_outside_photoshop_sandbox(self) -> None:
        response = request(
            4,
            "tools/call",
            {
                "name": "photoshop.recipe_plan",
                "arguments": {"output_dir": "examples/output/illustrator"},
            },
        )

        structured = response["result"]["structuredContent"]
        self.assertIn("output_dir", structured["error"])

    def test_recipe_validate_is_sanitized_and_declares_manifest_gate(self) -> None:
        response = request(
            5,
            "tools/call",
            {"name": "photoshop.recipe_validate", "arguments": {"dry_run": True}},
        )

        structured = response["result"]["structuredContent"]
        names = {item["name"] for item in structured["validation"]}
        self.assertIn("manifest_schema", names)
        self.assertIn("no_private_path_leak", names)
        self.assert_no_private_paths(structured)


if __name__ == "__main__":
    unittest.main()
