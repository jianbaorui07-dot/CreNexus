"""Local-first image decomposition for editable Photoshop documents."""

from .github_feedback import FEEDBACK_SCHEMA_VERSION
from .intent import (
    GITHUB_FEEDBACK_CONSENT_VERSION,
    INTENT_SCHEMA_VERSION,
    client_questions,
    normalise_intent_profile,
    recommended_intent_profile,
)
from .pipeline import (
    DecompositionOptions,
    apply_review_patch,
    batch_decompose,
    decompose_image,
    plan_image,
)
from .public_dataset import (
    PUBLIC_DATASET_REQUEST_SCHEMA,
    PUBLIC_DATASET_SCHEMA,
    acquire_public_dataset,
)
from .public_experiment import PUBLIC_EXPERIMENT_SCHEMA, run_public_client_mode_experiment
from .regression import REGRESSION_SCHEMA_VERSION, run_synthetic_regression
from .training import (
    SUBJECT_MODEL_SCHEMA,
    TRAINING_REPORT_SCHEMA,
    score_subject_mask_features,
    train_subject_mask_quality_model,
)

__all__ = [
    "DecompositionOptions",
    "FEEDBACK_SCHEMA_VERSION",
    "GITHUB_FEEDBACK_CONSENT_VERSION",
    "INTENT_SCHEMA_VERSION",
    "PUBLIC_DATASET_REQUEST_SCHEMA",
    "PUBLIC_DATASET_SCHEMA",
    "PUBLIC_EXPERIMENT_SCHEMA",
    "REGRESSION_SCHEMA_VERSION",
    "SUBJECT_MODEL_SCHEMA",
    "TRAINING_REPORT_SCHEMA",
    "apply_review_patch",
    "acquire_public_dataset",
    "batch_decompose",
    "client_questions",
    "decompose_image",
    "normalise_intent_profile",
    "plan_image",
    "recommended_intent_profile",
    "run_synthetic_regression",
    "run_public_client_mode_experiment",
    "score_subject_mask_features",
    "train_subject_mask_quality_model",
]
