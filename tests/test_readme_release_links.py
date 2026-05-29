from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReadmeReleaseLinksTests(unittest.TestCase):
    def test_readme_links_release_polish_docs(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for link in (
            "docs/adobe-demo-gallery.md",
            "docs/adobe-demo-smoke-test.md",
            "RELEASE_NOTES_DRAFT.md",
        ):
            with self.subTest(link=link):
                self.assertIn(link, text)


if __name__ == "__main__":
    unittest.main()
