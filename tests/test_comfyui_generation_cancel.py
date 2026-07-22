from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from examples.comfy_bridge.workflow_agent import generation_cancel
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

PROMPT_ID = "queued-job-123"


class ComfyGenerationCancelTests(unittest.TestCase):
    def test_default_is_network_free_dry_run_and_redacts_prompt_id(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.post_json") as post:
            result = generation_cancel({"prompt_id": PROMPT_ID})

        post.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertFalse(result["cancel_requested"])
        self.assertFalse(result["cancelled"])
        self.assertEqual("not_cancelled", result["state"])
        self.assertIn("confirmation_required", result["warnings"])
        self.assertNotIn(PROMPT_ID, json.dumps(result, ensure_ascii=False))

    def test_confirmed_request_uses_only_official_per_job_endpoint(self) -> None:
        with patch(
            "examples.comfy_bridge.workflow_agent.post_json",
            return_value={"cancelled": True, "private": "must not escape"},
        ) as post:
            result = generation_cancel(
                {"prompt_id": PROMPT_ID, "confirm_cancel": True, "timeout": 4}
            )

        post.assert_called_once_with(
            "http://127.0.0.1:8188",
            f"/api/jobs/{PROMPT_ID}/cancel",
            {},
            4,
        )
        self.assertTrue(result["ok"])
        self.assertEqual("confirmed", result["mode"])
        self.assertTrue(result["cancel_requested"])
        self.assertTrue(result["cancelled"])
        self.assertEqual("cancelled", result["state"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(PROMPT_ID, serialized)
        self.assertNotIn("private", serialized)
        self.assertNotIn("/interrupt", serialized)

    def test_finished_or_unknown_job_is_structured_idempotent_noop(self) -> None:
        with patch(
            "examples.comfy_bridge.workflow_agent.post_json",
            return_value={"cancelled": False},
        ):
            result = generation_cancel({"prompt_id": PROMPT_ID, "confirm_cancel": True})

        self.assertTrue(result["ok"])
        self.assertFalse(result["cancelled"])
        self.assertEqual("not_cancelled", result["state"])
        self.assertIn("job_finished_or_unknown", result["warnings"])

    def test_endpoint_errors_and_invalid_payloads_fail_closed_and_redacted(self) -> None:
        failures = (
            urllib.error.URLError(f"http://127.0.0.1:8188/{PROMPT_ID} private failure"),
            ValueError("private invalid response"),
        )
        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                patch("examples.comfy_bridge.workflow_agent.post_json", side_effect=failure),
            ):
                result = generation_cancel({"prompt_id": PROMPT_ID, "confirm_cancel": True})

            self.assertFalse(result["ok"])
            self.assertEqual("cancel_unavailable", result["state"])
            self.assertEqual("comfyui_cancel_unavailable", result["error_code"])
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn(PROMPT_ID, serialized)
            self.assertNotIn("private", serialized)

    def test_unexpected_response_shape_fails_closed(self) -> None:
        for payload in ({}, {"cancelled": "yes"}, {"cancelled": 1}):
            with (
                self.subTest(payload=payload),
                patch("examples.comfy_bridge.workflow_agent.post_json", return_value=payload),
            ):
                result = generation_cancel({"prompt_id": PROMPT_ID, "confirm_cancel": True})

            self.assertFalse(result["ok"])
            self.assertEqual("cancel_unavailable", result["state"])

    def test_only_bounded_ids_and_loopback_urls_are_allowed(self) -> None:
        for prompt_id in ("", "../queue", "has space", "x" * 129):
            with self.subTest(prompt_id=prompt_id), self.assertRaises(ValueError):
                generation_cancel({"prompt_id": prompt_id})

        for url in ("https://127.0.0.1:8188", "http://example.invalid:8188"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "loopback"):
                generation_cancel({"prompt_id": PROMPT_ID, "comfy_url": url})

    def test_tool_schema_registry_and_mcp_handler_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.generation_cancel"]
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["requiresConfirmation"])
        self.assertTrue(tool["annotations"]["requiresLocalSoftware"])
        self.assertEqual("guarded_local_process", tool["annotations"]["riskLevel"])
        self.assertFalse(tool["inputSchema"]["properties"]["confirm_cancel"]["default"])
        self.assertIn("prompt_id", tool["inputSchema"]["required"])

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=True)}
        self.assertIn("comfyui.generation_cancel", capabilities)

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "comfyui.generation_cancel",
                    "arguments": {"prompt_id": PROMPT_ID},
                },
            }
        )
        assert response is not None
        self.assertFalse(response["result"]["isError"])
        result = response["result"]["structuredContent"]
        self.assertEqual("dry_run", result["mode"])
        self.assertNotIn(PROMPT_ID, json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
