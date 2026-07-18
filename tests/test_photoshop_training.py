from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.adapters.photoshop.semantic_layers.training import (
    SUBJECT_MODEL_SCHEMA,
    TRAINING_REPORT_SCHEMA,
    score_subject_mask_features,
    train_subject_mask_quality_model,
)


class PhotoshopTrainingTests(unittest.TestCase):
    def test_training_protocol_schemas_are_public_valid_json(self) -> None:
        protocol_root = (
            Path(__file__).resolve().parents[1] / "examples" / "photoshop_bridge" / "protocols"
        )
        expected = {
            "subject_mask_training_report.v1.schema.json": TRAINING_REPORT_SCHEMA,
            "subject_mask_quality_model.v1.schema.json": SUBJECT_MODEL_SCHEMA,
        }
        for filename, schema_version in expected.items():
            with self.subTest(filename=filename):
                schema = json.loads((protocol_root / filename).read_text(encoding="utf-8"))
                self.assertEqual("object", schema["type"])
                self.assertEqual(schema_version, schema["properties"]["schema_version"]["const"])

    def example(self, group: int, index: int, *, accepted: bool) -> dict[str, object]:
        if accepted:
            features = {
                "engine": "offline_iterative_grabcut",
                "candidate_score": 0.88 + index * 0.002,
                "coverage": 0.30 + index * 0.001,
                "center_overlap": 0.82,
                "border_touch": 0.01,
                "edge_alignment": 0.86,
                "recomposition_similarity": 0.99,
            }
        else:
            features = {
                "engine": "offline_iterative_grabcut",
                "candidate_score": 0.45 - index * 0.002,
                "coverage": 0.72 - index * 0.001,
                "center_overlap": 0.52,
                "border_touch": 0.18,
                "edge_alignment": 0.31,
                "recomposition_similarity": 0.995,
            }
        return {
            "example_id": f"example-{group}-{index}-{int(accepted)}",
            "schema_version": "starbridge.layer_decision_example.v1",
            "pipeline_version": "pipeline-test",
            "source_fingerprint": f"{group:012x}",
            "intent_profile_sha256": "a" * 64,
            "includes_pixels": False,
            "decision_type": "subject_mask_review",
            "features": features,
            "decision": {
                "accepted": accepted,
                "quality_score": 0.9 if accepted else 0.3,
                "failure_modes": [] if accepted else ["over_selection"],
                "confidence": 0.98,
            },
        }

    def write_examples(self, path: Path, group_count: int) -> None:
        examples = []
        for group in range(group_count):
            examples.append(self.example(group, group, accepted=True))
            examples.append(self.example(group, group, accepted=False))
        path.write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in examples) + "\n",
            encoding="utf-8",
        )

    def test_small_realistic_dataset_produces_insufficient_data_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "four-examples.jsonl"
            self.write_examples(dataset, 2)
            output = root / "training-report.json"
            result = train_subject_mask_quality_model([dataset], output)
            self.assertEqual(TRAINING_REPORT_SCHEMA, result["schema_version"])
            self.assertEqual("insufficient_data", result["status"])
            self.assertFalse(result["model_written"])
            self.assertFalse(result["automatic_application_allowed"])
            self.assertTrue(result["requirements"]["missing"])
            self.assertNotIn(str(root), output.read_text(encoding="utf-8"))

    def test_grouped_training_builds_candidate_only_model_and_never_auto_applies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "synthetic-mechanics.jsonl"
            self.write_examples(dataset, 12)
            output = root / "model.json"
            model = train_subject_mask_quality_model([dataset], output)
            self.assertEqual(SUBJECT_MODEL_SCHEMA, model["schema_version"])
            self.assertEqual("candidate_only", model["status"])
            self.assertTrue(model["model_written"])
            self.assertFalse(model["automatic_application_allowed"])
            self.assertGreaterEqual(model["validation_metrics"]["accuracy"], 0.9)
            positive = score_subject_mask_features(
                model,
                self.example(99, 0, accepted=True)["features"],
            )
            negative = score_subject_mask_features(
                model,
                self.example(99, 0, accepted=False)["features"],
            )
            self.assertGreater(
                positive["acceptance_probability"], negative["acceptance_probability"]
            )
            self.assertFalse(positive["automatic_patch_applied"])
            self.assertTrue(positive["human_review_required"])

    def test_pixel_bearing_example_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "unsafe.jsonl"
            unsafe = self.example(1, 1, accepted=True)
            unsafe["includes_pixels"] = True
            dataset.write_text(json.dumps(unsafe) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not include pixels"):
                train_subject_mask_quality_model([dataset], root / "model.json")


if __name__ == "__main__":
    unittest.main()
