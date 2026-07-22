from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.vectorization.vector60.report import (
    RenderMetrics,
    Vector60Report,
    write_report,
)


def metrics() -> RenderMetrics:
    return RenderMetrics(
        ssim=0.97,
        normalized_mae=0.03,
        edge_dice=0.94,
        anchors=120,
        subpaths=16,
        svg_bytes=4096,
        elapsed_seconds=0.25,
        reference_width=128,
        reference_height=96,
        rendered_width=128,
        rendered_height=96,
    )


class Vector60ReportTests(unittest.TestCase):
    def test_selected_report_requires_safe_original_resolution_evidence(self) -> None:
        report = Vector60Report(
            scene="logo",
            status="selected",
            candidate_count=4,
            selected_candidate="vtracer-logo-01",
            metrics=metrics(),
            safety_verified=True,
            final_render_scored=True,
        )

        payload = report.as_public_dict()

        self.assertTrue(payload["validation"]["original_resolution_render"])
        self.assertNotIn("input_path", payload)
        self.assertNotIn("output_path", payload)

    def test_report_rejects_candidate_overflow_and_unrendered_selection(self) -> None:
        with self.assertRaises(ValueError):
            Vector60Report(
                scene="flat",
                status="selected",
                candidate_count=13,
                selected_candidate="candidate-13",
                metrics=metrics(),
                safety_verified=True,
                final_render_scored=True,
            )
        with self.assertRaises(ValueError):
            Vector60Report(
                scene="flat",
                status="selected",
                candidate_count=1,
                selected_candidate="candidate-01",
                metrics=None,
                safety_verified=True,
                final_render_scored=False,
            )

        with self.assertRaises(ValueError):
            RenderMetrics(
                **{
                    **metrics().__dict__,
                    "rendered_width": 64,
                }
            )

    def test_report_rejects_private_path_or_secret_shaped_reason_text(self) -> None:
        for unsafe in ("C:/private/source.png", "token=secret", "customer material"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                Vector60Report(
                    scene="unsupported_photo",
                    status="unsupported_photo_fallback",
                    candidate_count=0,
                    fallback_reason=unsafe,
                    safety_verified=True,
                    final_render_scored=False,
                )

    def test_written_report_contains_no_output_path(self) -> None:
        report = Vector60Report(
            scene="unsupported_photo",
            status="unsupported_photo_fallback",
            candidate_count=0,
            fallback_reason="unsupported_photo",
            safety_verified=True,
            final_render_scored=False,
            warning_codes=("artisan_baseline_retained",),
        )
        with tempfile.TemporaryDirectory(prefix="private-account-material-") as temporary:
            output = Path(temporary) / "customer-token-cookie"
            json_path, markdown_path = write_report(output, report)
            combined = json_path.read_text(encoding="utf-8") + markdown_path.read_text(
                encoding="utf-8"
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertNotIn(str(output), combined)
        self.assertNotIn(output.name, combined)
        self.assertEqual(payload["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
