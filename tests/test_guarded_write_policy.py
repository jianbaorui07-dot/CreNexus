from __future__ import annotations

import unittest

from starbridge_mcp.mcp_server import handle_request


SIMPLE_PLAN = {
    "units": "mm",
    "entities": [{"type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10}],
}


class GuardedWritePolicyTest(unittest.TestCase):
    def call_tool(self, name: str, arguments: dict) -> dict:
        response = handle_request({"jsonrpc": "2.0", "id": 101, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        assert response is not None
        return response["result"]["structuredContent"]

    def test_dxf_real_write_requires_confirm_write(self) -> None:
        result = self.call_tool(
            "autocad_dxf.write_dxf",
            {"plan": SIMPLE_PLAN, "output_path": "examples/cad/output/test.dxf", "dry_run": False},
        )

        self.assertFalse(result["ok"])
        self.assertIn("confirm_write", result["message"])

    def test_photoshop_real_write_requires_confirm_write(self) -> None:
        result = self.call_tool("photoshop.create_demo_document", {"dry_run": False})

        self.assertFalse(result["ok"])
        self.assertIn("confirm_write", " ".join(result["warnings"]))

    def test_photoshop_real_export_requires_confirm_export(self) -> None:
        result = self.call_tool("photoshop.export_demo_preview", {"dry_run": False})

        self.assertFalse(result["ok"])
        self.assertIn("confirm_export", " ".join(result["warnings"]))

    def test_illustrator_real_write_requires_confirm_write(self) -> None:
        result = self.call_tool("illustrator.create_demo_artboard", {"dry_run": False})

        self.assertFalse(result["ok"])
        self.assertIn("confirm_write", " ".join(result["warnings"]))

    def test_illustrator_real_export_requires_confirm_export(self) -> None:
        result = self.call_tool("illustrator.export_demo_assets", {"dry_run": False})

        self.assertFalse(result["ok"])
        self.assertIn("confirm_export", " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
