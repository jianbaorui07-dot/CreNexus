from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class OutputGitignoreTests(unittest.TestCase):
    def git_check_ignore(self, path: str) -> bool:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=REPO_ROOT,
            check=False,
        )
        return completed.returncode == 0

    def test_generated_output_formats_are_ignored(self) -> None:
        for suffix in ("png", "jpg", "jpeg", "webp", "svg", "pdf", "psd", "ai", "json"):
            with self.subTest(suffix=suffix):
                self.assertTrue(self.git_check_ignore(f"examples/output/illustrator/demo.{suffix}"))

    def test_output_readme_and_gitkeep_are_not_ignored(self) -> None:
        self.assertFalse(self.git_check_ignore("examples/output/.gitkeep"))
        self.assertFalse(self.git_check_ignore("examples/output/README.md"))
