from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from examples.comfy_bridge.workflow_agent import generation_result
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

PROMPT_ID = "9f5f84f8-private-prompt-id"


class ComfyGenerationResultTests(unittest.TestCase):
    def test_completed_generation_returns_basename_only_manifest(self) -> None:
        history = {
            PROMPT_ID: {
                "status": {"status_str": "success", "completed": True, "messages": []},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "C:\\Users\\private\\Desktop\\result.png",
                                "subfolder": "private\\batch",
                                "type": "output",
                            }
                        ]
                    }
                },
            }
        }
        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history) as read:
            result = generation_result({"prompt_id": PROMPT_ID})

        read.assert_called_once_with("http://127.0.0.1:8188", f"/history/{PROMPT_ID}", 8)
        self.assertTrue(result["ok"])
        self.assertEqual("completed", result["state"])
        self.assertTrue(result["terminal"])
        self.assertTrue(result["result_ready"])
        image = result["output_manifest"]["images"][0]
        self.assertRegex(image["asset_id"], r"^asset_[0-9a-f]{16}$")
        self.assertEqual("result.png", image["filename"])
        self.assertEqual("batch", image["subfolder"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(PROMPT_ID, serialized)
        self.assertNotIn("C:\\Users\\", serialized)
        self.assertNotIn("Desktop", serialized)

    def test_asset_ids_are_stable_and_distinguish_output_identity(self) -> None:
        base_history = {
            PROMPT_ID: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "result.png",
                                "subfolder": "batch-a",
                                "type": "output",
                            },
                            {
                                "filename": "result.png",
                                "subfolder": "batch-b",
                                "type": "output",
                            },
                        ]
                    }
                },
            }
        }
        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=base_history):
            first = generation_result({"prompt_id": PROMPT_ID})
            second = generation_result({"prompt_id": PROMPT_ID})

        first_ids = [item["asset_id"] for item in first["output_manifest"]["images"]]
        second_ids = [item["asset_id"] for item in second["output_manifest"]["images"]]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(2, len(set(first_ids)))

    def test_pending_failed_and_cancelled_states_are_structured(self) -> None:
        cases = (
            ({}, "queued_or_running", True, False),
            (
                {
                    PROMPT_ID: {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [["execution_error", {"traceback": "private"}]],
                        },
                        "outputs": {},
                    }
                },
                "failed",
                False,
                True,
            ),
            (
                {
                    PROMPT_ID: {
                        "status": {
                            "status_str": "interrupted",
                            "messages": [["execution_interrupted", {"reason": "private"}]],
                        },
                        "outputs": {},
                    }
                },
                "cancelled",
                False,
                True,
            ),
        )
        for history, state, ok, terminal in cases:
            with (
                self.subTest(state=state),
                patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history),
            ):
                result = generation_result({"prompt_id": PROMPT_ID})
            self.assertEqual(state, result["state"])
            self.assertEqual(ok, result["ok"])
            self.assertEqual(terminal, result["terminal"])
            self.assertNotIn("private", json.dumps(result, ensure_ascii=False))

    def test_only_bounded_ids_and_loopback_urls_are_allowed(self) -> None:
        for prompt_id in ("", "../history", "has space", "x" * 129):
            with self.subTest(prompt_id=prompt_id), self.assertRaises(ValueError):
                generation_result({"prompt_id": prompt_id})

        for url in ("https://127.0.0.1:8188", "http://example.invalid:8188"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "loopback"):
                generation_result({"prompt_id": PROMPT_ID, "comfy_url": url})

    def test_endpoint_errors_do_not_echo_prompt_id_or_url(self) -> None:
        with patch(
            "examples.comfy_bridge.workflow_agent.get_json",
            side_effect=urllib.error.URLError(
                f"http://127.0.0.1:8188/history/{PROMPT_ID} private failure"
            ),
        ):
            result = generation_result({"prompt_id": PROMPT_ID})

        serialized = json.dumps(result, ensure_ascii=False)
        self.assertFalse(result["ok"])
        self.assertEqual("unavailable", result["state"])
        self.assertNotIn(PROMPT_ID, serialized)
        self.assertNotIn("private failure", serialized)

    def test_tool_schema_registry_and_mcp_handler_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.generation_result"]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["requiresLocalSoftware"])
        self.assertIn("prompt_id", tool["inputSchema"]["required"])

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=False)}
        self.assertIn("comfyui.generation_result", capabilities)

        history = {
            PROMPT_ID: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"9": {"images": [{"filename": "result.png"}]}},
            }
        }
        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history):
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "comfyui.generation_result",
                        "arguments": {"prompt_id": PROMPT_ID},
                    },
                }
            )
        assert response is not None
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("completed", response["result"]["structuredContent"]["state"])


if __name__ == "__main__":
    unittest.main()
