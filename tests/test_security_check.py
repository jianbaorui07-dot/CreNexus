from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import security_check


class SecurityCheckTest(unittest.TestCase):
    def test_forbidden_asset_extensions_are_tracked(self) -> None:
        self.assertIn(".psd", security_check.FORBIDDEN_EXTENSIONS)
        self.assertIn(".dwg", security_check.FORBIDDEN_EXTENSIONS)
        self.assertIn(".ai", security_check.FORBIDDEN_EXTENSIONS)
        self.assertIn(".blend", security_check.FORBIDDEN_EXTENSIONS)

    def test_local_only_project_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "examples" / "unreal_worldforge_agent" / "manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")

            failures = security_check.find_failures([path], root)

        self.assertEqual(
            ["local-only path is tracked: examples/unreal_worldforge_agent/manifest.json"],
            failures,
        )

    def test_example_reports_are_allowed(self) -> None:
        self.assertTrue(
            security_check.is_allowed_example(
                security_check.REPO_ROOT / "sample_report.example.json"
            )
        )

    def test_github_secret_reference_is_allowed_but_literal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / ".github" / "workflows" / "release.yml"
            workflow.parent.mkdir(parents=True)
            sensitive_name = "PASS" + "WORD"
            workflow.write_text(
                f"TAURI_SIGNING_PRIVATE_KEY_{sensitive_name}: "
                f"${{{{ secrets.TAURI_SIGNING_PRIVATE_KEY_{sensitive_name} }}}}\n",
                encoding="utf-8",
            )
            self.assertEqual([], security_check.find_failures([workflow], root))

            workflow.write_text(
                f"TAURI_SIGNING_PRIVATE_KEY_{sensitive_name}: actual-secret-value\n",
                encoding="utf-8",
            )
            failures = security_check.find_failures([workflow], root)

        self.assertEqual(1, len(failures))
        self.assertIn("sensitive assignment", failures[0])

    def test_powershell_secure_string_must_come_directly_from_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "release.ps1"
            sensitive_name = ("PASS" + "WORD").lower()
            script.write_text(
                f"${sensitive_name} = ConvertTo-SecureString "
                f"$env:SIGNING_{sensitive_name.upper()} -AsPlainText -Force\n",
                encoding="utf-8",
            )
            self.assertEqual([], security_check.find_failures([script], root))

            script.write_text(f'${sensitive_name} = "actual-secret-value"\n', encoding="utf-8")
            failures = security_check.find_failures([script], root)

        self.assertEqual(1, len(failures))
        self.assertIn("sensitive assignment", failures[0])

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
