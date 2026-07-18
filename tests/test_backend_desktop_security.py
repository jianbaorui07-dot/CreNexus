from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch

from starbridge_mcp.backend import (
    READY_PREFIX,
    SESSION_HEADER,
    SESSION_TOKEN_ENV,
    ParentProcessMonitor,
    StarBridgeBackend,
    StarBridgeHttpServer,
)
from starbridge_mcp.core.app_data import APP_DATA_ENV, resolve_app_data_paths

TEST_SESSION_CREDENTIAL = "-".join(
    ("starbridge", "test", "session", "credential", "000000000000000000000001")
)


class DesktopBackendSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def desktop_backend(self, **kwargs: object) -> StarBridgeBackend:
        return StarBridgeBackend(
            app_data_dir=self.root / "app-data",
            session_credential=TEST_SESSION_CREDENTIAL,
            mode="desktop",
            **kwargs,
        )

    @staticmethod
    def request(
        server: StarBridgeHttpServer,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object]]:
        connection = HTTPConnection(server.host, server.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, response_headers, payload
        finally:
            connection.close()

    def test_port_zero_binds_random_loopback_port_and_releases_it(self) -> None:
        server = StarBridgeHttpServer(self.desktop_backend(), port=0)
        server.start()
        port = server.port
        try:
            self.assertEqual("127.0.0.1", server.host)
            self.assertGreater(port, 0)
            status, _, payload = self.request(server, "GET", "/api/health")
            self.assertEqual(200, status)
            self.assertTrue(payload["ok"])
        finally:
            server.stop()

        self.assertTrue(server.wait(timeout=2))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # The listener must be gone, but an accepted connection can remain in
            # TIME_WAIT on Linux. SO_REUSEADDR distinguishes that kernel state
            # from an active StarBridge listener without weakening the assertion.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))

    def test_non_loopback_bind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            StarBridgeHttpServer(self.desktop_backend(), host="0.0.0.0", port=0)

    def test_health_is_public_but_bootstrap_requires_current_session(self) -> None:
        backend = self.desktop_backend()

        health = backend.route("GET", "/api/health")
        missing = backend.route("GET", "/api/bootstrap")
        wrong = backend.route(
            "GET",
            "/api/bootstrap",
            headers={SESSION_HEADER: "wrong-session-token-with-enough-characters"},
        )
        correct = backend.route(
            "GET", "/api/bootstrap", headers={SESSION_HEADER: TEST_SESSION_CREDENTIAL}
        )

        self.assertEqual(200, health.status)
        self.assertEqual(401, missing.status)
        self.assertEqual("authentication_required", missing.body["error"]["code"])
        self.assertEqual(403, wrong.status)
        self.assertEqual("authentication_failed", wrong.body["error"]["code"])
        self.assertEqual(200, correct.status)
        self.assertIn("safe_roots", correct.body["data"])

        preflight_missing = backend.route("OPTIONS", "/api/bootstrap")
        preflight_correct = backend.route(
            "OPTIONS",
            "/api/bootstrap",
            headers={SESSION_HEADER: TEST_SESSION_CREDENTIAL},
        )
        self.assertEqual(401, preflight_missing.status)
        self.assertEqual(204, preflight_correct.status)

    def test_session_token_is_removed_from_responses_history_logs_and_diagnostics(self) -> None:
        backend = self.desktop_backend()

        protected = backend.protect({"secret": TEST_SESSION_CREDENTIAL})
        backend._save_history([{"summary": TEST_SESSION_CREDENTIAL}])
        backend.record_runtime_event("redaction_test", {"secret": TEST_SESSION_CREDENTIAL})
        backend.record_crash(RuntimeError(TEST_SESSION_CREDENTIAL))

        self.assertNotIn(TEST_SESSION_CREDENTIAL, json.dumps(protected))
        for path in backend.app_paths.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(TEST_SESSION_CREDENTIAL, path.read_text(encoding="utf-8"))

    def test_desktop_mode_never_returns_wildcard_cors(self) -> None:
        server = StarBridgeHttpServer(self.desktop_backend(), port=0)
        server.start()
        try:
            status, headers, payload = self.request(
                server,
                "GET",
                "/api/bootstrap",
                headers={
                    SESSION_HEADER: TEST_SESSION_CREDENTIAL,
                    "Origin": "tauri://localhost",
                },
            )
        finally:
            server.stop()

        self.assertEqual(403, status)
        self.assertEqual("origin_not_allowed", payload["error"]["code"])
        self.assertNotEqual("*", headers.get("access-control-allow-origin"))
        self.assertEqual("no-store", headers["cache-control"])

    def test_development_cors_echoes_only_an_explicit_allowed_origin(self) -> None:
        backend = StarBridgeBackend(app_data_dir=self.root / "development")
        server = StarBridgeHttpServer(backend, port=0)
        server.start()
        try:
            status, headers, _ = self.request(
                server,
                "GET",
                "/api/health",
                headers={"Origin": "http://127.0.0.1:5173"},
            )
        finally:
            server.stop()

        self.assertEqual(200, status)
        self.assertEqual("http://127.0.0.1:5173", headers["access-control-allow-origin"])
        self.assertNotEqual("*", headers["access-control-allow-origin"])

    def test_request_body_size_and_content_type_are_enforced(self) -> None:
        backend = self.desktop_backend(max_request_body_bytes=32)
        server = StarBridgeHttpServer(backend, port=0)
        server.start()
        try:
            too_large = self.request(
                server,
                "POST",
                "/api/tools/call",
                body=b"{" + (b"x" * 64) + b"}",
                headers={
                    SESSION_HEADER: TEST_SESSION_CREDENTIAL,
                    "Content-Type": "application/json",
                },
            )
            wrong_type = self.request(
                server,
                "POST",
                "/api/tools/call",
                body=b"{}",
                headers={
                    SESSION_HEADER: TEST_SESSION_CREDENTIAL,
                    "Content-Type": "text/plain",
                },
            )
        finally:
            server.stop()

        self.assertEqual(413, too_large[0])
        self.assertEqual("request_too_large", too_large[2]["error"]["code"])
        self.assertEqual(415, wrong_type[0])
        self.assertEqual("unsupported_content_type", wrong_type[2]["error"]["code"])

    def test_invalid_content_length_is_rejected(self) -> None:
        server = StarBridgeHttpServer(self.desktop_backend(), port=0)
        server.start()
        connection = HTTPConnection(server.host, server.port, timeout=5)
        try:
            connection.putrequest("POST", "/api/tools/call")
            connection.putheader("Content-Length", "not-a-number")
            connection.putheader("Content-Type", "application/json")
            connection.putheader(SESSION_HEADER, TEST_SESSION_CREDENTIAL)
            connection.endheaders()
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()
            server.stop()

        self.assertEqual(400, response.status)
        self.assertEqual("invalid_content_length", payload["error"]["code"])

    def test_app_data_override_creates_only_documented_subdirectories(self) -> None:
        target = self.root / "中文 路径" / "StarBridge"
        with patch.dict(os.environ, {APP_DATA_ENV: str(target)}):
            paths = resolve_app_data_paths()

        self.assertEqual(target.resolve(), paths.root)
        self.assertEqual(
            {
                "data",
                "history",
                "logs",
                "cache",
                "diagnostics",
                "projects",
                "jobs",
                "artifacts",
                "evidence",
                "deliveries",
            },
            {item.name for item in paths.root.iterdir()},
        )

    def test_history_round_trip_uses_app_data_history_directory(self) -> None:
        backend = StarBridgeBackend(app_data_dir=self.root / "round trip")
        backend.route("GET", "/api/recipes/comfyui_txt2img_lifecycle/plan")

        reloaded = StarBridgeBackend(app_data_dir=self.root / "round trip")
        history = reloaded.route("GET", "/api/audit/history")

        self.assertEqual(reloaded.app_paths.history_file, reloaded.history_path)
        self.assertEqual(1, history.body["data"]["event_count"])

    def test_authenticated_shutdown_stops_server_cleanly(self) -> None:
        server = StarBridgeHttpServer(self.desktop_backend(), port=0)
        server.start()

        status, _, payload = self.request(
            server,
            "POST",
            "/api/lifecycle/shutdown",
            body=b"{}",
            headers={
                SESSION_HEADER: TEST_SESSION_CREDENTIAL,
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(202, status)
        self.assertEqual("stopping", payload["data"]["status"])
        self.assertTrue(server.wait(timeout=5))
        server.stop()
        events = [
            json.loads(line)
            for line in server.backend.app_paths.runtime_log.read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        self.assertEqual("server_stopped", events[-1]["event"])

    def test_parent_monitor_requests_stop_when_parent_is_absent(self) -> None:
        stopped = Event()
        monitor = ParentProcessMonitor(2_147_483_647, stopped.set, poll_interval=0.01)
        monitor.start()
        try:
            self.assertTrue(stopped.wait(timeout=2))
        finally:
            monitor.stop()

    def test_desktop_cli_emits_token_free_ready_line_and_accepts_shutdown(self) -> None:
        environment = os.environ.copy()
        environment[SESSION_TOKEN_ENV] = TEST_SESSION_CREDENTIAL
        environment[APP_DATA_ENV] = str(self.root / "cli app data")
        environment["PYTHONUTF8"] = "1"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "starbridge_mcp.backend",
                "--desktop",
                "--parent-pid",
                str(os.getpid()),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        output_queue: queue.Queue[str] = queue.Queue()

        def read_ready() -> None:
            if process.stdout is not None:
                output_queue.put(process.stdout.readline())

        reader = Thread(target=read_ready, daemon=True)
        reader.start()
        try:
            ready_line = output_queue.get(timeout=10).strip()
            self.assertTrue(ready_line.startswith(READY_PREFIX), ready_line)
            self.assertNotIn(TEST_SESSION_CREDENTIAL, ready_line)
            ready = json.loads(ready_line[len(READY_PREFIX) :])
            self.assertEqual("127.0.0.1", ready["host"])
            self.assertGreater(ready["port"], 0)

            connection = HTTPConnection("127.0.0.1", ready["port"], timeout=5)
            connection.request(
                "POST",
                "/api/lifecycle/shutdown",
                body=b"{}",
                headers={
                    SESSION_HEADER: TEST_SESSION_CREDENTIAL,
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(202, response.status)
            self.assertEqual(0, process.wait(timeout=10))
            stderr = process.stderr.read() if process.stderr is not None else ""
            self.assertNotIn(TEST_SESSION_CREDENTIAL, stderr)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
