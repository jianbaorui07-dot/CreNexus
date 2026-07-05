"""Unit tests for the strict=true safety guard on the Photoshop bridge.

These do *not* require Photoshop, node_proxy, or UXP. They monkeypatch the
node_proxy probe to simulate a disconnected UXP client and verify that the
adapter refuses to silently fall back to mock behavior. Pairing with the real
e2e tests in test_photoshop_real_export_e2e.py keeps "real link asserted" and
"mock-falls-back-loudly" cleanly separated.
"""

from __future__ import annotations

import unittest
from unittest import mock

from starbridge_mcp.adapters.photoshop import bridge as bridge_module
from starbridge_mcp.mcp_server import handle_request


def _disconnected_proxy_probe() -> dict:
    status = {
        "ok": False,
        "node_proxy_running": False,
        "uxp_client_connected": False,
        "photoshop_host_seen": False,
        "message": "node_proxy_unavailable: simulated",
    }
    return {
        "health": status,
        "status": status,
        "node_proxy_running": False,
        "uxp_client_connected": False,
        "photoshop_host_seen": False,
    }


def _call(name: str, arguments: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 7001,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    response = handle_request(payload)
    assert response is not None
    return response["result"]["structuredContent"]


class StrictModeTests(unittest.TestCase):
    def test_strict_probe_fails_when_only_mock_is_available(self) -> None:
        with (
            mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe),
            mock.patch.object(bridge_module, "_probe_com", return_value=(False, {}, None)),
        ):
            result = _call("ps.probe", {"strict": True})
        self.assertFalse(result["ok"], msg=result)
        self.assertEqual("mock", result["details"]["bridge_kind"])
        self.assertIn("strict=true", result["message"])

    def test_strict_probe_passes_without_strict(self) -> None:
        with (
            mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe),
            mock.patch.object(bridge_module, "_probe_com", return_value=(False, {}, None)),
        ):
            result = _call("ps.probe", {})
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual("mock", result["details"]["bridge_kind"])

    def test_strict_preview_export_dry_run_refuses_mock(self) -> None:
        with mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe):
            result = _call(
                "ps.preview.export",
                {
                    "dry_run": True,
                    "strict": True,
                    "output_dir": "examples/output/photoshop",
                },
            )
        self.assertFalse(result["ok"], msg=result)
        self.assertEqual("mock", result["details"]["bridge_kind"])
        manifest_errors = result["details"]["evidence_manifest"]["errors"]
        self.assertTrue(
            any("strict=true" in err for err in manifest_errors),
            msg=manifest_errors,
        )

    def test_strict_preview_export_real_run_refuses_placeholder(self) -> None:
        with mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe):
            result = _call(
                "ps.preview.export",
                {
                    "dry_run": False,
                    "writes_files": True,
                    "requires_confirmation": True,
                    "confirm_write": True,
                    "strict": True,
                    "output_dir": "examples/output/photoshop",
                },
            )
        self.assertFalse(result["ok"], msg=result)
        self.assertEqual(0, len(result["details"]["preview_files"]))
        self.assertEqual(0, len(result["details"]["output_artifacts"]))

    def test_non_strict_real_run_refuses_placeholder_by_default(self) -> None:
        with mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe):
            result = _call(
                "ps.preview.export",
                {
                    "dry_run": False,
                    "writes_files": True,
                    "requires_confirmation": True,
                    "confirm_write": True,
                    "output_dir": "sandbox",
                },
            )
        self.assertFalse(result["ok"], msg=result)
        self.assertEqual("mock", result["details"]["bridge_kind"])
        self.assertEqual(0, len(result["details"]["preview_files"]))
        self.assertEqual(0, len(result["details"]["output_artifacts"]))
        self.assertFalse(result["details"]["real_output_verified"])

    def test_non_strict_real_run_allows_marked_placeholder_when_explicit(self) -> None:
        with mock.patch.object(bridge_module, "_node_proxy_probe", _disconnected_proxy_probe):
            result = _call(
                "ps.preview.export",
                {
                    "dry_run": False,
                    "writes_files": True,
                    "requires_confirmation": True,
                    "confirm_write": True,
                    "allow_placeholder": True,
                    "output_dir": "sandbox",
                },
            )
        self.assertTrue(result["ok"], msg=result)
        self.assertEqual("mock", result["details"]["bridge_kind"])
        self.assertEqual(1, len(result["details"]["preview_files"]))
        self.assertFalse(result["details"]["real_output_verified"])
        self.assertFalse(result["details"]["evidence_manifest"]["photoshop_available"])
        artifact = result["details"]["output_artifacts"][0]
        self.assertTrue(artifact["placeholder"])


if __name__ == "__main__":
    unittest.main()
