from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

SUBJECT_MODEL_SCHEMA = "starbridge.subject_mask_quality_model.v1"
TRAINING_REPORT_SCHEMA = "starbridge.subject_mask_training_report.v1"
FEATURE_NAMES = (
    "candidate_score",
    "coverage",
    "center_overlap",
    "border_touch",
    "edge_alignment",
    "recomposition_similarity",
)
MINIMUM_EXAMPLES = 20
MINIMUM_SOURCE_GROUPS = 8
MINIMUM_CLASS_EXAMPLES = 5


def _load_subject_examples(dataset_paths: list[str | Path]) -> list[dict[str, Any]]:
    if not 1 <= len(dataset_paths) <= 128:
        raise ValueError("Training requires 1 to 128 explicit dataset files")
    examples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dataset_path in dataset_paths:
        path = Path(dataset_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError("An explicit training dataset file is missing")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("schema_version") != "starbridge.layer_decision_example.v1":
                raise ValueError("Unsupported decision example schema_version")
            if item.get("includes_pixels") is not False:
                raise ValueError("Training examples must not include pixels")
            if item.get("decision_type") != "subject_mask_review":
                continue
            example_id = str(item.get("example_id") or "")
            if not example_id or example_id in seen:
                continue
            source_group = str(item.get("source_fingerprint") or "")
            if not re_fullmatch_hex(source_group, 12):
                raise ValueError("Training example source_fingerprint is invalid")
            features = item.get("features")
            decision = item.get("decision")
            if not isinstance(features, dict) or not isinstance(decision, dict):
                raise ValueError("Training example features and decision must be objects")
            vector = []
            for feature_name in FEATURE_NAMES:
                value = float(features.get(feature_name, 0.0))
                if not math.isfinite(value):
                    raise ValueError("Training feature must be finite")
                vector.append(value)
            if not isinstance(decision.get("accepted"), bool):
                raise ValueError("Training decision accepted must be boolean")
            examples.append(
                {
                    "example_id": example_id,
                    "source_group": source_group,
                    "vector": vector,
                    "label": 1 if decision["accepted"] else 0,
                }
            )
            seen.add(example_id)
    return examples


def re_fullmatch_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


def _requirements(examples: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [int(item["label"]) for item in examples]
    groups = {str(item["source_group"]) for item in examples}
    positives = sum(labels)
    negatives = len(labels) - positives
    missing: list[str] = []
    if len(examples) < MINIMUM_EXAMPLES:
        missing.append(f"{MINIMUM_EXAMPLES - len(examples)} more examples")
    if len(groups) < MINIMUM_SOURCE_GROUPS:
        missing.append(f"{MINIMUM_SOURCE_GROUPS - len(groups)} more independent source groups")
    if positives < MINIMUM_CLASS_EXAMPLES:
        missing.append(f"{MINIMUM_CLASS_EXAMPLES - positives} more accepted examples")
    if negatives < MINIMUM_CLASS_EXAMPLES:
        missing.append(f"{MINIMUM_CLASS_EXAMPLES - negatives} more rejected examples")
    return {
        "example_count": len(examples),
        "source_group_count": len(groups),
        "accepted_count": positives,
        "rejected_count": negatives,
        "minimum_examples": MINIMUM_EXAMPLES,
        "minimum_source_groups": MINIMUM_SOURCE_GROUPS,
        "minimum_per_class": MINIMUM_CLASS_EXAMPLES,
        "missing": missing,
        "satisfied": not missing,
    }


def _validation_groups(groups: list[str]) -> set[str]:
    ranked = sorted(
        groups,
        key=lambda value: hashlib.sha256(("validation:" + value).encode("utf-8")).hexdigest(),
    )
    count = max(2, int(round(len(ranked) * 0.2)))
    return set(ranked[:count])


def _sigmoid(values: Any) -> Any:
    import numpy as np

    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _metrics(labels: Any, probabilities: Any) -> dict[str, float]:
    import numpy as np

    predictions = probabilities >= 0.5
    labels_bool = labels >= 0.5
    true_positive = int(np.count_nonzero(predictions & labels_bool))
    false_positive = int(np.count_nonzero(predictions & ~labels_bool))
    false_negative = int(np.count_nonzero(~predictions & labels_bool))
    accuracy = float(np.mean(predictions == labels_bool))
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    epsilon = 1e-7
    log_loss = -float(
        np.mean(
            labels * np.log(np.clip(probabilities, epsilon, 1.0 - epsilon))
            + (1.0 - labels) * np.log(np.clip(1.0 - probabilities, epsilon, 1.0 - epsilon))
        )
    )
    return {
        "accuracy": round(accuracy, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "log_loss": round(log_loss, 6),
    }


def train_subject_mask_quality_model(
    dataset_paths: list[str | Path],
    output_report_path: str | Path,
) -> dict[str, Any]:
    import numpy as np

    examples = _load_subject_examples(dataset_paths)
    requirements = _requirements(examples)
    report_path = Path(output_report_path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_digest = hashlib.sha256(
        "\n".join(sorted(str(item["example_id"]) for item in examples)).encode("utf-8")
    ).hexdigest()
    if not requirements["satisfied"]:
        report = {
            "schema_version": TRAINING_REPORT_SCHEMA,
            "status": "insufficient_data",
            "model_written": False,
            "requirements": requirements,
            "dataset_digest": dataset_digest,
            "private_paths_recorded": False,
            "automatic_application_allowed": False,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**report, "report_path": str(report_path)}

    validation_groups = _validation_groups(sorted({str(item["source_group"]) for item in examples}))
    train_items = [item for item in examples if item["source_group"] not in validation_groups]
    validation_items = [item for item in examples if item["source_group"] in validation_groups]
    train_labels = {int(item["label"]) for item in train_items}
    validation_labels = {int(item["label"]) for item in validation_items}
    if train_labels != {0, 1} or validation_labels != {0, 1}:
        report = {
            "schema_version": TRAINING_REPORT_SCHEMA,
            "status": "insufficient_grouped_validation",
            "model_written": False,
            "requirements": requirements,
            "dataset_digest": dataset_digest,
            "private_paths_recorded": False,
            "automatic_application_allowed": False,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**report, "report_path": str(report_path)}

    train_x = np.asarray([item["vector"] for item in train_items], dtype=np.float64)
    train_y = np.asarray([item["label"] for item in train_items], dtype=np.float64)
    validation_x = np.asarray([item["vector"] for item in validation_items], dtype=np.float64)
    validation_y = np.asarray([item["label"] for item in validation_items], dtype=np.float64)
    means = np.mean(train_x, axis=0)
    scales = np.std(train_x, axis=0)
    scales[scales < 1e-8] = 1.0
    train_scaled = (train_x - means) / scales
    validation_scaled = (validation_x - means) / scales
    weights = np.zeros(train_scaled.shape[1], dtype=np.float64)
    bias = 0.0
    learning_rate = 0.08
    regularization = 0.01
    for _ in range(1200):
        probabilities = _sigmoid(train_scaled @ weights + bias)
        error = probabilities - train_y
        weights -= learning_rate * (
            (train_scaled.T @ error) / len(train_y) + regularization * weights
        )
        bias -= learning_rate * float(np.mean(error))

    train_probabilities = _sigmoid(train_scaled @ weights + bias)
    validation_probabilities = _sigmoid(validation_scaled @ weights + bias)
    model = {
        "schema_version": SUBJECT_MODEL_SCHEMA,
        "status": "candidate_only",
        "feature_names": list(FEATURE_NAMES),
        "means": [round(float(value), 10) for value in means],
        "scales": [round(float(value), 10) for value in scales],
        "weights": [round(float(value), 10) for value in weights],
        "bias": round(float(bias), 10),
        "threshold": 0.5,
        "training_examples": len(train_items),
        "validation_examples": len(validation_items),
        "training_source_groups": len({str(item["source_group"]) for item in train_items}),
        "validation_source_groups": len(validation_groups),
        "training_metrics": _metrics(train_y, train_probabilities),
        "validation_metrics": _metrics(validation_y, validation_probabilities),
        "dataset_digest": dataset_digest,
        "private_paths_recorded": False,
        "automatic_application_allowed": False,
    }
    report_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**model, "model_written": True, "report_path": str(report_path)}


def score_subject_mask_features(model: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    if model.get("schema_version") != SUBJECT_MODEL_SCHEMA:
        raise ValueError("Unsupported subject mask quality model schema_version")
    if model.get("automatic_application_allowed") is not False:
        raise ValueError("Subject mask model violated the human-review safety contract")
    vector = np.asarray([float(features.get(name, 0.0)) for name in FEATURE_NAMES])
    means = np.asarray(model["means"], dtype=np.float64)
    scales = np.asarray(model["scales"], dtype=np.float64)
    weights = np.asarray(model["weights"], dtype=np.float64)
    probability = float(_sigmoid(((vector - means) / scales) @ weights + float(model["bias"])))
    return {
        "acceptance_probability": round(probability, 6),
        "recommendation": "review_likely_acceptable"
        if probability >= float(model.get("threshold", 0.5))
        else "review_likely_reject",
        "automatic_patch_applied": False,
        "human_review_required": True,
    }
