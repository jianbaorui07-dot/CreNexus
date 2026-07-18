from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from starbridge_mcp.domain.errors import DomainValidationError
from starbridge_mcp.domain.models import (
    TERMINAL_JOB_STATUSES,
    Artifact,
    CreativeJob,
    JobError,
    JobHistoryEvent,
    utc_now_iso,
)
from starbridge_mcp.storage.job_store import JobStore

ALLOWED_TRANSITIONS = {
    "queued": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"running", "needs_user", "completed", "failed", "cancelled"}),
    "needs_user": frozenset({"needs_user", "running", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


class JobStateMachine:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def transition(
        self,
        job: CreativeJob,
        target: str,
        *,
        current_step: str,
        progress: int,
        message: str,
        artifacts: tuple[Artifact, ...] | None = None,
        warnings: tuple[str, ...] | None = None,
        error: JobError | None = None,
        evidence_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> CreativeJob:
        if target not in ALLOWED_TRANSITIONS.get(job.status, frozenset()):
            raise DomainValidationError(f"invalid job transition: {job.status} -> {target}")
        if progress < job.progress:
            raise DomainValidationError("job progress must not move backwards")
        if target == "completed":
            progress = 100
        completed_at = utc_now_iso() if target in TERMINAL_JOB_STATUSES else None
        transitioned = replace(
            job,
            status=target,
            current_step=current_step,
            progress=progress,
            updated_at=utc_now_iso(),
            completed_at=completed_at,
            artifacts=artifacts if artifacts is not None else job.artifacts,
            warnings=warnings if warnings is not None else job.warnings,
            error=error,
            evidence_id=evidence_id if evidence_id is not None else job.evidence_id,
        )
        self.store.save(transitioned)
        self.store.append_event(
            JobHistoryEvent(
                event_id=f"event-{uuid4().hex[:16]}",
                job_id=job.job_id,
                status=target,
                step_id=current_step,
                message=message,
                details=dict(details or {}),
            )
        )
        return transitioned
