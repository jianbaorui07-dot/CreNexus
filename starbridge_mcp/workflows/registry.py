from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from starbridge_mcp.adapters.base import CreativeAdapter
from starbridge_mcp.domain.models import WorkflowPlan, WorkflowStep, validate_id

WorkflowPlanFactory = Callable[[dict[str, Any]], WorkflowPlan]


def build_workflow_plan(
    workflow_id: str,
    steps: Iterable[WorkflowStep],
    *,
    revision: int = 1,
) -> WorkflowPlan:
    validate_id(workflow_id, "workflowId")
    step_tuple = tuple(steps)
    canonical = json.dumps(
        {
            "workflowId": workflow_id,
            "revision": revision,
            "steps": [step.to_dict() for step in step_tuple],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    plan_hash = hashlib.sha256(canonical).hexdigest()
    return WorkflowPlan(
        plan_id=f"plan-{plan_hash[:16]}",
        workflow_id=workflow_id,
        revision=revision,
        steps=step_tuple,
        plan_hash=plan_hash,
    )


class WorkflowRegistry:
    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowPlanFactory] = {}
        self._adapters: dict[str, CreativeAdapter] = {}

    def register_workflow(self, workflow_id: str, factory: WorkflowPlanFactory) -> None:
        validate_id(workflow_id, "workflowId")
        if workflow_id in self._workflows:
            raise ValueError(f"workflow is already registered: {workflow_id}")
        self._workflows[workflow_id] = factory

    def register_adapter(self, adapter: CreativeAdapter) -> None:
        validate_id(adapter.adapter_id, "adapterId")
        if adapter.adapter_id in self._adapters:
            raise ValueError(f"adapter is already registered: {adapter.adapter_id}")
        self._adapters[adapter.adapter_id] = adapter

    def create_plan(self, workflow_id: str, inputs: dict[str, Any]) -> WorkflowPlan:
        try:
            factory = self._workflows[workflow_id]
        except KeyError as exc:
            raise KeyError(f"workflow is not registered: {workflow_id}") from exc
        plan = factory(inputs)
        if plan.workflow_id != workflow_id:
            raise ValueError("workflow factory returned a plan for another workflow")
        return plan

    def adapter(self, adapter_id: str) -> CreativeAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise KeyError(f"adapter is not registered: {adapter_id}") from exc

    def workflow_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._workflows))

    def adapter_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))
