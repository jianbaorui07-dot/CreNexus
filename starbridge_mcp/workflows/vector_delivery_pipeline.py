from __future__ import annotations

from typing import Any

from starbridge_mcp.adapters.local import LocalDeliveryAdapter, UserReviewAdapter
from starbridge_mcp.adapters.vectorization import VectorizationAdapter
from starbridge_mcp.domain.models import WorkflowPlan, WorkflowStep, validate_relative_path
from starbridge_mcp.workflows.registry import WorkflowRegistry, build_workflow_plan

WORKFLOW_ID = "vector-delivery-v1"
DRAWING_MODES = frozenset({"exact", "artisan", "smart", "lightweight"})


def create_vector_delivery_plan(inputs: dict[str, Any]) -> WorkflowPlan:
    source_relative_path = validate_relative_path(str(inputs.get("sourceAssetRelativePath") or ""))
    drawing_mode = str(inputs.get("drawingMode") or "exact")
    if drawing_mode not in DRAWING_MODES:
        raise ValueError("drawingMode must be exact, artisan, smart, or lightweight")
    parameters = inputs.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")
    exact_parameters = parameters.get("exact") or {}
    drawing_parameters = parameters.get("drawing") or {}
    if not isinstance(exact_parameters, dict):
        raise ValueError("parameters.exact must be an object")
    if not isinstance(drawing_parameters, dict):
        raise ValueError("parameters.drawing must be an object")
    exact_max_dimension = exact_parameters.get("maxDimension")
    if exact_max_dimension is not None and (
        isinstance(exact_max_dimension, bool)
        or not isinstance(exact_max_dimension, int | float)
        or int(exact_max_dimension) != exact_max_dimension
        or (int(exact_max_dimension) != 0 and not 256 <= int(exact_max_dimension) <= 4096)
    ):
        raise ValueError("exact maxDimension must be 0 or between 256 and 4096")
    exact_max_svg_size = exact_parameters.get("maxSvgSizeMb")
    if exact_max_svg_size is not None and (
        isinstance(exact_max_svg_size, bool)
        or not isinstance(exact_max_svg_size, int | float)
        or not 1 <= float(exact_max_svg_size) <= 256
    ):
        raise ValueError("exact maxSvgSizeMb must be between 1 and 256")
    common = {"sourceAssetRelativePath": source_relative_path}
    steps = [
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
                "parameters": exact_parameters,
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
    ]
    if drawing_mode != "exact":
        steps.extend(
            (
                WorkflowStep(
                    step_id="draw-vector",
                    adapter="vectorization",
                    input_data={
                        **common,
                        "operation": "vectorize",
                        "mode": drawing_mode,
                        "parameters": drawing_parameters,
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
            )
        )
    steps.extend(
        (
            WorkflowStep(
                step_id="review-result",
                adapter="user-review",
                input_data={
                    "review": "pixel-reconstruction" if drawing_mode == "exact" else "vector-result"
                },
                requires_confirmation=True,
                rollback_policy={"enabled": False, "preserveArtifacts": True},
            ),
            WorkflowStep(
                step_id="collect-delivery",
                adapter="local-delivery",
                input_data={"formats": "from-existing-artifacts-only"},
                validation=("no-fabricated-format", "redacted-evidence"),
            ),
        )
    )
    return build_workflow_plan(WORKFLOW_ID, tuple(steps))


def register_vector_delivery_workflow(registry: WorkflowRegistry) -> None:
    registry.register_adapter(VectorizationAdapter())
    registry.register_adapter(UserReviewAdapter())
    registry.register_adapter(LocalDeliveryAdapter())
    registry.register_workflow(WORKFLOW_ID, create_vector_delivery_plan)
