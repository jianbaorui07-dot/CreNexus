from __future__ import annotations

import subprocess
import sys
import unittest

from scripts import security_check


class SecurityCheckTest(unittest.TestCase):
    def test_forbidden_asset_extensions_are_tracked(self) -> None:
        self.assertIn(".psd", security_check.FORBIDDEN_EXTENSIONS)
        self.assertIn(".dwg", security_check.FORBIDDEN_EXTENSIONS)
        self.assertIn(".ai", security_check.FORBIDDEN_EXTENSIONS)

    def test_example_reports_are_allowed(self) -> None:
        self.assertTrue(
            security_check.is_allowed_example(
                security_check.REPO_ROOT / "sample_report.example.json"
            )
        )

    def test_security_check_script_runs(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(security_check.REPO_ROOT / "scripts" / "security_check.py")],
            cwd=security_check.REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("security check passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
