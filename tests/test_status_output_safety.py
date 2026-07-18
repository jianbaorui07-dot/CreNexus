from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "AppData", "Desktop", "Documents")


def probe_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "STARBRIDGE_COMFYUI_URL",
        "COMFY_BASE_URL",
        "COMFY_ROOT",
        "COMFY_LAUNCHER",
        "BLENDER_EXE",
        "BLENDER_MCP_DIR",
        "AUTOCAD_EXE",
        "PHOTOSHOP_EXE",
        "ILLUSTRATOR_EXE",
        "JIANYING_EXE",
        "JIANYING_DRAFTS_DIR",
        "CAPCUT_EXE",
        "CAPCUT_DRAFTS_DIR",
    ):
        env.pop(key, None)
    env["STARBRIDGE_COMFYUI_URL"] = "http://127.0.0.1:9"
    return env


class StatusOutputSafetyTests(unittest.TestCase):
    def assert_no_private_paths(self, text: str) -> None:
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_server_json_exit_code_and_schema_are_stable(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "--json"],
            cwd=REPO_ROOT,
            env=probe_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_no_private_paths(completed.stdout)
        payload = json.loads(completed.stdout)
        required = {"ok", "bridge", "action", "message", "details", "warnings", "next_steps"}
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertEqual(required, set(result))

    def test_server_strict_fails_when_bridge_is_not_ready(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "--json", "--strict"],
            cwd=REPO_ROOT,
            env=probe_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_no_private_paths(completed.stdout)

    def test_legacy_bridge_status_json_exit_code_and_output_are_safe(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "examples" / "bridge_status.py"),
                "--json",
                "--redact-paths",
                "--soft-exit",
            ],
            cwd=REPO_ROOT,
            env=probe_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_no_private_paths(completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["results"])
        by_name = {item["name"]: item for item in payload["results"]}
        for name in ("Photoshop", "Illustrator"):
            self.assertEqual("warn", by_name[name]["status"])
            self.assertFalse(by_name[name]["data"]["connection_verified"])


if __name__ == "__main__":
    unittest.main()
