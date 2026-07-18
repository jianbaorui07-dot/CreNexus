from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starbridge_mcp.backend import SESSION_HEADER, StarBridgeBackend
from starbridge_mcp.core.app_data import APP_DATA_ENV, resolve_app_data_paths
from starbridge_mcp.core.desktop_connections import (
    CONNECTOR_BEGIN,
    CONNECTOR_END,
    ConnectionSetupError,
    DesktopConnectionManager,
    pair_desktop_session,
)
from starbridge_mcp.mcp_server import handle_request


def call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    return response["result"]["structuredContent"]


class DesktopConnectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.paths = resolve_app_data_paths(self.root / "app-data")

    def manager(self) -> DesktopConnectionManager:
        return DesktopConnectionManager(
            self.paths,
            codex_app_probe=lambda: True,
            process_probe=lambda: set(),
            install_probe=lambda _names, _env: False,
            comfy_probe=lambda: False,
        )

    def test_pairing_is_explicit_and_scoped_to_current_desktop_session(self) -> None:
        manager = self.manager()
        before = manager.overview()
        self.assertFalse(before["drawing_enabled"])
        self.assertRegex(before["codex"]["pairing_code"], r"^[A-Z2-9]{8}$")

        refused = pair_desktop_session(
            self.paths,
            pairing_code=before["codex"]["pairing_code"],
            confirm_pairing=False,
        )
        self.assertFalse(refused["ok"])
        self.assertEqual("confirmation_required", refused["error"]["code"])

        wrong = pair_desktop_session(
            self.paths,
            pairing_code="ABCDEFGH",
            confirm_pairing=True,
        )
        self.assertFalse(wrong["ok"])
        self.assertEqual("pairing_code_invalid", wrong["error"]["code"])

        paired = pair_desktop_session(
            self.paths,
            pairing_code=before["codex"]["pairing_code"],
            confirm_pairing=True,
        )
        self.assertTrue(paired["ok"])
        self.assertTrue(manager.overview()["drawing_enabled"])
        self.assertNotIn("session_id", json.dumps(paired))

        restarted = self.manager()
        self.assertFalse(restarted.overview()["drawing_enabled"])
        self.assertNotEqual(
            before["codex"]["pairing_code"], restarted.overview()["codex"]["pairing_code"]
        )

    def test_connector_install_preserves_other_config_and_is_idempotent(self) -> None:
        manager = self.manager()
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        config = codex_home / "config.toml"
        config.write_text('model = "gpt-5.6"\n', encoding="utf-8")

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
            first = manager.install_codex_connector(confirm_install=True)
            second = manager.install_codex_connector(confirm_install=True)

        contents = config.read_text(encoding="utf-8")
        self.assertTrue(first["installed"])
        self.assertTrue(second["installed"])
        self.assertIn('model = "gpt-5.6"', contents)
        self.assertEqual(1, contents.count(CONNECTOR_BEGIN))
        self.assertEqual(1, contents.count(CONNECTOR_END))
        self.assertIn("mcp_servers.starbridge-desktop", contents)
        self.assertNotIn("auth.json", contents)
        self.assertNotIn("token", contents.lower())

    def test_mcp_pair_tool_schema_and_guarded_write(self) -> None:
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert listed is not None
        tools = {item["name"]: item for item in listed["result"]["tools"]}
        tool = tools["starbridge.desktop_pair"]
        self.assertFalse(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["requiresConfirmation"])
        self.assertEqual(
            ["pairing_code", "confirm_pairing", "confirm_write"],
            tool["inputSchema"]["required"],
        )

        manager = self.manager()
        code = manager.overview()["codex"]["pairing_code"]
        with patch.dict(os.environ, {APP_DATA_ENV: str(self.paths.root)}):
            refused = call_tool(
                "starbridge.desktop_pair",
                {
                    "pairing_code": code,
                    "confirm_pairing": False,
                    "confirm_write": True,
                    "dry_run": False,
                },
            )
            paired = call_tool(
                "starbridge.desktop_pair",
                {
                    "pairing_code": code,
                    "confirm_pairing": True,
                    "confirm_write": True,
                    "dry_run": False,
                },
            )

        self.assertFalse(refused["ok"])
        self.assertTrue(paired["ok"])
        self.assertTrue(manager.overview()["drawing_enabled"])

    def test_desktop_api_enforces_pairing_before_vectorization(self) -> None:
        credential = "desktop-test-credential-0000000000000000000000000001"
        backend = StarBridgeBackend(
            app_data_dir=self.root / "backend-data",
            session_credential=credential,
            mode="desktop",
        )
        headers = {SESSION_HEADER: credential}
        connections = backend.route("GET", "/api/connections", headers=headers)
        self.assertEqual(200, connections.status)
        self.assertFalse(connections.body["data"]["drawing_enabled"])

        locked = backend.route(
            "POST",
            "/api/vectorization/jobs",
            raw_body=b"{}",
            headers=headers,
        )
        self.assertEqual(409, locked.status)
        self.assertEqual("codex_association_required", locked.body["error"]["code"])

        paired = pair_desktop_session(
            backend.app_paths,
            pairing_code=connections.body["data"]["codex"]["pairing_code"],
            confirm_pairing=True,
        )
        self.assertTrue(paired["ok"])
        unlocked = backend.route(
            "POST",
            "/api/vectorization/jobs",
            raw_body=b"{}",
            headers=headers,
        )
        self.assertEqual(400, unlocked.status)
        self.assertEqual("confirmation_required", unlocked.body["error"]["code"])

    def test_creative_application_pairing_requires_codex_and_tracks_verified_bridge(self) -> None:
        manager = DesktopConnectionManager(
            self.paths,
            codex_app_probe=lambda: True,
            process_probe=lambda: {"photoshop.exe"},
            install_probe=lambda _names, _env: False,
            comfy_probe=lambda: False,
            bridge_probe=lambda application_id: application_id == "photoshop",
        )
        with self.assertRaises(ConnectionSetupError) as blocked:
            manager.pair_application("photoshop", confirm_pairing=True)
        self.assertEqual("codex_association_required", blocked.exception.code)

        code = manager.overview()["codex"]["pairing_code"]
        pair_desktop_session(self.paths, pairing_code=code, confirm_pairing=True)
        paired = manager.pair_application("photoshop", confirm_pairing=True)
        self.assertTrue(paired["paired"])
        self.assertEqual("paired", paired["pairing_state"])
        self.assertTrue(paired["bridge_available"])
        self.assertNotIn(str(self.root), json.dumps(paired))

        reconnected = manager.reconnect_application("photoshop", confirm_reconnect=True)
        self.assertEqual("paired", reconnected["pairing_state"])
        disconnected = manager.disconnect_application("photoshop", confirm_disconnect=True)
        self.assertFalse(disconnected["paired"])
        self.assertEqual("ready_to_pair", disconnected["pairing_state"])

    def test_process_only_application_pairing_is_truthfully_limited(self) -> None:
        manager = DesktopConnectionManager(
            self.paths,
            codex_app_probe=lambda: True,
            process_probe=lambda: {"blender.exe"},
            install_probe=lambda _names, _env: False,
            comfy_probe=lambda: False,
            bridge_probe=lambda _application_id: False,
        )
        code = manager.overview()["codex"]["pairing_code"]
        pair_desktop_session(self.paths, pairing_code=code, confirm_pairing=True)

        paired = manager.pair_application("blender", confirm_pairing=True)
        self.assertTrue(paired["paired"])
        self.assertFalse(paired["bridge_available"])
        self.assertEqual("paired_limited", paired["pairing_state"])
        self.assertEqual("session_detection", paired["control_level"])

        manager.reset_pairing()
        current = next(
            item for item in manager.overview()["applications"] if item["id"] == "blender"
        )
        self.assertFalse(current["paired"])
        self.assertEqual("ready_to_pair", current["pairing_state"])

    def test_application_pairing_api_lifecycle_uses_fixed_ids_and_confirmations(self) -> None:
        credential = "desktop-test-credential-0000000000000000000000000002"
        backend = StarBridgeBackend(
            app_data_dir=self.root / "backend-pair-data",
            session_credential=credential,
            mode="desktop",
        )
        headers = {SESSION_HEADER: credential}
        backend.connections._process_probe = lambda: {"blender.exe"}
        backend.connections._install_probe = lambda _names, _env: False
        backend.connections._bridge_probe = lambda _application_id: False
        overview = backend.route("GET", "/api/connections", headers=headers)
        pair_desktop_session(
            backend.app_paths,
            pairing_code=overview.body["data"]["codex"]["pairing_code"],
            confirm_pairing=True,
        )

        refused = backend.route(
            "POST",
            "/api/connections/applications/pair",
            raw_body=b'{"application_id":"blender","confirm_pairing":false}',
            headers=headers,
        )
        self.assertEqual(409, refused.status)
        self.assertEqual("confirmation_required", refused.body["error"]["code"])

        paired = backend.route(
            "POST",
            "/api/connections/applications/pair",
            raw_body=b'{"application_id":"blender","confirm_pairing":true}',
            headers=headers,
        )
        self.assertEqual(200, paired.status)
        self.assertEqual("paired_limited", paired.body["data"]["pairing_state"])

        disconnected = backend.route(
            "POST",
            "/api/connections/applications/disconnect",
            raw_body=b'{"application_id":"blender","confirm_disconnect":true}',
            headers=headers,
        )
        self.assertEqual(200, disconnected.status)
        self.assertFalse(disconnected.body["data"]["paired"])


if __name__ == "__main__":
    unittest.main()
