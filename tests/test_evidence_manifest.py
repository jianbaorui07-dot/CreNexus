from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.core.evidence import (
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    manifest_validation_result,
    repo_relative,
    save_manifest,
)


class EvidenceManifestTests(unittest.TestCase):
    def test_create_and_validate_manifest(self) -> None:
        manifest = create_manifest(bridge="comfyui", action="workflow_build", job_id="job_123")
        payload = manifest.to_dict()

        self.assertEqual("queued", payload["status"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual("job_123", payload["job_id"])
        self.assertTrue(manifest_validation_result(payload).ok)

    def test_status_vocabulary_is_enforced(self) -> None:
        with self.assertRaises(ValueError):
            create_manifest(status="done")

    def test_manifest_path_stays_inside_evidence_root(self) -> None:
        target = ensure_evidence_path("examples/output/evidence/custom.json")
        self.assertEqual("examples/output/evidence/custom.json", repo_relative(target))
        with self.assertRaises(ValueError):
            ensure_evidence_path("examples/output/escaped.json")

    def test_saved_manifest_uses_redacted_paths(self) -> None:
        manifest = create_manifest()
        manifest.add_output_file(r"C:\Users\<USER_HOME>\Desktop\secret.png", label="secret")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "manifest.json"
            safe_target = ensure_evidence_path(Path("examples/output/evidence") / target.name)
            save_manifest(manifest, safe_target)
            payload = load_manifest(safe_target)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(r"C:\Users\<USER_HOME>", text)
        self.assertIn("<REDACTED_PATH>", text)
