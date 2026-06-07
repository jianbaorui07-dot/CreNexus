from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starbridge_mcp.core.evidence import VALID_JOB_STATUSES, ensure_status
from starbridge_mcp.core.security import sanitize


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    bridge: str
    action: str
    status: str
    progress: int = 0
    message: str = ""
    evidence_manifest: dict[str, Any] = field(default_factory=dict)
    next_steps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        ensure_status(self.status)
        if not 0 <= self.progress <= 100:
            raise ValueError("progress must be between 0 and 100")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "job_id": self.job_id,
                "bridge": self.bridge,
                "action": self.action,
                "status": self.status,
                "progress": self.progress,
                "message": self.message,
                "evidence_manifest": self.evidence_manifest,
                "next_steps": self.next_steps,
            }
        )


def allowed_statuses() -> tuple[str, ...]:
    return VALID_JOB_STATUSES
