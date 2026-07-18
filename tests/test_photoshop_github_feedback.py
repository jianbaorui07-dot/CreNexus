from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starbridge_mcp.adapters.photoshop.semantic_layers.github_feedback import (
    FEEDBACK_SCHEMA_VERSION,
    build_manifest_feedback,
    maybe_submit_manifest_feedback,
    submit_feedback_payload,
    validate_feedback_payload,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.intent import (
    GITHUB_FEEDBACK_CONSENT_VERSION,
    recommended_intent_profile,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.manifest import (
    GROUPS_BOTTOM_TO_TOP,
    SCHEMA_VERSION,
    write_manifest,
)


class PhotoshopGithubFeedbackTests(unittest.TestCase):
    def manifest(self, *, feedback_enabled: bool) -> dict[str, object]:
        profile = recommended_intent_profile("poster_basic")
        profile["feedback"]["github_metrics_upload"] = feedback_enabled
        return {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "name": "private-client-poster.png",
                "sha256": "a" * 64,
                "sha256_12": "a" * 12,
            },
            "canvas": {"width": 2048, "height": 3072, "resolution": 72},
            "strategy": {"id": "poster_basic"},
            "intent": {
                "status": "explicit",
                "profile_sha256": "b" * 64,
                "profile": profile,
            },
            "groups_bottom_to_top": list(GROUPS_BOTTOM_TO_TOP),
            "layers": [
                {
                    "id": "background",
                    "name": "客户背景",
                    "group": "04_背景",
                    "type": "pixel",
                    "source": "layers/private-client-background.png",
                    "z_index": 10,
                }
            ],
            "analysis": {
                "semantic_regions": [
                    {
                        "region_id": "private_person",
                        "semantic_label": "客户姓名",
                    }
                ]
            },
            "quality": {
                "overall_score": 91.23456,
                "recomposition_similarity": 0.97654,
                "requires_manual_review": True,
                "manual_review_reasons": ["客户文字待确认"],
                "background": {"clean_score": 0.91234},
                "semantic_subdivision": {"layer_editability_score": 82.345},
            },
            "pipeline": {
                "version": "starbridge.image_to_editable_psd.pipeline.v9",
            },
        }

    def test_payload_contains_only_allowlisted_aggregated_metrics(self) -> None:
        payload = build_manifest_feedback(
            self.manifest(feedback_enabled=True),
            event_type="run",
            operation_result={"ok": True, "cached": False},
        )
        validate_feedback_payload(payload)
        encoded = json.dumps(payload, ensure_ascii=False).lower()
        self.assertEqual(FEEDBACK_SCHEMA_VERSION, payload["schema_version"])
        self.assertNotIn("private-client", encoded)
        self.assertNotIn("客户", encoded)
        self.assertNotIn("sha256", encoded)
        self.assertNotIn("layers/", encoded)
        self.assertEqual("4_to_16mp", payload["document"]["size_bucket"])
        self.assertEqual(91.235, payload["quality"]["overall"])

    def test_privacy_validator_rejects_forbidden_fields_and_paths(self) -> None:
        payload = build_manifest_feedback(
            self.manifest(feedback_enabled=True),
            event_type="run",
        )
        payload["result"]["source_path"] = "C:\\Users\\client\\secret.png"
        with self.assertRaisesRegex(ValueError, "result fields do not match the allowlist"):
            validate_feedback_payload(payload)

    def test_disabled_consent_never_invokes_github(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            write_manifest(manifest_path, self.manifest(feedback_enabled=False))
            with mock.patch("subprocess.run") as run:
                result = maybe_submit_manifest_feedback(
                    manifest_path,
                    event_type="run",
                    operation_result={"ok": True},
                )
            self.assertEqual("disabled", result["status"])
            self.assertFalse(result["uploaded"])
            run.assert_not_called()

    def test_consented_dry_run_exposes_only_the_safe_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path = Path(temporary) / "manifest.json"
            write_manifest(manifest_path, self.manifest(feedback_enabled=True))
            environment = {
                "STARBRIDGE_FEEDBACK_REPOSITORY": "owner/repository",
                "STARBRIDGE_FEEDBACK_ISSUE": "42",
                "STARBRIDGE_FEEDBACK_DRY_RUN": "1",
            }
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch("subprocess.run") as run,
            ):
                result = maybe_submit_manifest_feedback(
                    manifest_path,
                    event_type="build",
                    operation_result={"ok": True},
                )
            self.assertEqual("dry_run", result["status"])
            self.assertFalse(result["uploaded"])
            validate_feedback_payload(result["payload"])
            self.assertEqual(
                GITHUB_FEEDBACK_CONSENT_VERSION,
                self.manifest(feedback_enabled=True)["intent"]["profile"]["feedback"][
                    "consent_version"
                ],
            )
            run.assert_not_called()

    def test_upload_posts_one_comment_to_the_configured_issue(self) -> None:
        payload = build_manifest_feedback(
            self.manifest(feedback_enabled=True),
            event_type="patch",
            operation_result={"ok": True, "reprocessed_pixels": True},
        )
        environment = {
            "STARBRIDGE_FEEDBACK_REPOSITORY": "owner/repository",
            "STARBRIDGE_FEEDBACK_ISSUE": "42",
        }
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("subprocess.run", return_value=completed) as run,
        ):
            result = submit_feedback_payload(payload)
        self.assertEqual("uploaded", result["status"])
        self.assertTrue(result["uploaded"])
        command = run.call_args.args[0]
        self.assertEqual("gh", command[0])
        self.assertIn("repos/owner/repository/issues/42/comments", command)
        self.assertFalse(run.call_args.kwargs.get("shell", False))
        body = next(item for item in command if item.startswith("body="))
        self.assertIn("starbridge-layer-feedback-v1", body)
        self.assertNotIn("private-client", body)

    def test_upload_can_append_to_a_configured_discussion(self) -> None:
        payload = build_manifest_feedback(
            self.manifest(feedback_enabled=True),
            event_type="build",
            operation_result={"ok": True},
        )
        environment = {
            "STARBRIDGE_FEEDBACK_TRANSPORT": "discussion_comment",
            "STARBRIDGE_FEEDBACK_REPOSITORY": "owner/repository",
            "STARBRIDGE_FEEDBACK_DISCUSSION_ID": "D_kwDOExample42",
        }
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("subprocess.run", return_value=completed) as run,
        ):
            result = submit_feedback_payload(payload)
        self.assertEqual("uploaded", result["status"])
        self.assertEqual("discussion_comment", result["transport"])
        command = run.call_args.args[0]
        self.assertEqual(["gh", "api", "graphql"], command[:3])
        self.assertIn("discussionId=D_kwDOExample42", command)
        self.assertTrue(any("addDiscussionComment" in item for item in command))


if __name__ == "__main__":
    unittest.main()
