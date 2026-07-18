from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_PROXY_ROOT = REPO_ROOT / "node_proxy" / "photoshop-bridge"
SERVER_JS = NODE_PROXY_ROOT / "server.js"


def read_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_rpc(port: str, method: str, params: dict, request_id: int = 1) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/rpc",
        data=json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def live_update(**overrides: object) -> dict:
    payload = {
        "type": "codex_session",
        "protocol_version": 1,
        "session_id": "ps-demo",
        "bridge": "photoshop",
        "mode": "structured",
        "phase": "running",
        "step": {"id": "layers", "label": "调整图层", "index": 2, "total": 4},
        "message": "Codex 正在调整图层结构",
        "progress": 50,
        "at": "2026-07-18T00:00:00.000Z",
    }
    payload.update(overrides)
    return payload


@unittest.skipUnless(SERVER_JS.exists(), "node proxy source not present")
class PhotoshopNodeProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = "8975"
        env = dict(os.environ)
        env["STARBRIDGE_PHOTOSHOP_PROXY_PORT"] = self.port
        self.process = subprocess.Popen(
            ["node", str(SERVER_JS)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                read_json(f"http://127.0.0.1:{self.port}/health")
                return
            except Exception:
                time.sleep(0.2)
        stdout, stderr = self.process.communicate(timeout=2)
        self.fail(f"node proxy did not start\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

    def tearDown(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()

    def test_health_endpoint_reports_running(self) -> None:
        payload = read_json(f"http://127.0.0.1:{self.port}/health")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["node_proxy_running"])
        self.assertFalse(payload["uxp_client_connected"])
        self.assertFalse(payload["live_session"]["active"])

    def test_live_session_can_be_published_and_read(self) -> None:
        status, accepted = post_json(
            f"http://127.0.0.1:{self.port}/session", live_update()
        )
        self.assertEqual(202, status)
        self.assertEqual("ps-demo", accepted["update"]["session_id"])
        snapshot = read_json(f"http://127.0.0.1:{self.port}/session")
        self.assertEqual("running", snapshot["current"]["phase"])
        health = read_json(f"http://127.0.0.1:{self.port}/health")
        self.assertTrue(health["live_session"]["active"])
        self.assertEqual(50, health["live_session"]["progress"])

    def test_live_session_rejects_private_paths(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            post_json(
                f"http://127.0.0.1:{self.port}/session",
                live_update(message="正在处理 C:/private/client.psd"),
            )
        self.assertEqual(400, caught.exception.code)

    def test_bridge_status_reports_uxp_not_connected(self) -> None:
        payload = read_json(f"http://127.0.0.1:{self.port}/bridge/status")
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["uxp_client_connected"])
        self.assertIn("pending_jobs", payload)
        self.assertIn("last_error", payload)
        self.assertIn("last_client_registered_at", payload)

    def test_events_endpoint_reports_startup_event(self) -> None:
        payload = read_json(f"http://127.0.0.1:{self.port}/events")
        self.assertTrue(payload["ok"])
        event_types = {event["type"] for event in payload["events"]}
        self.assertIn("node_proxy_started", event_types)

    def test_rpc_without_uxp_client_returns_explicit_error(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/rpc",
            data=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "starbridge.ping", "params": {}}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(-32001, payload["error"]["code"])
        self.assertIn("uxp_client_not_connected", payload["error"]["message"])

    def test_rpc_rejects_invalid_json_without_crashing(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/rpc",
            data=b"{not-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(-32700, payload["error"]["code"])
        self.assertEqual("parse_error", payload["error"]["message"])

    def test_rpc_validates_jsonrpc_shape(self) -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/rpc",
            data=json.dumps({"id": 1, "method": "starbridge.ping"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(-32600, payload["error"]["code"])
        self.assertEqual("jsonrpc_must_be_2_0", payload["error"]["message"])

    def test_rpc_rejects_unlisted_method_before_forwarding(self) -> None:
        payload = post_rpc(self.port, "ps.run_jsx", {})
        self.assertEqual(-32601, payload["error"]["code"])
        self.assertEqual("method_not_allowed", payload["error"]["message"])

    def test_preview_export_requires_explicit_confirmation(self) -> None:
        payload = post_rpc(
            self.port,
            "ps.preview.export",
            {"dry_run": False, "output_path": "preview.png"},
        )
        self.assertEqual(-32010, payload["error"]["code"])
        self.assertEqual("confirm_write=true_required", payload["error"]["message"])

    def test_preview_export_rejects_path_outside_repo_sandbox(self) -> None:
        payload = post_rpc(
            self.port,
            "ps.preview.export",
            {
                "dry_run": False,
                "confirm_write": True,
                "output_path": "C:/outside/preview.png",
            },
        )
        self.assertEqual(-32602, payload["error"]["code"])
        self.assertEqual("output_path_outside_sandbox", payload["error"]["message"])

    def test_preview_export_accepts_sandbox_path_before_connection_check(self) -> None:
        output_path = REPO_ROOT / "sandbox" / "ps_preview_safe.png"
        payload = post_rpc(
            self.port,
            "ps.preview.export",
            {
                "dry_run": False,
                "confirm_write": True,
                "output_path": output_path.as_posix(),
            },
        )
        self.assertEqual(-32001, payload["error"]["code"])
        self.assertEqual("uxp_client_not_connected", payload["error"]["message"])

    def test_batchplay_execute_requires_confirmation(self) -> None:
        payload = post_rpc(
            self.port,
            "ps.batchplay.execute_confirmed",
            {"descriptors": [{"_obj": "make"}]},
        )
        self.assertEqual(-32010, payload["error"]["code"])

    def test_protocol_schema_lists_same_public_methods(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT
                / "examples"
                / "photoshop_bridge"
                / "protocols"
                / "node_proxy_rpc.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        methods = set(schema["properties"]["method"]["enum"])
        self.assertNotIn("ps.run_jsx", methods)
        self.assertIn("ps.preview.export", methods)
        self.assertIn("ps.batchplay.execute_confirmed", methods)

    def test_uxp_bridge_declares_runtime_sandbox_guards(self) -> None:
        index_source = (REPO_ROOT / "uxp" / "photoshop-bridge" / "src" / "index.js").read_text(
            encoding="utf-8"
        )
        runner_source = (
            REPO_ROOT / "uxp" / "photoshop-bridge" / "src" / "batchplay-runner.js"
        ).read_text(encoding="utf-8")
        self.assertIn("assertSandboxOutputPath", index_source)
        self.assertIn("document.duplicate", runner_source)
        self.assertIn("registerAutoCloseDocument", runner_source)
        self.assertIn("unregisterAutoCloseDocument", runner_source)

    def test_uxp_bridge_has_in_app_codex_live_panel(self) -> None:
        plugin = REPO_ROOT / "uxp" / "photoshop-bridge"
        manifest = json.loads((plugin / "manifest.json").read_text(encoding="utf-8"))
        panel_ids = {
            entry["id"] for entry in manifest["entrypoints"] if entry["type"] == "panel"
        }
        self.assertEqual("index.html", manifest["main"])
        self.assertIn("starbridgePhotoshopLivePanel", panel_ids)
        html = (plugin / "index.html").read_text(encoding="utf-8")
        client = (plugin / "src" / "bridge-client.js").read_text(encoding="utf-8")
        for element_id in ("session-phase", "session-message", "session-progress"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('message?.type === "codex_session"', client)
        self.assertIn("this.onSession(message)", client)


if __name__ == "__main__":
    unittest.main()
