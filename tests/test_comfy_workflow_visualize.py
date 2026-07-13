from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from examples.comfy_bridge.workflow_visualize import visualize_workflow
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / "examples" / "comfy_bridge" / "workflows" / "minimal_api_workflow.json"


class ComfyWorkflowVisualizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

    def test_visualizes_api_workflow_as_mermaid_without_input_values(self) -> None:
        result = visualize_workflow(self.workflow)

        self.assertTrue(result["ok"])
        self.assertEqual("workflow_visualize", result["action"])
        self.assertEqual(7, result["summary"]["node_count"])
        self.assertEqual(9, result["summary"]["edge_count"])
        self.assertIn("flowchart LR", result["mermaid"])
        self.assertIn("CheckpointLoaderSimple", result["mermaid"])
        self.assertNotIn("public placeholder prompt", result["mermaid"])
        self.assertNotIn("__checkpoint_placeholder__", result["mermaid"])
        self.assertFalse(result["privacy"]["reads_files"])
        self.assertFalse(result["privacy"]["uses_network"])

    def test_private_values_are_never_rendered(self) -> None:
        workflow = copy.deepcopy(self.workflow)
        private_root = "C:" + "\\Users\\private"
        workflow["1"]["inputs"]["ckpt_name"] = private_root + "\\model.ckpt"
        workflow["2"]["inputs"]["text"] = private_root + "\\client prompt"

        result = visualize_workflow(workflow)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertNotIn(private_root, encoded)
        self.assertNotIn("client prompt", encoded)
        self.assertNotIn("model.ckpt", encoded)

    def test_invalid_direction_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "direction must be LR or TD"):
            visualize_workflow(self.workflow, direction="SIDEWAYS")

    def test_tool_schema_registry_and_mcp_call_are_safe(self) -> None:
        tools = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        tool = tools["comfy.workflow_visualize"]
        self.assertEqual(["workflow"], tool["inputSchema"]["required"])
        self.assertTrue(tool["annotations"]["safeDefault"])
        self.assertTrue(tool["annotations"]["readOnlyHint"])

        capabilities = {item["name"]: item for item in list_capabilities(bridge="comfyui")}
        self.assertEqual("safe_read_only", capabilities["comfy.workflow_visualize"]["risk_level"])

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 92,
                "method": "tools/call",
                "params": {
                    "name": "comfy.workflow_visualize",
                    "arguments": {"workflow": self.workflow, "direction": "TD"},
                },
            }
        )
        assert response is not None
        structured = response["result"]["structuredContent"]
        self.assertFalse(response["result"]["isError"])
        self.assertEqual("TD", structured["direction"])
        self.assertIn("flowchart TD", structured["mermaid"])


if __name__ == "__main__":
    unittest.main()
