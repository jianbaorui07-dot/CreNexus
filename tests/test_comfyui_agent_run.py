from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from examples.comfy_bridge.workflow_agent import agent_run
from starbridge_mcp.mcp_server import handle_request

BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


class ComfyAgentRunTests(unittest.TestCase):
    def assert_no_private_paths(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_agent_run_without_confirm_run_does_not_submit(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.submit_workflow") as submit:
            result = agent_run({"goal": "生成一张国风 Q版 明代街市人物场景图"})

        submit.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertFalse(result["submitted"])
        self.assertIsNone(result["prompt_id"])
        self.assertIn("confirm_run=true", " ".join(result["warnings"]))

    def test_agent_run_confirm_true_allows_submit_and_sanitizes_manifest(self) -> None:
        fake_submission = {
            "ok": True,
            "prompt_id": "abc-123",
            "job_status": {
                "state": "completed",
                "history_available": True,
                "output_manifest": {
                    "prompt_id": "abc-123",
                    "image_count": 1,
                    "images": [
                        {
                            "node_id": "9",
                            "filename": "agent_00001.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ],
                },
            },
        }
        with patch(
            "examples.comfy_bridge.workflow_agent.submit_workflow", return_value=fake_submission
        ) as submit:
            result = agent_run(
                {
                    "goal": "生成一张国风 Q版 明代街市人物场景图",
                    "confirm_run": True,
                    "checkpoint": "placeholder.safetensors",
                }
            )

        submit.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual("confirmed", result["mode"])
        self.assertTrue(result["submitted"])
        self.assertEqual("abc-123", result["prompt_id"])
        self.assertEqual(1, result["output_manifest"]["image_count"])
        self.assert_no_private_paths(result)

    def test_mcp_tools_list_contains_agent_workflow_tools(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertIn("comfyui.workflow_build_plan", names)
        self.assertIn("comfyui.workflow_build", names)
        self.assertIn("comfyui.workflow_repair", names)
        self.assertIn("comfyui.agent_run", names)


if __name__ == "__main__":
    unittest.main()
