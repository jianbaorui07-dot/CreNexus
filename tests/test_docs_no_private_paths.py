from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_TEXT = (
    "C:\\Users\\",
    "Desktop",
    "Downloads",
    "WeChat",
    "微信",
    "jianbaorui07",
    "Program Files\\Adobe",
    "Adobe\\Adobe Photoshop",
    "Adobe\\Adobe Illustrator",
)
DOCS_TO_SCAN = (
    "CHANGELOG.md",
    "ROADMAP.md",
    "RELEASE_NOTES_DRAFT.md",
    "VERSION",
    "docs/adobe-demo-gallery.md",
    "docs/adobe-demo-smoke-test.md",
    "docs/assets/adobe-demo/README.md",
)


class DocsNoPrivatePathsTests(unittest.TestCase):
    def test_release_docs_do_not_contain_private_path_markers(self) -> None:
        for relative in DOCS_TO_SCAN:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            for marker in BANNED_TEXT:
                with self.subTest(file=relative, marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
