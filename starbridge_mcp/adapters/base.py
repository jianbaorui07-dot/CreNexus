from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from starbridge_mcp.core.app_data import AppDataPaths
from starbridge_mcp.domain.models import Artifact, JobError, WorkflowStep


@dataclass(frozen=True)
class ProbeResult:
    available: bool
    connection_state: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    warnings: tuple[str, ...] = ()
    error: JobError | None = None


@dataclass(frozen=True)
class AdapterResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[Artifact, ...] = ()
    warnings: tuple[str, ...] = ()
    error: JobError | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"completed", "needs_user", "failed", "cancelled"}:
            raise ValueError("adapter result status is invalid")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed adapter results require a structured error")


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class AdapterContext:
    job_id: str
    project_id: str
    workflow_id: str
    step: WorkflowStep
    app_paths: AppDataPaths
    cancellation: CancellationToken


class CreativeAdapter(ABC):
    adapter_id: str

    @abstractmethod
    def probe(self, context: AdapterContext) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    def plan(self, context: AdapterContext) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate(self, context: AdapterContext) -> ValidationReport:
        raise NotImplementedError

    @abstractmethod
    def execute(self, context: AdapterContext) -> AdapterResult:
        raise NotImplementedError

    def cancel(self, context: AdapterContext) -> None:
        context.cancellation.cancel()

    def collect_artifacts(
        self, context: AdapterContext, result: AdapterResult
    ) -> tuple[Artifact, ...]:
        return result.artifacts

    def collect_evidence(self, context: AdapterContext, result: AdapterResult) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "stepId": context.step.step_id,
            "status": result.status,
            "warnings": list(result.warnings),
            "artifactIds": [artifact.artifact_id for artifact in result.artifacts],
        }

    def rollback(self, context: AdapterContext, result: AdapterResult) -> bool:
        return True
