from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "uxp" / "illustrator-bridge"


class IllustratorUxpBridgeTests(unittest.TestCase):
    def test_state_v2_schema_excludes_private_names_and_paths(self):
        schema = json.loads(
            (
                ROOT
                / "examples"
                / "illustrator_bridge"
                / "protocols"
                / "realtime_state.v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(2, schema["properties"]["protocol_version"]["const"])
        self.assertFalse(schema["additionalProperties"])
        serialized = json.dumps(schema)
        for forbidden in ("document_name", "layer_name", "file_path", "font", "linked"):
            self.assertNotIn(forbidden, serialized)

    def test_manifest_is_local_network_only(self):
        manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
        domains = manifest["requiredPermissions"]["network"]["domains"]
        self.assertTrue(domains)
        self.assertTrue(all("127.0.0.1:8972" in value for value in domains))
        self.assertNotIn("localFileSystem", manifest["requiredPermissions"])

    def test_protocol_has_only_allowlisted_methods(self):
        source = (PLUGIN / "src" / "protocol.js").read_text(encoding="utf-8")
        for method in (
            "get_state",
            "document_info",
            "select_object",
            "set_fill",
            "move_object",
            "create_path",
            "zoom_to_selection",
            "apply_artisan_map",
            "readback_artisan_map",
            "commit_artisan_map",
            "rollback_artisan_map",
        ):
            self.assertIn(f"illustrator.{method}", source)
        self.assertNotIn("run_jsx", source)
        self.assertNotIn("eval(", source)
        schema = json.loads(
            (
                ROOT
                / "examples"
                / "illustrator_bridge"
                / "protocols"
                / "realtime_command.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            "^item:[1-9][0-9]*$",
            schema["properties"]["params"]["properties"]["object_id"]["pattern"],
        )

    def test_write_confirmation_guard_exists(self):
        source = (PLUGIN / "src" / "protocol.js").read_text(encoding="utf-8")
        self.assertIn("confirm_write", source)
        self.assertIn("WRITE_METHODS", source)
        self.assertIn("illustrator.apply_artisan_map", source)
        self.assertIn("illustrator.rollback_artisan_map", source)

    def test_artisan_host_has_transaction_readback_and_rollback(self):
        source = (PLUGIN / "src" / "host-adapter.js").read_text(encoding="utf-8")
        self.assertIn("nameTransactions", source)
        self.assertIn("applyArtisanMap", source)
        self.assertIn("readbackArtisanMap", source)
        self.assertIn("commitArtisanMap", source)
        self.assertIn("rollbackArtisanMap", source)
        self.assertIn("artisan_apply_failed_rollback_completed", source)

    def test_host_adapter_does_not_expose_paths(self):
        source = (PLUGIN / "src" / "host-adapter.js").read_text(encoding="utf-8")
        self.assertNotIn("fullName", source)
        self.assertNotIn("filePath", source)
        self.assertNotIn("linkedItems", source)
        self.assertNotIn("document.name", source)
        self.assertNotIn("layer?.name", source)
        self.assertNotIn("board?.name", source)
        self.assertIn("protocol_version: 2", source)

    def test_panel_displays_codex_live_updates(self):
        html = (PLUGIN / "index.html").read_text(encoding="utf-8")
        source = (PLUGIN / "src" / "bridge-client.js").read_text(encoding="utf-8")
        for element_id in ("session-phase", "session-step", "session-progress", "session-mode"):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn('message?.type === "codex_session"', source)
        self.assertIn("this.onSession(message)", source)


if __name__ == "__main__":
    unittest.main()
