from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
class BootstrapEntrypointTests(unittest.TestCase):
    def test_profile_is_forwarded_by_name_and_dry_run_returns_json(self) -> None:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "bootstrap.ps1"),
                "-Profile",
                "auto",
                "-SkipNode",
                "-SkipCodexConfig",
                "-DryRun",
                "-Json",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("auto", payload["profile_requested"])
        self.assertIn(payload["profile_applied"], {"core", "standard"})
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
