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

    def test_unlisted_method_rejected(self):
        msg = {"jsonrpc": "2.0", "id": 2, "method": "illustrator.run_jsx", "params": {}}
        _, payload = request(
            "http://127.0.0.1:8976/rpc",
            json.dumps(msg).encode(),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(-32600, payload["error"]["code"])

    def test_desktop_frame_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request(
                "http://127.0.0.1:8976/capture/frame",
                b"fake",
                {"Content-Type": "image/jpeg", "X-StarBridge-Capture-Target": "desktop"},
            )
        self.assertEqual(400, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
