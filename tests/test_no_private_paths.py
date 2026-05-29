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
)
FILES_TO_SCAN = (
    "docs/demo-illustrator.md",
    "docs/demo-photoshop.md",
    "examples/illustrator_bridge/scripts/document_info.ps1",
    "examples/illustrator_bridge/scripts/create_demo_artboard.ps1",
    "examples/illustrator_bridge/scripts/export_demo_assets.ps1",
    "examples/illustrator_bridge/scripts/run_demo.ps1",
    "examples/illustrator_bridge/jsx/document_info.jsx",
    "examples/illustrator_bridge/jsx/create_demo_artboard.jsx",
    "examples/illustrator_bridge/jsx/export_demo_assets.jsx",
    "examples/illustrator_bridge/write_demo_manifest.py",
    "examples/photoshop_bridge/scripts/create_demo_document.ps1",
    "examples/photoshop_bridge/scripts/export_demo_preview.ps1",
    "examples/photoshop_bridge/scripts/run_demo.ps1",
    "examples/photoshop_bridge/jsx/document_info.jsx",
    "examples/photoshop_bridge/jsx/create_demo_document.jsx",
    "examples/photoshop_bridge/jsx/export_demo_preview.jsx",
    "examples/photoshop_bridge/write_demo_manifest.py",
    "examples/output/README.md",
)


class NoPrivatePathsTests(unittest.TestCase):
    def test_new_adobe_files_do_not_contain_private_path_markers(self) -> None:
        for relative in FILES_TO_SCAN:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            for marker in BANNED_TEXT:
                with self.subTest(file=relative, marker=marker):
                    self.assertNotIn(marker, text)

    def test_new_adobe_files_do_not_contain_real_adobe_install_paths(self) -> None:
        install_markers = (
            "Program Files\\Adobe",
            "Adobe\\Adobe Photoshop",
            "Adobe\\Adobe Illustrator",
        )
        for relative in FILES_TO_SCAN:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            for marker in install_markers:
                with self.subTest(file=relative, marker=marker):
                    self.assertNotIn(marker, text)


if __name__ == "__main__":
    unittest.main()
