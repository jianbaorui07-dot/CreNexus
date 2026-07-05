from __future__ import annotations

import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from starbridge_mcp.backend import StarBridgeBackend, make_handler


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = StarBridgeBackend()

    def test_health_endpoint(self) -> None:
        response = self.backend.route("GET", "/api/health")

        self.assertEqual(200, response.status)
        self.assertTrue(response.body["ok"])
        self.assertEqual("starbridge-backend", response.body["service"])

    def test_capabilities_endpoint_reuses_mcp_registry(self) -> None:
        response = self.backend.route("GET", "/api/capabilities?safe_only=true")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("starbridge.capabilities.v2", data["manifest_version"])
        self.assertIn("bridge_overview", data)
        self.assertTrue(all(item["safe_default"] for item in data["capabilities"]))

    def test_tools_endpoint_returns_mcp_tool_definitions(self) -> None:
        response = self.backend.route("GET", "/api/tools")

        self.assertEqual(200, response.status)
        names = {item["name"] for item in response.body["data"]["tools"]}
        self.assertIn("starbridge.recipe_plan", names)
        self.assertIn("starbridge.recipe_evidence", names)

    def test_bootstrap_endpoint_returns_ui_startup_payload(self) -> None:
        response = self.backend.route("GET", "/api/bootstrap")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertIn("capabilities", data)
        self.assertIn("recipes", data)
        self.assertIn("resources", data)
        self.assertIn("safe_roots", data)

    def test_recipe_plan_endpoint(self) -> None:
        response = self.backend.route("GET", "/api/recipes/comfyui_txt2img_lifecycle/plan")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("recipe_plan", data["action"])
        self.assertEqual("comfyui_txt2img_lifecycle", data["recipe_id"])
        self.assertIn("quality_gates", data["plan"])

    def test_recipe_evidence_endpoint(self) -> None:
        response = self.backend.route("POST", "/api/recipes/blender_scene_evidence/evidence")

        self.assertEqual(200, response.status)
        manifest = response.body["data"]["manifest"]
        self.assertEqual("recipe_evidence", manifest["action"])
        self.assertIn("quality_gates", manifest)
        self.assertIn("asset_manifest", manifest)

    def test_generic_tool_call_endpoint(self) -> None:
        body = json.dumps(
            {
                "name": "starbridge.recipe_list",
                "arguments": {"bridge": "blender"},
            }
        ).encode("utf-8")

        response = self.backend.route("POST", "/api/tools/call", body)

        self.assertEqual(200, response.status)
        recipes = response.body["data"]["recipes"]
        self.assertEqual(["blender_scene_evidence"], [item["recipe_id"] for item in recipes])

    def test_invalid_json_is_400(self) -> None:
        response = self.backend.route("POST", "/api/tools/call", b"{")

        self.assertEqual(400, response.status)
        self.assertFalse(response.body["ok"])

    def test_http_server_serves_health_json(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.backend))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(200, response.status)
        self.assertTrue(payload["ok"])
        self.assertEqual("starbridge-backend", payload["service"])

    def test_http_server_supports_head_for_static_frontend(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text("<main>ok</main>", encoding="utf-8")
            backend = StarBridgeBackend(static_root=root)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(backend))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                connection.request("HEAD", "/")
                response = connection.getresponse()
                body = response.read()
            finally:
                server.shutdown()
                server.server_close()

        self.assertEqual(200, response.status)
        self.assertEqual(b"", body)

    def test_static_frontend_is_served_when_built(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text('<div id="root">StarBridge UI</div>', encoding="utf-8")
            backend = StarBridgeBackend(static_root=root)

            response = backend.route("GET", "/")

        self.assertEqual(200, response.status)
        self.assertEqual("text/html; charset=utf-8", response.content_type)
        self.assertIn(b"StarBridge UI", response.body)

    def test_spa_unknown_non_api_route_falls_back_to_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text("fallback", encoding="utf-8")
            backend = StarBridgeBackend(static_root=root)

            response = backend.route("GET", "/workbench/recipes")

        self.assertEqual(200, response.status)
        self.assertEqual(b"fallback", response.body)


if __name__ == "__main__":
    unittest.main()
