from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "starbridge_preflight.py"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

spec = importlib.util.spec_from_file_location("starbridge_preflight", SCRIPT_PATH)
starbridge_preflight = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(starbridge_preflight)


class StarbridgePreflightTest(unittest.TestCase):
    def test_run_checks_passes_current_repository_contracts(self) -> None:
        results = starbridge_preflight.run_checks()

        self.assertGreaterEqual(len(results), 4)
        self.assertTrue(all(item["status"] == "pass" for item in results), results)

    def test_markdown_output_contains_all_gate_names(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--markdown"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn("| security | pass |", completed.stdout)
        self.assertIn("| bridge_metadata | pass |", completed.stdout)
        self.assertIn("| sample_reports | pass |", completed.stdout)
        self.assertIn("| bridge_capabilities | pass |", completed.stdout)
        self.assertIn("| markdown_links | pass |", completed.stdout)

    def test_documentation_mentions_preflight_entrypoints(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        package_json = (REPO_ROOT / "package.json").read_text(encoding="utf-8")

        self.assertIn("python scripts\\starbridge_preflight.py --markdown", readme)
        self.assertIn("python scripts\\starbridge_preflight.py --write-report --soft-exit", readme)
        self.assertIn(
            '"preflight": "python scripts/starbridge_preflight.py --markdown"', package_json
        )
        self.assertIn(
            '"bridge:capabilities": "python scripts/bridge_capability_matrix.py --markdown"',
            package_json,
        )

    def test_write_report_creates_json_and_markdown_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--write-report",
                    "--soft-exit",
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )

            json_report = report_dir / "starbridge_preflight_report.json"
            markdown_report = report_dir / "starbridge_preflight_report.md"
            self.assertTrue(json_report.exists(), completed.stdout)
            self.assertTrue(markdown_report.exists(), completed.stdout)
            self.assertTrue(json.loads(json_report.read_text(encoding="utf-8"))["ok"])
            self.assertIn("| security | pass |", markdown_report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
