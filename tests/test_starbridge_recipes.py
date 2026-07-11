from __future__ import annotations

import json
import unittest

from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


def request(message_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_request(payload)
    assert response is not None
    return response


class StarBridgeRecipeTests(unittest.TestCase):
    def assert_no_private_paths(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_recipe_tools_are_listed_and_safe_default(self) -> None:
        response = request(1, "tools/list")
        by_name = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertIn("starbridge.recipe_list", by_name)
        self.assertIn("starbridge.recipe_plan", by_name)
        self.assertIn("starbridge.recipe_evidence", by_name)
        self.assertTrue(by_name["starbridge.recipe_plan"]["annotations"]["safeDefault"])
        self.assertFalse(by_name["starbridge.recipe_plan"]["annotations"]["requiresConfirmation"])

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=False)}
        self.assertIn("starbridge.recipe_list", capabilities)
        self.assertIn("starbridge.recipe_plan", capabilities)
        self.assertIn("starbridge.recipe_evidence", capabilities)

    def test_recipe_list_filters_by_bridge(self) -> None:
        response = request(
            2,
            "tools/call",
            {"name": "starbridge.recipe_list", "arguments": {"bridge": "comfyui"}},
        )
        structured = response["result"]["structuredContent"]
        recipe_ids = {recipe["recipe_id"] for recipe in structured["recipes"]}
        self.assertEqual({"comfyui_txt2img_lifecycle"}, recipe_ids)
        self.assert_no_private_paths(structured)

    def test_recipe_plan_returns_action_plan_without_execution(self) -> None:
        response = request(
            3,
            "tools/call",
            {
                "name": "starbridge.recipe_plan",
                "arguments": {"recipe_id": "blender_scene_evidence"},
            },
        )
        structured = response["result"]["structuredContent"]
        plan = structured["plan"]

        self.assertTrue(structured["ok"])
        self.assertEqual("blender", structured["bridge"])
        self.assertTrue(plan["dry_run"])
        self.assertIn("no_arbitrary_python", plan["quality_gates"])
        self.assertIn("starbridge.evidence_init", plan["action_plan"]["tool_sequence"])
        transaction = plan["transaction"]
        self.assertEqual("planned", transaction["status"])
        self.assertEqual("L2", transaction["risk_level"])
        self.assertIn("user_confirmation_before_write", transaction["required_approvals"])
        self.assertEqual("frontier", transaction["model_policy"]["planner"])
        self.assert_no_private_paths(structured)

    def test_unknown_recipe_is_structured_error(self) -> None:
        response = request(
            4,
            "tools/call",
            {"name": "starbridge.recipe_plan", "arguments": {"recipe_id": "missing"}},
        )
        structured = response["result"]["structuredContent"]

        self.assertFalse(structured["ok"])
        self.assertIn("available_recipes", structured)

    def test_recipe_evidence_returns_standard_manifest_preview(self) -> None:
        response = request(
            5,
            "tools/call",
            {
                "name": "starbridge.recipe_evidence",
                "arguments": {"recipe_id": "comfyui_txt2img_lifecycle"},
            },
        )
        structured = response["result"]["structuredContent"]
        manifest = structured["manifest"]

        self.assertTrue(structured["ok"])
        self.assertEqual("comfyui", manifest["bridge"])
        self.assertEqual("recipe_evidence", manifest["action"])
        self.assertTrue(manifest["quality_gates"])
        self.assertTrue(manifest["asset_manifest"])
        self.assertIn("recipe_id", manifest["input_summary"])
        self.assert_no_private_paths(structured)


if __name__ == "__main__":
    unittest.main()
