from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from examples.comfy_bridge import workflow_agent
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

OLDER_ASSET_ID = "asset_1111111111111111"
NEWER_ASSET_ID = "asset_2222222222222222"


class ComfyAssetListTests(unittest.TestCase):
    def setUp(self) -> None:
        workflow_agent._GENERATION_RECORDS.clear()
        workflow_agent._ASSET_RECORDS.clear()
        self.older_workflow = workflow_agent.build_txt2img_workflow(
            {
                "prompt": "sensitive older prompt",
                "checkpoint": "sensitive-older-checkpoint",
                "seed": 11,
            }
        )
        self.newer_workflow = workflow_agent.build_txt2img_workflow(
            {
                "prompt": "sensitive newer prompt",
                "checkpoint": "sensitive-newer-checkpoint",
                "seed": 22,
            }
        )
        workflow_agent._ASSET_RECORDS.update(
            {
                OLDER_ASSET_ID: {
                    "created_at": 100.0,
                    "workflow": self.older_workflow,
                },
                NEWER_ASSET_ID: {
                    "created_at": 110.0,
                    "workflow": self.newer_workflow,
                },
            }
        )

    def tearDown(self) -> None:
        workflow_agent._GENERATION_RECORDS.clear()
        workflow_agent._ASSET_RECORDS.clear()

    def test_assets_are_bounded_newest_first_and_redacted(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.time.monotonic", return_value=120.0):
            result = workflow_agent.asset_list({"limit": 1})

        self.assertTrue(result["ok"])
        self.assertEqual("session_read_only", result["mode"])
        self.assertEqual(1, result["limit"])
        self.assertEqual(1, result["asset_count"])
        self.assertEqual(2, result["total_available"])
        self.assertTrue(result["truncated"])
        self.assertEqual(NEWER_ASSET_ID, result["assets"][0]["asset_id"])
        self.assertEqual(
            workflow_agent.workflow_hash(self.newer_workflow),
            result["assets"][0]["workflow_hash"],
        )
        self.assertEqual(
            workflow_agent.PROVENANCE_TTL_SECONDS - 10,
            result["assets"][0]["expires_in_seconds"],
        )
        self.assertEqual(
            {"asset_id", "can_regenerate", "workflow_hash", "expires_in_seconds"},
            set(result["assets"][0]),
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("sensitive older prompt", serialized)
        self.assertNotIn("sensitive newer prompt", serialized)
        self.assertNotIn("sensitive-older-checkpoint", serialized)
        self.assertNotIn("sensitive-newer-checkpoint", serialized)
        self.assertNotIn('"workflow"', serialized)

    def test_expired_assets_are_pruned_before_listing(self) -> None:
        now = float(workflow_agent.PROVENANCE_TTL_SECONDS + 20)
        workflow_agent._ASSET_RECORDS[OLDER_ASSET_ID]["created_at"] = 0.0
        workflow_agent._ASSET_RECORDS[NEWER_ASSET_ID]["created_at"] = now - 10.0

        with patch("examples.comfy_bridge.workflow_agent.time.monotonic", return_value=now):
            result = workflow_agent.asset_list({})

        self.assertEqual(1, result["asset_count"])
        self.assertEqual(1, result["total_available"])
        self.assertFalse(result["truncated"])
        self.assertEqual([NEWER_ASSET_ID], [item["asset_id"] for item in result["assets"]])
        self.assertNotIn(OLDER_ASSET_ID, workflow_agent._ASSET_RECORDS)

    def test_empty_list_is_successful_and_limit_is_bounded(self) -> None:
        workflow_agent._ASSET_RECORDS.clear()
        with patch("examples.comfy_bridge.workflow_agent.time.monotonic", return_value=1.0):
            minimum = workflow_agent.asset_list({"limit": 0})
            maximum = workflow_agent.asset_list({"limit": 1000})

        self.assertEqual(1, minimum["limit"])
        self.assertEqual(100, maximum["limit"])
        self.assertEqual([], minimum["assets"])
        self.assertEqual(0, minimum["total_available"])
        self.assertFalse(minimum["truncated"])
        self.assertEqual(
            workflow_agent.MAX_PROVENANCE_RECORDS,
            minimum["provenance"]["max_records"],
        )

    def test_tool_schema_registry_and_mcp_handler_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.asset_list"]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["requiresConfirmation"])
        self.assertFalse(tool["annotations"]["requiresLocalSoftware"])
        self.assertNotIn("required", tool["inputSchema"])
        self.assertEqual(20, tool["inputSchema"]["properties"]["limit"]["default"])
        self.assertEqual(100, tool["inputSchema"]["properties"]["limit"]["maximum"])

        capabilities = {item["name"]: item for item in list_capabilities()}
        self.assertIn("comfyui.asset_list", capabilities)

        with patch("examples.comfy_bridge.workflow_agent.time.monotonic", return_value=120.0):
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "comfyui.asset_list",
                        "arguments": {"limit": 1},
                    },
                }
            )
        assert response is not None
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(
            NEWER_ASSET_ID, response["result"]["structuredContent"]["assets"][0]["asset_id"]
        )


if __name__ == "__main__":
    unittest.main()
