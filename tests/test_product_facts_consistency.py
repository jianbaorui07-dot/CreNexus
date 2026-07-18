from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.check_product_facts import check_product_facts, pep440_version

REPO_ROOT = Path(__file__).resolve().parents[1]


class ProductFactsConsistencyTests(unittest.TestCase):
    def test_semver_to_pep440_mapping(self) -> None:
        self.assertEqual("0.1.0a0", pep440_version("0.1.0-alpha.0"))
        self.assertEqual("1.2.3rc4", pep440_version("1.2.3-rc.4"))

    def test_all_machine_readable_product_facts_are_consistent(self) -> None:
        self.assertEqual([], check_product_facts())

    def test_capability_schema_uses_only_canonical_statuses(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "product" / "capability-status.schema.json").read_text(encoding="utf-8")
        )
        statuses = schema["properties"]["capabilityStatus"]["enum"]
        self.assertEqual(["stable", "experimental", "planned", "not_implemented"], statuses)

    def test_check_script_runs(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_product_facts.py"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("product facts check passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
