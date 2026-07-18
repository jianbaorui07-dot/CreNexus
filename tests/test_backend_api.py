from __future__ import annotations

import json
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from PIL import Image

from starbridge_mcp.backend import StarBridgeBackend, make_handler


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.backend = StarBridgeBackend(app_data_dir=self.temp_dir.name)

    def test_health_endpoint(self) -> None:
        response = self.backend.route("GET", "/api/health")

        self.assertEqual(200, response.status)
        self.assertTrue(response.body["ok"])
        self.assertEqual("starbridge-backend", response.body["service"])

    def _make_vector_source(self) -> Path:
        source = Path(self.temp_dir.name) / "private-customer-art.png"
        image = Image.new("RGBA", (12, 8), (0, 0, 0, 0))
        for x in range(2, 10):
            for y in range(1, 7):
                image.putpixel((x, y), (28, 98, 214, 255))
        image.save(source)
        return source

    def test_vectorization_requires_all_three_explicit_confirmations(self) -> None:
        source = self._make_vector_source()
        selected = self.backend.route(
            "POST",
            "/api/vectorization/selections",
            json.dumps({"input_path": str(source)}).encode("utf-8"),
        )
        selection_id = selected.body["data"]["selectionId"]

        response = self.backend.route(
            "POST",
            "/api/vectorization/jobs",
            json.dumps(
                {
                    "selection_id": selection_id,
                    "mode": "exact",
                    "parameters": {},
                    "confirm_run": True,
                    "confirm_write": True,
                }
            ).encode("utf-8"),
        )

        self.assertEqual(400, response.status)
        self.assertEqual("confirmation_required", response.body["error"]["code"])

    def test_vectorization_runs_locally_without_exposing_the_input_path(self) -> None:
        source = self._make_vector_source()
        selected = self.backend.route(
            "POST",
            "/api/vectorization/selections",
            json.dumps({"input_path": str(source)}).encode("utf-8"),
        )

        self.assertEqual(200, selected.status)
        serialized_selection = json.dumps(selected.body, ensure_ascii=False)
        self.assertNotIn(str(source), serialized_selection)
        self.assertNotIn(str(source.parent), serialized_selection)
        selection = selected.body["data"]
        self.assertEqual(source.name, selection["fileName"])
        self.assertTrue(selection["previewDataUrl"].startswith("data:image/png;base64,"))

        started = self.backend.route(
            "POST",
            "/api/vectorization/jobs",
            json.dumps(
                {
                    "selection_id": selection["selectionId"],
                    "mode": "exact",
                    "parameters": {},
                    "confirm_run": True,
                    "confirm_write": True,
                    "confirm_export": True,
                }
            ).encode("utf-8"),
        )
        self.assertEqual(202, started.status)
        job_id = started.body["data"]["jobId"]

        deadline = time.monotonic() + 10
        completed = started
        while time.monotonic() < deadline:
            completed = self.backend.route("GET", f"/api/vectorization/jobs/{job_id}")
            if completed.body["data"]["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        self.assertEqual("completed", completed.body["data"]["status"], completed.body)
        result = completed.body["data"]["result"]
        self.assertTrue(result["metrics"]["pixelMatch"])
        self.assertTrue(result["resultPreviewDataUrl"].startswith("data:image/png;base64,"))
        serialized_job = json.dumps(completed.body, ensure_ascii=False)
        self.assertNotIn(str(source), serialized_job)
        self.assertNotIn(str(source.parent), serialized_job)

        output_root = self.backend.app_paths.data / "vectorization"
        self.assertTrue(any(output_root.rglob("vector.svg")))
        history = self.backend.route("GET", "/api/vectorization/history")
        self.assertEqual(1, history.body["data"]["eventCount"])
        serialized_history = json.dumps(history.body, ensure_ascii=False)
        self.assertNotIn(source.name, serialized_history)
        self.assertNotIn(str(source.parent), serialized_history)

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
        self.assertIn("catalog", data)
        self.assertIn("hybrid", data)
        self.assertIn("history", data)
        self.assertIn("recipes", data)
        self.assertIn("resources", data)
        self.assertIn("safe_roots", data)
        self.assertIn("tiers", data)

    def test_catalog_endpoint_preserves_published_mit_recipe_cards(self) -> None:
        response = self.backend.route("GET", "/api/catalog")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("starbridge.catalog.v1", data["catalog_version"])
        self.assertGreaterEqual(data["item_count"], 5)
        by_recipe = {item["recipe_id"]: item for item in data["items"]}
        self.assertEqual("Community / Open core", by_recipe["photoshop_preview_export"]["tier"])
        self.assertIn("price_signal", by_recipe["comfyui_txt2img_lifecycle"])

    def test_recipe_plan_endpoint(self) -> None:
        response = self.backend.route("GET", "/api/recipes/comfyui_txt2img_lifecycle/plan")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("recipe_plan", data["action"])
        self.assertEqual("comfyui_txt2img_lifecycle", data["recipe_id"])
        self.assertIn("quality_gates", data["plan"])
        self.assertEqual("recipe_action", response.body["event"]["kind"])

    def test_recipe_evidence_endpoint(self) -> None:
        response = self.backend.route("POST", "/api/recipes/blender_scene_evidence/evidence")

        self.assertEqual(200, response.status)
        manifest = response.body["data"]["manifest"]
        self.assertEqual("recipe_evidence", manifest["action"])
        self.assertIn("quality_gates", manifest)
        self.assertIn("asset_manifest", manifest)
        self.assertEqual("evidence", response.body["event"]["action"])

    def test_recipe_actions_are_recorded_in_audit_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = StarBridgeBackend(
                history_path=Path(temp_dir) / "history.json",
                app_data_dir=Path(temp_dir) / "app-data",
            )

            backend.route("GET", "/api/recipes/comfyui_txt2img_lifecycle/plan")
            backend.route("POST", "/api/recipes/comfyui_txt2img_lifecycle/evidence")
            backend.route(
                "POST",
                "/api/recipes/comfyui_txt2img_lifecycle/run",
                json.dumps({"confirm_run": True, "execution_target": "local"}).encode("utf-8"),
            )
            response = backend.route("GET", "/api/audit/history")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("starbridge.audit.v1", data["history_version"])
        self.assertEqual(3, data["event_count"])
        self.assertEqual("run", data["events"][0]["action"])
        self.assertEqual("local", data["events"][0]["execution_target"])
        self.assertEqual("evidence", data["events"][1]["action"])
        self.assertEqual("plan", data["events"][2]["action"])

    def test_tiers_endpoint_returns_community_pro_enterprise_model(self) -> None:
        response = self.backend.route("GET", "/api/tiers")

        self.assertEqual(200, response.status)
        tiers = response.body["data"]["tiers"]
        self.assertEqual(["community", "pro", "enterprise"], [item["id"] for item in tiers])

    def test_execution_endpoint_returns_local_only_lanes(self) -> None:
        response = self.backend.route("GET", "/api/hybrid")

        self.assertEqual(200, response.status)
        lanes = {item["id"]: item for item in response.body["data"]["lanes"]}
        self.assertIn("photoshop", lanes["local_desktop"]["bridges"])
        self.assertEqual("local", lanes["local_comfyui"]["execution_target"])

    def test_recipe_run_requires_confirmation(self) -> None:
        response = self.backend.route("POST", "/api/recipes/comfyui_txt2img_lifecycle/run")

        self.assertEqual(400, response.status)
        self.assertFalse(response.body["ok"])
        self.assertIn("confirm_run", response.body["error"])

    def test_recipe_run_records_confirmed_safe_execution_request(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = StarBridgeBackend(
                history_path=Path(temp_dir) / "history.json",
                app_data_dir=Path(temp_dir) / "app-data",
            )
            body = json.dumps({"confirm_run": True, "execution_target": "local"}).encode("utf-8")

            response = backend.route("POST", "/api/recipes/comfyui_txt2img_lifecycle/run", body)
            history = backend.route("GET", "/api/audit/history")

        self.assertEqual(200, response.status)
        data = response.body["data"]
        self.assertEqual("recipe_run", data["action"])
        self.assertEqual("local", data["execution_target"])
        self.assertFalse(data["billing_preview"]["billable"])
        self.assertTrue(response.body["event"]["evidence_ready"])
        self.assertEqual("run", history.body["data"]["events"][0]["action"])

    def test_audit_history_can_be_cleared(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = StarBridgeBackend(
                history_path=Path(temp_dir) / "history.json",
                app_data_dir=Path(temp_dir) / "app-data",
            )
            backend.route("GET", "/api/recipes/comfyui_txt2img_lifecycle/plan")

            response = backend.route("DELETE", "/api/audit/history")
            history = backend.route("GET", "/api/audit/history")

        self.assertEqual(200, response.status)
        self.assertEqual(0, history.body["data"]["event_count"])

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
            backend = StarBridgeBackend(static_root=root, app_data_dir=root / "app-data")
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
            backend = StarBridgeBackend(static_root=root, app_data_dir=root / "app-data")

            response = backend.route("GET", "/")

        self.assertEqual(200, response.status)
        self.assertEqual("text/html; charset=utf-8", response.content_type)
        self.assertIn(b"StarBridge UI", response.body)

    def test_spa_unknown_non_api_route_falls_back_to_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "index.html").write_text("fallback", encoding="utf-8")
            backend = StarBridgeBackend(static_root=root, app_data_dir=root / "app-data")

            response = backend.route("GET", "/workbench/recipes")

        self.assertEqual(200, response.status)
        self.assertEqual(b"fallback", response.body)


if __name__ == "__main__":
    unittest.main()
