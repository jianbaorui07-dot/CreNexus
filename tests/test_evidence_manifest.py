from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.core.evidence import (
    EvidenceManifest,
    ValidationResult,
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    manifest_validation_result,
    repo_relative,
    sanitize_path_string,
    save_manifest,
)


class EvidenceManifestTests(unittest.TestCase):
    def test_create_and_validate_manifest(self) -> None:
        manifest = create_manifest(bridge="comfyui", action="workflow_build", job_id="job_123")
        payload = manifest.to_dict()

        self.assertEqual("queued", payload["status"])
        self.assertTrue(payload["dry_run"])
        self.assertEqual("job_123", payload["job_id"])
        self.assertIn("quality_gates", payload)
        self.assertIn("asset_manifest", payload)
        self.assertTrue(manifest_validation_result(payload).ok)

    def test_manifest_carries_quality_gates_and_asset_manifest(self) -> None:
        manifest = create_manifest(bridge="blender", action="recipe_evidence")
        manifest.add_quality_gate(
            ValidationResult(name="same_camera_compare", ok=True, message="declared gate")
        )
        manifest.add_asset("examples/output/evidence/render_compare.json", label="compare")
        payload = manifest.to_dict()

        self.assertEqual("same_camera_compare", payload["quality_gates"][0]["name"])
        self.assertEqual("compare", payload["asset_manifest"][0]["label"])
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

    def test_manifest_redacts_structured_posix_temporary_paths(self) -> None:
        temporary_roots = (
            "/tmp",
            "/private/tmp",
            "/var/tmp",
            "/private/var/tmp",
            "/var/folders",
            "/private/var/folders",
        )
        temporary_paths = temporary_roots + tuple(
            f"{root}/job/manifest.latest.json" for root in temporary_roots
        ) + (
            "/private//tmp/secret.png",
            "/var//tmp/secret.png",
            "/private/var//folders/ab/T/secret.png",
            "//tmp",
            "//tmp/secret.png",
            "///private///var///tmp",
            "///private///var///tmp/secret.png",
            "/tmp//secret.png",
            "/private//var///folders//ab/T/secret.png",
        )
        for path in temporary_paths:
            with self.subTest(path=path):
                self.assertEqual("<REDACTED_PATH>", sanitize_path_string(path))
                with patch(
                    "starbridge_mcp.core.evidence.ensure_evidence_path",
                    return_value=Path(path),
                ):
                    manifest = create_manifest()
                self.assertEqual(["<REDACTED_PATH>"], manifest.redacted_paths)

        similar_roots = (
            "/tmpfile/public.json",
            "/tmp.foo",
            "/private/tmpfile/public.json",
            "/private//tmpfile/public.json",
            "/var/tmp-public/public.json",
            "/var/tmpish/public.json",
            "/var//tmpish/public.json",
            "/private/var/tmp-public/public.json",
            "/var/folders-public/public.json",
            "/private/var/folders-public/public.json",
            "tmp/relative.json",
            "private//tmp/relative.json",
            "https://example.test/tmp/secret.png",
            "file:///tmp/secret.png",
            "file:////tmp/secret.png",
            "file://local／host/tmp/secret.png",
            "https://e.test/?local=%252Ftmp%252Fsecret",
            "file:///tmp%252Fsecret",
        )
        for path in similar_roots:
            with self.subTest(path=path):
                self.assertEqual(path, sanitize_path_string(path))

    def test_manifest_write_chains_redact_normalized_temporary_paths(self) -> None:
        manifest = EvidenceManifest(bridge="test", action="path_redaction")
        manifest.add_output_file("/private//tmp/output.png")
        manifest.add_screenshot("/var//tmp/screenshot.png")
        manifest.add_asset("/private/var//folders/ab/T/asset.json")

        self.assertEqual("<REDACTED_PATH>", manifest.output_files[0].path)
        self.assertEqual("<REDACTED_PATH>", manifest.screenshots[0].path)
        self.assertEqual("<REDACTED_PATH>", manifest.asset_manifest[0].path)
        self.assertEqual(["<REDACTED_PATH>"] * 3, manifest.redacted_paths)
