from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "node_proxy" / "illustrator-bridge" / "server.js"


def request(url, data=None, headers=None):
    req = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST" if data is not None else "GET"
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read().decode())


def push_state(port: int, state: dict) -> None:
    script = """
import WebSocket from 'ws';
const ws = new WebSocket(process.argv[1]);
ws.on('open', () => { ws.send(process.argv[2]); setTimeout(() => ws.close(), 30); });
ws.on('error', error => { console.error(error.message); process.exit(1); });
setTimeout(() => process.exit(0), 100);
"""
    completed = subprocess.run(
        [
            shutil.which("node"),
            "--input-type=module",
            "-e",
            script,
            f"ws://127.0.0.1:{port}/illustrator",
            json.dumps(state),
        ],
        cwd=SERVER.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


def push_states(port: int, states: list[dict]) -> None:
    script = """
import WebSocket from 'ws';
const ws = new WebSocket(process.argv[1]);
const states = JSON.parse(process.argv[2]);
ws.on('open', () => { for (const state of states) ws.send(JSON.stringify(state)); setTimeout(() => ws.close(), 30); });
ws.on('error', error => { console.error(error.message); process.exit(1); });
setTimeout(() => process.exit(0), 100);
"""
    completed = subprocess.run(
        [
            shutil.which("node"),
            "--input-type=module",
            "-e",
            script,
            f"ws://127.0.0.1:{port}/illustrator",
            json.dumps(states),
        ],
        cwd=SERVER.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)


def minimal_state(sequence: int = 1) -> dict:
    return {
        "type": "state",
        "protocol_version": 2,
        "sequence": sequence,
        "host": {
            "app": "Adobe Illustrator",
            "version": "30.0",
            "adapter": "custom_uxp_v2",
        },
        "document": None,
        "selection": [],
        "layers": [],
        "artboards": [],
        "zoom": None,
        "tool": None,
        "captured_at": "2026-07-14T00:00:00.000Z",
    }


def live_update(**overrides) -> dict:
    payload = {
        "type": "codex_session",
        "protocol_version": 1,
        "session_id": "ai-demo",
        "bridge": "illustrator",
        "mode": "structured",
        "phase": "running",
        "step": {"id": "paths", "label": "生成路径", "index": 1, "total": 3},
        "message": "Codex 正在生成矢量路径",
        "progress": 33,
        "at": "2026-07-18T00:00:00.000Z",
    }
    payload.update(overrides)
    return payload


@unittest.skipUnless(SERVER.exists(), "illustrator realtime proxy missing")
class IllustratorRealtimeProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("Node.js is not installed")

        dependency = subprocess.run(
            [node, "--input-type=module", "-e", "import('ws')"],
            cwd=SERVER.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if dependency.returncode != 0:
            output = f"{dependency.stdout}\n{dependency.stderr}"
            if "ERR_MODULE_NOT_FOUND" in output and "ws" in output:
                raise unittest.SkipTest(
                    "Illustrator realtime proxy requires an installed ws package"
                )
            raise RuntimeError(f"unable to verify Illustrator proxy dependencies\n{output}")

        env = dict(os.environ)
        env["STARBRIDGE_ILLUSTRATOR_PROXY_PORT"] = "8976"
        cls.process = subprocess.Popen(
            [node, str(SERVER)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(50):
            try:
                request("http://127.0.0.1:8976/health")
                return
            except Exception:
                time.sleep(0.1)
        if cls.process.poll() is None:
            cls.process.terminate()
        stdout, stderr = cls.process.communicate(timeout=5)
        raise RuntimeError(f"proxy did not start\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)

    def test_health_is_local_safe_default(self):
        _, payload = request("http://127.0.0.1:8976/health")
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["adapter_connected"])
        self.assertFalse(payload["live_session"]["active"])

    def test_live_session_can_be_published_and_read(self):
        status, accepted = request(
            "http://127.0.0.1:8976/session",
            json.dumps(live_update()).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(202, status)
        self.assertEqual("ai-demo", accepted["update"]["session_id"])
        _, snapshot = request("http://127.0.0.1:8976/session")
        self.assertEqual("running", snapshot["current"]["phase"])
        _, health = request("http://127.0.0.1:8976/health")
        self.assertTrue(health["live_session"]["active"])

    def test_live_session_rejects_bridge_mismatch(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request(
                "http://127.0.0.1:8976/session",
                json.dumps(live_update(bridge="photoshop")).encode("utf-8"),
                {"Content-Type": "application/json"},
            )
        self.assertEqual(400, caught.exception.code)

    def test_preview_page_is_available(self):
        with urllib.request.urlopen("http://127.0.0.1:8976/preview", timeout=5) as response:
            page = response.read().decode("utf-8")
        self.assertIn("Illustrator 窗口实时预览", page)
        self.assertIn("/frame/latest", page)

    def test_write_requires_confirmation(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "illustrator.move_object",
            "params": {"object_id": "session:1", "dx": 1, "dy": 1},
        }
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(msg).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32010, payload["error"]["code"])

    def test_write_rejects_non_session_object_id(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "illustrator.move_object",
            "params": {
                "object_id": "external-object",
                "dx": 1,
                "dy": 1,
                "confirm_write": True,
            },
        }
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(msg).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32602, payload["error"]["code"])

    def test_unlisted_method_rejected(self):
        msg = {"jsonrpc": "2.0", "id": 2, "method": "illustrator.run_jsx", "params": {}}
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(msg).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32600, payload["error"]["code"])

    def test_artisan_map_requires_current_state_revision(self):
        push_state(8976, minimal_state(20))
        _, health = request("http://127.0.0.1:8976/health")
        params = {
            "confirm_write": True,
            "transaction_ref": "apply:0123456789ab",
            "map_ref": "imap:abcdef012345",
            "expected_state_revision": health["state_revision"] + 1,
            "layers": [["layer-subject", "主体色块"]],
            "objects": [["shape-0002", "朱红装饰"]],
        }
        message = {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "illustrator.apply_artisan_map",
            "params": params,
        }
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(message).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32011, payload["error"]["code"])
        message["params"]["expected_state_revision"] = health["state_revision"]
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(message).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32001, payload["error"]["code"])

    def test_desktop_frame_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request(
                "http://127.0.0.1:8976/capture/frame",
                b"fake",
                {"Content-Type": "image/jpeg", "X-StarBridge-Capture-Target": "desktop"},
            )
        self.assertEqual(400, caught.exception.code)

    def test_state_is_redacted_and_reports_freshness(self):
        push_state(
            8976,
            {
                "type": "state",
                "protocol_version": 2,
                "sequence": 7,
                "host": {
                    "app": "Adobe Illustrator",
                    "version": "30.0",
                    "adapter": "custom_uxp_v2",
                },
                "document": {
                    "name": "client-project.ai",
                    "page_items": 2,
                    "layer_count": 1,
                    "artboard_count": 1,
                    "color_space": "RGB",
                    "full_path": "C:/private/client-project.ai",
                },
                "selection": [
                    {
                        "object_id": "item:1",
                        "name": "Customer Logo",
                        "type": "PathItem",
                        "selected": True,
                        "locked": False,
                        "hidden": False,
                    }
                ],
                "layers": [
                    {
                        "layer_id": "layer:1",
                        "name": "Customer Identity",
                        "visible": True,
                        "locked": False,
                    }
                ],
                "artboards": [
                    {
                        "artboard_id": "artboard:1",
                        "name": "Campaign",
                        "rect": [0, 100, 100, 0],
                    }
                ],
                "zoom": 1,
                "tool": "selection",
                "captured_at": "2026-07-14T00:00:00.000Z",
            },
        )
        _, payload = request("http://127.0.0.1:8976/state?max_age_ms=2000")
        serialized = json.dumps(payload)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["stale"])
        self.assertGreaterEqual(payload["revision"], 1)
        self.assertGreaterEqual(payload["age_ms"], 0)
        self.assertEqual(2000, request("http://127.0.0.1:8976/state")[1]["max_age_ms"])
        self.assertNotIn("client-project", serialized)
        self.assertNotIn("Customer", serialized)
        self.assertNotIn("full_path", serialized)

    def test_state_age_limit_marks_old_state_stale(self):
        push_state(8976, minimal_state(8))
        time.sleep(0.12)
        _, payload = request("http://127.0.0.1:8976/state?max_age_ms=100")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["stale"])

    def test_invalid_state_does_not_replace_last_valid_state(self):
        push_state(8976, minimal_state(9))
        _, before = request("http://127.0.0.1:8976/state")
        push_state(8976, {"type": "state", "protocol_version": 1})
        _, after = request("http://127.0.0.1:8976/state")
        self.assertEqual(before["revision"], after["revision"])
        _, health = request("http://127.0.0.1:8976/health")
        self.assertGreaterEqual(health["rejected_states"], 1)

    def test_non_monotonic_sequence_is_rejected(self):
        _, before = request("http://127.0.0.1:8976/health")
        push_states(8976, [minimal_state(10), minimal_state(10)])
        _, after = request("http://127.0.0.1:8976/health")
        self.assertEqual(before["state_revision"] + 1, after["state_revision"])
        self.assertGreaterEqual(after["rejected_states"], before["rejected_states"] + 1)


if __name__ == "__main__":
    unittest.main()
