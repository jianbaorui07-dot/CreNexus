from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANVAS_ROOT = REPO_ROOT / "examples" / "starbridge_canvas"


class StarBridgeCanvasTest(unittest.TestCase):
    def test_canvas_example_declares_expected_runtime(self) -> None:
        package = json.loads((CANVAS_ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual("starbridge-canvas", package["name"])
        self.assertEqual("vite", package["scripts"]["dev"])
        self.assertEqual("vite build", package["scripts"]["build"])
        for dependency in ("react", "react-dom", "tldraw", "vite", "fractional-indexing"):
            self.assertIn(dependency, package["dependencies"])

    def test_realtime_canvas_endpoints_are_wired(self) -> None:
        vite_config = (CANVAS_ROOT / "vite.config.js").read_text(encoding="utf-8")
        app = (CANVAS_ROOT / "src" / "App.jsx").read_text(encoding="utf-8")

        self.assertIn("/api/canvas-events", vite_config)
        self.assertIn("/api/canvas-live", vite_config)
        self.assertIn("drawing-event", vite_config)
        self.assertIn("broadcastDrawingEvent", vite_config)
        self.assertIn("STARBRIDGE_CANVAS_PROJECT_DIR", vite_config)
        self.assertIn("STARBRIDGE_CANVAS_DIR", vite_config)

        self.assertIn("CANVAS_LIVE_ENDPOINT", app)
        self.assertIn("EventSource", app)
        self.assertIn("drawing-event", app)
        self.assertIn("starbridge-live-status", app)
        self.assertIn("summarizeStoreChanges", app)

    def test_canvas_mcp_exposes_starbridge_tools(self) -> None:
        server = (CANVAS_ROOT / "mcp" / "server.mjs").read_text(encoding="utf-8")

        self.assertIn("StarBridge Canvas MCP", server)
        self.assertIn("get_starbridge_canvas_selection", server)
        self.assertIn("insert_starbridge_canvas_image", server)
        self.assertIn("STARBRIDGE_CANVAS_URL", server)
        self.assertIn("get_cowart_selection", server)
        self.assertIn("insert_cowart_image", server)

    def test_start_script_sets_canvas_environment(self) -> None:
        script = (REPO_ROOT / "scripts" / "start_starbridge_canvas.ps1").read_text(encoding="utf-8")

        self.assertIn("STARBRIDGE_CANVAS_PROJECT_DIR", script)
        self.assertIn("STARBRIDGE_CANVAS_DIR", script)
        self.assertIn("STARBRIDGE_CANVAS_URL", script)
        self.assertIn("npm.cmd", script)
        self.assertIn("--package-lock=false", script)

    def test_canvas_skill_and_docs_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "docs" / "starbridge-canvas.md").exists())
        self.assertTrue((CANVAS_ROOT / "README.md").exists())
        self.assertTrue(
            (REPO_ROOT / ".codex" / "skills" / "starbridge-canvas-mcp" / "SKILL.md").exists()
        )


if __name__ == "__main__":
    unittest.main()
