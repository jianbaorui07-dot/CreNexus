from __future__ import annotations

from typing import Any

from starbridge_mcp.adapters.local import LocalDeliveryAdapter, UserReviewAdapter
from starbridge_mcp.adapters.vectorization import VectorizationAdapter
from starbridge_mcp.domain.models import WorkflowPlan, WorkflowStep, validate_relative_path
from starbridge_mcp.workflows.registry import WorkflowRegistry, build_workflow_plan

WORKFLOW_ID = "vector-delivery-v1"
DRAWING_MODES = frozenset({"artisan", "smart", "lightweight"})


def create_vector_delivery_plan(inputs: dict[str, Any]) -> WorkflowPlan:
    source_relative_path = validate_relative_path(str(inputs.get("sourceAssetRelativePath") or ""))
    drawing_mode = str(inputs.get("drawingMode") or "artisan")
    if drawing_mode not in DRAWING_MODES:
        raise ValueError("drawingMode must be artisan, smart, or lightweight")
    parameters = inputs.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    common = {"sourceAssetRelativePath": source_relative_path}
    return build_workflow_plan(
        WORKFLOW_ID,
        (
            WorkflowStep(
                step_id="validate-source",
                adapter="vectorization",
                input_data={**common, "operation": "validate-source"},
                validation=("explicit-file", "png-or-jpeg", "managed-project-source"),
            ),
            WorkflowStep(
                step_id="exact-reconstruction",
                adapter="vectorization",
                input_data={
                    **common,
                    "operation": "vectorize",
                    "mode": "exact",
                    "parameters": parameters.get("exact") or {},
                },
                validation=("safe-output-root", "no-source-overwrite"),
                requires_confirmation=True,
                rollback_policy={"enabled": False, "preserveFailedOutputForDiagnostics": True},
            ),
            WorkflowStep(
                step_id="verify-exact-baseline",
                adapter="vectorization",
                input_data={**common, "operation": "verify-exact"},
                validation=(
                    "pixel-match",
                    "raster-free-svg",
                    "no-script",
                    "no-external-reference",
                    "image-trace-not-used",
                ),
            ),
            WorkflowStep(
                step_id="draw-vector",
                adapter="vectorization",
                input_data={
                    **common,
                    "operation": "vectorize",
                    "mode": drawing_mode,
                    "parameters": parameters.get("drawing") or {},
                },
                validation=("exact-baseline-completed", "safe-output-root"),
                requires_confirmation=True,
                retry_policy={"maxAttempts": 1},
                rollback_policy={"enabled": False, "preserveExactBaseline": True},
            ),
            WorkflowStep(
                step_id="compare-quality",
                adapter="vectorization",
                input_data={**common, "operation": "compare-quality", "mode": drawing_mode},
                validation=("final-svg-render", "quality-metrics"),
            ),
            WorkflowStep(
                step_id="review-result",
                adapter="user-review",
                input_data={"review": "vector-result"},
                requires_confirmation=True,
                rollback_policy={"enabled": False, "preserveArtifacts": True},
            ),
            WorkflowStep(
                step_id="collect-delivery",
                adapter="local-delivery",
                input_data={"formats": "from-existing-artifacts-only"},
                validation=("no-fabricated-format", "redacted-evidence"),
            ),
        ),
    )


def register_vector_delivery_workflow(registry: WorkflowRegistry) -> None:
    registry.register_adapter(VectorizationAdapter())
    registry.register_adapter(UserReviewAdapter())
    registry.register_adapter(LocalDeliveryAdapter())
    registry.register_workflow(WORKFLOW_ID, create_vector_delivery_plan)
