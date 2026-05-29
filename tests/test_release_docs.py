from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocsTests(unittest.TestCase):
    def test_release_documentation_files_exist(self) -> None:
        for relative in (
            "CHANGELOG.md",
            "ROADMAP.md",
            "RELEASE_NOTES_DRAFT.md",
            "VERSION",
            "docs/adobe-demo-gallery.md",
            "docs/adobe-demo-smoke-test.md",
        ):
            with self.subTest(path=relative):
                self.assertTrue((REPO_ROOT / relative).exists())

    def test_version_is_0_1_0(self) -> None:
        self.assertEqual("0.1.0", (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
