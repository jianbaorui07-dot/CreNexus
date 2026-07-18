from __future__ import annotations

from typing import Any

from starbridge_mcp.adapters.comfyui import ComfyUiAdapter, RuntimeInputVault
from starbridge_mcp.adapters.local import LocalDeliveryAdapter, UserReviewAdapter
from starbridge_mcp.domain.models import WorkflowPlan, WorkflowStep, validate_basename
from starbridge_mcp.workflows.registry import WorkflowRegistry, build_workflow_plan

WORKFLOW_ID = "comfyui-generation-v1"
SAMPLERS = frozenset({"euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde"})
SCHEDULERS = frozenset({"normal", "karras", "exponential", "sgm_uniform"})


def _bounded_int(value: Any, default: int, minimum: int, maximum: int, name: str) -> int:
    result = default if value is None else int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def _prepare_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    prompt = str(inputs.get("prompt") or "").strip()
    negative_prompt = str(inputs.get("negativePrompt") or "").strip()
    checkpoint = str(inputs.get("checkpointName") or "")
    validate_basename(checkpoint, "checkpointName")
    if not prompt or len(prompt) > 4000 or len(negative_prompt) > 4000:
        raise ValueError("prompt is required and prompt fields must not exceed 4000 characters")
    width = _bounded_int(inputs.get("width"), 512, 64, 2048, "width")
    height = _bounded_int(inputs.get("height"), 512, 64, 2048, "height")
    if width % 8 or height % 8:
        raise ValueError("width and height must be multiples of 8")
    sampler = str(inputs.get("sampler") or "dpmpp_2m")
    scheduler = str(inputs.get("scheduler") or "karras")
    if sampler not in SAMPLERS or scheduler not in SCHEDULERS:
        raise ValueError("sampler or scheduler is not in the safe allowlist")
    cfg = float(inputs.get("cfg") if inputs.get("cfg") is not None else 7.0)
    if not 1.0 <= cfg <= 30.0:
        raise ValueError("cfg must be between 1 and 30")
    seed = inputs.get("seed")
    if seed is not None and not 0 <= int(seed) <= 2**63 - 1:
        raise ValueError("seed is outside the safe range")
    return {
        "prompt": prompt,
        "negativePrompt": negative_prompt,
        "checkpointName": checkpoint,
        "width": width,
        "height": height,
        "seed": int(seed) if seed is not None else None,
        "steps": _bounded_int(inputs.get("steps"), 24, 1, 100, "steps"),
        "cfg": cfg,
        "sampler": sampler,
        "scheduler": scheduler,
        "timeout": _bounded_int(inputs.get("timeout"), 8, 1, 30, "timeout"),
        "waitSeconds": _bounded_int(inputs.get("waitSeconds"), 0, 0, 5, "waitSeconds"),
        "comfyUrl": inputs.get("comfyUrl"),
    }


def create_comfyui_generation_factory(vault: RuntimeInputVault):
    def create_plan(inputs: dict[str, Any]) -> WorkflowPlan:
        prepared = _prepare_inputs(inputs)
        runtime_ref = vault.put(prepared)
        common = {"runtimeInputRef": runtime_ref}
        public_parameters = {
            "width": prepared["width"],
            "height": prepared["height"],
            "steps": prepared["steps"],
            "cfg": prepared["cfg"],
            "sampler": prepared["sampler"],
            "scheduler": prepared["scheduler"],
            "seedProvided": prepared["seed"] is not None,
            "promptPersisted": False,
            "modelNamePersisted": False,
        }
        return build_workflow_plan(
            WORKFLOW_ID,
            (
                WorkflowStep(
                    step_id="validate-workflow",
                    adapter="comfyui",
                    input_data={
                        **common,
                        "operation": "validate-workflow",
                        "parameters": public_parameters,
                    },
                    validation=("api-workflow-format", "safe-node-graph", "no-persistent-prompt"),
                ),
                WorkflowStep(
                    step_id="probe-comfyui",
                    adapter="comfyui",
                    input_data={**common, "operation": "probe-service"},
                    validation=("loopback-only", "read-only-probe", "basic-nodes"),
                ),
                WorkflowStep(
                    step_id="submit-generation",
                    adapter="comfyui",
                    input_data={
                        **common,
                        "operation": "submit-generation",
                        "parameters": public_parameters,
                    },
                    validation=("validated-workflow", "loopback-only", "single-submit"),
                    requires_confirmation=True,
                    retry_policy={"maxAttempts": 1},
                    rollback_policy={"enabled": False, "doNotResubmitAutomatically": True},
                ),
                WorkflowStep(
                    step_id="collect-results",
                    adapter="comfyui",
                    input_data={"operation": "collect-results"},
                    validation=(
                        "same-prompt-id",
                        "terminal-success",
                        "basename-only",
                        "content-hash",
                    ),
                    retry_policy={"maxAttempts": 1},
                ),
                WorkflowStep(
                    step_id="review-result",
                    adapter="user-review",
                    input_data={"review": "generated-images"},
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

    return create_plan


def register_comfyui_generation_workflow(
    registry: WorkflowRegistry,
    *,
    adapter: ComfyUiAdapter | None = None,
    vault: RuntimeInputVault | None = None,
) -> RuntimeInputVault:
    runtime_vault = vault or RuntimeInputVault()
    comfy_adapter = adapter or ComfyUiAdapter(runtime_vault)
    if comfy_adapter.adapter_id not in registry.adapter_ids():
        registry.register_adapter(comfy_adapter)
    if "user-review" not in registry.adapter_ids():
        registry.register_adapter(UserReviewAdapter())
    if "local-delivery" not in registry.adapter_ids():
        registry.register_adapter(LocalDeliveryAdapter())
    registry.register_workflow(WORKFLOW_ID, create_comfyui_generation_factory(runtime_vault))
    return runtime_vault
