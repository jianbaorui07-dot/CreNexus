from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from examples.comfy_bridge import workflow_agent
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

PROMPT_ID = "source-prompt-1"


class ComfyRegenerateTests(unittest.TestCase):
    def setUp(self) -> None:
        workflow_agent._GENERATION_RECORDS.clear()
        workflow_agent._ASSET_RECORDS.clear()
        workflow = workflow_agent.build_txt2img_workflow(
            {
                "prompt": "private source prompt",
                "negative_prompt": "private negative prompt",
                "checkpoint": "reviewed-checkpoint",
                "seed": 10,
            }
        )
        workflow_agent._remember_generation(PROMPT_ID, workflow)
        history = {
            PROMPT_ID: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "C:\\Users\\private\\Desktop\\result.png",
                                "subfolder": "private-batch",
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

    def test_default_is_validated_dry_run_without_submission_or_private_data(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.submit_workflow") as submit:
            result = workflow_agent.regenerate(
                {
                    "asset_id": self.asset_id,
                    "prompt": "refined public prompt",
                    "steps": 28,
                    "cfg": 6.5,
                }
            )

        submit.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertFalse(result["submitted"])
        self.assertEqual(["cfg", "prompt", "steps"], result["overrides_applied"])
        self.assertTrue(result["validation_summary"]["ok"])
        self.assertEqual("memory_only", result["provenance"]["storage"])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("private source prompt", serialized)
        self.assertNotIn("private negative prompt", serialized)
        self.assertNotIn("C:\\Users\\", serialized)

    def test_confirmed_regenerate_submits_overridden_workflow_and_remembers_job(self) -> None:
        fake_submission = {
            "ok": False,
            "submitted": True,
            "prompt_id": "regenerated-prompt-2",
            "job_status": {
                "state": "queued_or_running",
                "history_available": False,
                "output_manifest": {"image_count": 0, "images": []},
            },
        }
        with patch(
            "examples.comfy_bridge.workflow_agent.submit_workflow",
            return_value=fake_submission,
        ) as submit:
            result = workflow_agent.regenerate(
                {
                    "asset_id": self.asset_id,
                    "prompt": "refined prompt",
                    "width": 768,
                    "height": 1024,
                    "confirm_run": True,
                }
            )

        submit.assert_called_once()
        submitted_workflow = submit.call_args.args[0]
        self.assertEqual("refined prompt", submitted_workflow["6"]["inputs"]["text"])
        self.assertEqual(768, submitted_workflow["5"]["inputs"]["width"])
        self.assertEqual(1024, submitted_workflow["5"]["inputs"]["height"])
        self.assertNotEqual(10, submitted_workflow["3"]["inputs"]["seed"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertEqual("regenerated-prompt-2", result["prompt_id"])
        self.assertEqual(["comfyui_regeneration_pending"], result["warnings"])
        self.assertIn("do not resubmit automatically", result["next_steps"][0])
        self.assertIn("regenerated-prompt-2", workflow_agent._GENERATION_RECORDS)

    def test_unknown_expired_and_invalid_asset_ids_never_submit(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.submit_workflow") as submit:
            missing = workflow_agent.regenerate(
                {"asset_id": "asset_0000000000000000", "confirm_run": True}
            )
            self.assertFalse(missing["ok"])
            self.assertEqual("asset_provenance_unavailable", missing["error_code"])

            workflow_agent._ASSET_RECORDS[self.asset_id]["created_at"] = -100000.0
            expired = workflow_agent.regenerate({"asset_id": self.asset_id, "confirm_run": True})
            self.assertEqual("asset_provenance_unavailable", expired["error_code"])

            with self.assertRaises(ValueError):
                workflow_agent.regenerate({"asset_id": "../private"})
        submit.assert_not_called()

    def test_tool_schema_registry_and_mcp_handler_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.regenerate"]
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["requiresConfirmation"])
        self.assertIn("asset_id", tool["inputSchema"]["required"])

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=True)}
        self.assertIn("comfyui.regenerate", capabilities)

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "comfyui.regenerate",
                    "arguments": {"asset_id": self.asset_id, "steps": 24},
                },
            }
        )
        assert response is not None
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("dry_run", response["result"]["structuredContent"]["mode"])


if __name__ == "__main__":
    unittest.main()
