from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from examples.comfy_bridge import workflow_agent
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

PROMPT_ID = "metadata-source-job"
SUPPORTED_OVERRIDES = [
    "cfg",
    "height",
    "negative_prompt",
    "prompt",
    "sampler",
    "scheduler",
    "seed",
    "steps",
    "width",
]


class ComfyAssetMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        workflow_agent._GENERATION_RECORDS.clear()
        workflow_agent._ASSET_RECORDS.clear()
        workflow = workflow_agent.build_txt2img_workflow(
            {
                "prompt": "private source prompt",
                "negative_prompt": "private negative prompt",
                "checkpoint": "private-checkpoint-name",
                "seed": 10,
            }
        )
        self.workflow_hash = workflow_agent.workflow_hash(workflow)
        workflow_agent._remember_generation(PROMPT_ID, workflow)
        history = {
            PROMPT_ID: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "result.png",
                                "subfolder": "batch",
                                "type": "output",
                            }
                        ]
                    }
                },
            }
        }
        manifest = workflow_agent.output_manifest_from_history(PROMPT_ID, history)
        self.asset_id = manifest["images"][0]["asset_id"]
        workflow_agent._remember_manifest_assets(PROMPT_ID, manifest)

    def tearDown(self) -> None:
        workflow_agent._GENERATION_RECORDS.clear()
        workflow_agent._ASSET_RECORDS.clear()

    def test_available_asset_returns_only_safe_regeneration_metadata(self) -> None:
        workflow_agent._ASSET_RECORDS[self.asset_id]["created_at"] = 100.0
        with patch("examples.comfy_bridge.workflow_agent.time.monotonic", return_value=110.0):
            result = workflow_agent.asset_metadata({"asset_id": self.asset_id})

        self.assertTrue(result["ok"])
        self.assertTrue(result["available"])
        self.assertTrue(result["can_regenerate"])
        self.assertEqual("session_read_only", result["mode"])
        self.assertEqual(self.workflow_hash, result["workflow_hash"])
        self.assertEqual(SUPPORTED_OVERRIDES, result["supported_overrides"])
        self.assertEqual(
            workflow_agent.PROVENANCE_TTL_SECONDS - 10,
            result["provenance"]["expires_in_seconds"],
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("private source prompt", serialized)
        self.assertNotIn("private negative prompt", serialized)
        self.assertNotIn("private-checkpoint-name", serialized)
        self.assertNotIn('"workflow"', serialized)

    def test_unknown_expired_and_invalid_assets_fail_closed(self) -> None:
        missing = workflow_agent.asset_metadata({"asset_id": "asset_0000000000000000"})
        self.assertFalse(missing["ok"])
        self.assertFalse(missing["available"])
        self.assertFalse(missing["can_regenerate"])
        self.assertEqual("asset_provenance_unavailable", missing["error_code"])

        workflow_agent._ASSET_RECORDS[self.asset_id]["created_at"] = 0.0
        with patch(
            "examples.comfy_bridge.workflow_agent.time.monotonic",
            return_value=workflow_agent.PROVENANCE_TTL_SECONDS + 1.0,
        ):
            expired = workflow_agent.asset_metadata({"asset_id": self.asset_id})
        self.assertEqual("asset_provenance_unavailable", expired["error_code"])

        with self.assertRaises(ValueError):
            workflow_agent.asset_metadata({"asset_id": "../private"})

    def test_tool_schema_registry_and_mcp_handler_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.asset_metadata"]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["requiresConfirmation"])
        self.assertFalse(tool["annotations"]["requiresLocalSoftware"])
        self.assertEqual(["asset_id"], tool["inputSchema"]["required"])

        capabilities = {item["name"]: item for item in list_capabilities()}
        self.assertIn("comfyui.asset_metadata", capabilities)

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "comfyui.asset_metadata",
                    "arguments": {"asset_id": self.asset_id},
                },
            }
        )
        assert response is not None
        self.assertFalse(response["result"]["isError"])
        self.assertTrue(response["result"]["structuredContent"]["can_regenerate"])


if __name__ == "__main__":
    unittest.main()
