from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_PROXY_ROOT = REPO_ROOT / "node_proxy" / "photoshop-bridge"
SERVER_JS = NODE_PROXY_ROOT / "server.js"


def read_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "starbridge.ping", "params": {}}).encode("utf-8"),
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


if __name__ == "__main__":
    unittest.main()
