from __future__ import annotations

import unittest

from starbridge_mcp.mcp_server import handle_request

SIMPLE_PLAN = {
    "units": "mm",
    "entities": [{"type": "line", "start": [0, 0], "end": [10, 10]}],
}


class SandboxOutputPathsTest(unittest.TestCase):
    def call_tool(self, name: str, arguments: dict) -> dict:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 201,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        assert response is not None
        return response["result"]["structuredContent"]

    def test_dxf_write_cannot_escape_cad_output_root(self) -> None:
        result = self.call_tool(
            "autocad_dxf.write_dxf",
            {
                "plan": SIMPLE_PLAN,
                "output_path": "examples/output/escaped.dxf",
                "dry_run": False,
                "confirm_write": True,
            },
        )

        self.assertFalse(result["ok"])
        self.assertIn("examples/cad/output", result["message"])

    def test_photoshop_output_dir_cannot_escape_sandbox(self) -> None:
        result = self.call_tool(
            "photoshop.create_demo_document", {"output_dir": "examples/output/illustrator"}
        )

        self.assertFalse(result["ok"])
        self.assertIn("output_dir", result["error"])

    def test_illustrator_output_dir_cannot_escape_sandbox(self) -> None:
        result = self.call_tool(
            "illustrator.export_demo_assets", {"output_dir": "examples/output/photoshop"}
        )

        self.assertFalse(result["ok"])
        self.assertIn("output_dir", result["error"])


if __name__ == "__main__":
    unittest.main()
