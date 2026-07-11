from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from starbridge_mcp.core.evidence import utc_now_iso
from starbridge_mcp.core.security import sanitize

RISK_LEVELS = ("L0", "L1", "L2", "L3", "L4")
TRANSACTION_STATUSES = (
    "draft",
    "planned",
    "validated",
    "awaiting_approval",
    "approved",
    "running",
    "verifying",
    "repair_needed",
    "completed",
    "failed",
    "aborted",
)

ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("planned", "aborted"),
    "planned": ("validated", "failed", "aborted"),
    "validated": ("awaiting_approval", "approved", "failed", "aborted"),
    "awaiting_approval": ("approved", "aborted"),
    "approved": ("running", "aborted"),
    "running": ("verifying", "failed", "aborted"),
    "verifying": ("completed", "repair_needed", "failed", "aborted"),
    "repair_needed": ("planned", "aborted"),
    "completed": (),
    "failed": (),
    "aborted": (),
}


def ensure_risk_level(value: str) -> str:
    if value not in RISK_LEVELS:
        raise ValueError(f"risk_level must be one of {', '.join(RISK_LEVELS)}")
    return value


def ensure_transaction_status(value: str) -> str:
    if value not in TRANSACTION_STATUSES:
        raise ValueError(f"status must be one of {', '.join(TRANSACTION_STATUSES)}")
    return value


@dataclass(frozen=True)
class ModelPolicy:
    planner: str = "frontier"
    executor: str = "balanced"
    observer: str = "fast"
    visual_reviewer: str = "frontier"

    def to_dict(self) -> dict[str, str]:
        return {
            "planner": self.planner,
            "executor": self.executor,
            "observer": self.observer,
            "visual_reviewer": self.visual_reviewer,
        }


@dataclass
class CreativeTransaction:
    intent: str
    bridge: str
    risk_level: str = "L2"
    dry_run: bool = True
    status: str = "draft"
    transaction_id: str = field(default_factory=lambda: f"txn_{uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    recipe_id: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    rollback_plan: dict[str, Any] = field(default_factory=dict)
    model_policy: ModelPolicy = field(default_factory=ModelPolicy)

    def __post_init__(self) -> None:
        self.risk_level = ensure_risk_level(self.risk_level)
        self.status = ensure_transaction_status(self.status)
        if not self.intent.strip():
            raise ValueError("intent must not be empty")
        if self.risk_level in {"L2", "L3", "L4"} and not self.required_approvals:
            self.required_approvals.append("user_confirmation_before_write")

    def transition_to(self, next_status: str) -> None:
        next_status = ensure_transaction_status(next_status)
        if next_status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid transaction transition: {self.status} -> {next_status}")
        self.status = next_status
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "transaction_id": self.transaction_id,
                "intent": self.intent,
                "bridge": self.bridge,
                "recipe_id": self.recipe_id,
                "risk_level": self.risk_level,
                "dry_run": self.dry_run,
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "steps": self.steps,
                "quality_gates": self.quality_gates,
                "required_approvals": self.required_approvals,
                "expected_outputs": self.expected_outputs,
                "rollback_plan": self.rollback_plan,
                "model_policy": self.model_policy.to_dict(),
                "allowed_next_statuses": list(ALLOWED_TRANSITIONS[self.status]),
            }
        )


def create_recipe_transaction(
    *,
    recipe_id: str,
    bridge: str,
    intent: str,
    steps: list[dict[str, Any]],
    quality_gates: list[str],
    expected_outputs: list[str],
    dry_run: bool = True,
) -> CreativeTransaction:
    transaction = CreativeTransaction(
        intent=intent,
        bridge=bridge,
        recipe_id=recipe_id,
        risk_level="L2" if dry_run else "L3",
        dry_run=dry_run,
        steps=steps,
        quality_gates=quality_gates,
        expected_outputs=expected_outputs,
        rollback_plan={
            "strategy": "discard_sandbox_outputs",
            "destructive_actions_allowed": False,
        },
    )
    transaction.transition_to("planned")
    return transaction
