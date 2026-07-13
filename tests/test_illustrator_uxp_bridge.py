from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "uxp" / "illustrator-bridge"


class IllustratorUxpBridgeTests(unittest.TestCase):
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
        ):
            self.assertIn(f"illustrator.{method}", source)
        self.assertNotIn("run_jsx", source)
        self.assertNotIn("eval(", source)

    def test_write_confirmation_guard_exists(self):
        source = (PLUGIN / "src" / "protocol.js").read_text(encoding="utf-8")
        self.assertIn("confirm_write", source)
        self.assertIn("WRITE_METHODS", source)

    def test_host_adapter_does_not_expose_paths(self):
        source = (PLUGIN / "src" / "host-adapter.js").read_text(encoding="utf-8")
        self.assertNotIn("fullName", source)
        self.assertNotIn("filePath", source)
        self.assertNotIn("linkedItems", source)


if __name__ == "__main__":
    unittest.main()
