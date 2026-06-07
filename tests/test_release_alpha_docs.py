from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseAlphaDocsTest(unittest.TestCase):
    def test_release_docs_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "docs" / "CAPABILITY_MATRIX.md").exists())
        self.assertTrue((REPO_ROOT / "docs" / "RELEASE_V0_1_ALPHA.md").exists())

    def test_capability_matrix_has_requested_columns_and_claims(self) -> None:
        matrix = (REPO_ROOT / "docs" / "CAPABILITY_MATRIX.md").read_text(encoding="utf-8")
        self.assertIn(
            "| Bridge | Capability categories | Stable | Experimental | Planned | Evidence / job lifecycle | Writes files | CI safe | Needs local app | Safety notes |",
            matrix,
        )
        for phrase in ("`starbridge.status`", "`comfyui.workflow_validate`", "Photoshop", "CapCut / Jianying", "EvidenceManifest"):
            self.assertIn(phrase, matrix)

    def test_release_doc_has_required_sections(self) -> None:
        release = (REPO_ROOT / "docs" / "RELEASE_V0_1_ALPHA.md").read_text(encoding="utf-8")
        for heading in (
            "## What is included",
            "## What is not included",
            "## CI checklist",
            "## Security checklist",
            "## Local smoke test checklist",
            "## Known limitations",
            "## Safe demo commands",
        ):
            self.assertIn(heading, release)


if __name__ == "__main__":
    unittest.main()
