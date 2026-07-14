from __future__ import annotations

import unittest

from starbridge_mcp.mcp_server import handle_request


def request(message_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_request(payload)
    assert response is not None
    return response


class AdobeMcpToolTests(unittest.TestCase):
    def test_tools_list_contains_adobe_demo_tools(self) -> None:
        response = request(1, "tools/list")
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertTrue(
            {
                "illustrator.document_info",
                "illustrator.create_demo_artboard",
                "illustrator.export_demo_assets",
                "illustrator.run_demo",
                "illustrator.color_vectorize_plan",
                "illustrator.color_vectorize_validate",
                "illustrator.color_vectorize_execute",
                "photoshop.document_info",
                "photoshop.create_demo_document",
                "photoshop.export_demo_preview",
                "photoshop.run_demo",
            }.issubset(names)
        )


if __name__ == "__main__":
    unittest.main()
