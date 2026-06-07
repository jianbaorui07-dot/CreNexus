from __future__ import annotations

import unittest

from starbridge_mcp.mcp_server import TOOL_DEFINITIONS


class McpToolSchemasTest(unittest.TestCase):
    def test_all_tools_have_required_mcp_fields_and_risk_metadata(self) -> None:
        for tool in TOOL_DEFINITIONS:
            with self.subTest(tool=tool["name"]):
                self.assertIsInstance(tool.get("name"), str)
                self.assertIsInstance(tool.get("description"), str)
                self.assertIsInstance(tool.get("inputSchema"), dict)
                self.assertIsInstance(tool.get("annotations"), dict)

                annotations = tool["annotations"]
                for key in ("riskLevel", "safeDefault", "requiresConfirmation", "requiresLocalSoftware", "currentStatus"):
                    self.assertIn(key, annotations)
                self.assertIn(annotations["riskLevel"], {"safe_read_only", "guarded_local_write", "guarded_local_process"})

    def test_guarded_write_tools_declare_dry_run_and_confirmation(self) -> None:
        for tool in TOOL_DEFINITIONS:
            annotations = tool["annotations"]
            if annotations.get("readOnlyHint"):
                continue

            schema = tool["inputSchema"]
            properties = schema.get("properties", {})
            with self.subTest(tool=tool["name"]):
                if tool["name"] == "comfyui.agent_run":
                    self.assertIn("confirm_run", properties)
                else:
                    self.assertIn("dry_run", properties)
                    self.assertTrue({"confirm_write", "confirm_export"} & set(properties))
                self.assertTrue(annotations["requiresConfirmation"])
                self.assertFalse(annotations["safeDefault"])

    def test_safe_only_evidence_tools_are_declared(self) -> None:
        by_name = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        for name in ("starbridge.evidence_init", "starbridge.evidence_validate", "starbridge.job_status"):
            with self.subTest(tool=name):
                self.assertIn(name, by_name)
                self.assertTrue(by_name[name]["annotations"]["readOnlyHint"])


if __name__ == "__main__":
    unittest.main()
