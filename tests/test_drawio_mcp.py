from __future__ import annotations

import unittest

from starbridge_mcp.adapters.drawio import TOOL_DEFINITIONS, TOOL_HANDLERS
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS as ROOT_TOOL_DEFINITIONS
from starbridge_mcp.mcp_server import TOOL_HANDLERS as ROOT_TOOL_HANDLERS


class DiagramForgeMcpTests(unittest.TestCase):
    def test_all_tools_have_handlers_and_safety_annotations(self) -> None:
        names = {tool["name"] for tool in TOOL_DEFINITIONS}
        self.assertEqual(names, set(TOOL_HANDLERS))
        self.assertEqual(
            names,
            {
                "drawio.probe",
                "drawio.capabilities",
                "drawio.plan",
                "drawio.create",
                "drawio.inspect",
                "drawio.patch",
                "drawio.rollback",
                "drawio.validate",
                "drawio.export",
                "drawio.handoff.plan",
                "drawio.batch",
            },
        )
        for tool in TOOL_DEFINITIONS:
            self.assertIn("inputSchema", tool)
            self.assertIn("riskLevel", tool["annotations"])
            if not tool["annotations"]["readOnlyHint"]:
                self.assertTrue(tool["annotations"]["requiresConfirmation"])

    def test_root_mcp_registers_diagramforge_tools(self) -> None:
        root_names = {tool["name"] for tool in ROOT_TOOL_DEFINITIONS}
        self.assertTrue(set(TOOL_HANDLERS).issubset(root_names))
        self.assertTrue(set(TOOL_HANDLERS).issubset(ROOT_TOOL_HANDLERS))

    def test_plan_tool_is_read_only_and_valid(self) -> None:
        result = TOOL_HANDLERS["drawio.plan"](
            {"input_format": "spec", "recipe_id": "system-architecture-v1"}
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["writes_files"])


if __name__ == "__main__":
    unittest.main()
