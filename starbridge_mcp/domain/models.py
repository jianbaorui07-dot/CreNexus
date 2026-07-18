from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, ClassVar

from starbridge_mcp.core.evidence import VALID_JOB_STATUSES
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.domain.errors import DomainValidationError

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise DomainValidationError(f"{field_name} must be a safe identifier")
    return value


def validate_basename(value: str, field_name: str = "basename") -> str:
    if not value or value in {".", ".."} or PurePosixPath(value).name != value:
        raise DomainValidationError(f"{field_name} must not contain a path")
    if "\\" in value or "/" in value:
        raise DomainValidationError(f"{field_name} must not contain a path")
    return value


def validate_relative_path(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        not value
        or candidate.is_absolute()
        or re.match(r"^[A-Za-z]:[/\\]", value)
        or value.startswith(("//", "\\\\"))
        or ".." in candidate.parts
        or "\\" in value
    ):
        raise DomainValidationError("relativePath must stay inside application data")
    return candidate.as_posix()


def validate_sha256(value: str) -> str:
    normalized = value.lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise DomainValidationError("sha256 must contain 64 hexadecimal characters")
    return normalized


@dataclass(frozen=True)
class SourceAsset:
    asset_id: str
    basename: str
    relative_path: str
    sha256: str
    media_type: str
    size_bytes: int
    imported_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        validate_id(self.asset_id, "assetId")
        validate_basename(self.basename)
        validate_relative_path(self.relative_path)
        validate_sha256(self.sha256)
        if self.size_bytes < 0:
            raise DomainValidationError("sizeBytes must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "assetId": self.asset_id,
            "basename": self.basename,
            "relativePath": self.relative_path,
            "sha256": self.sha256,
            "mediaType": self.media_type,
            "sizeBytes": self.size_bytes,
            "importedAt": self.imported_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceAsset:
        return cls(
            asset_id=str(payload["assetId"]),
            basename=str(payload["basename"]),
            relative_path=str(payload["relativePath"]),
            sha256=str(payload["sha256"]),
            media_type=str(payload.get("mediaType") or "application/octet-stream"),
            size_bytes=int(payload["sizeBytes"]),
            imported_at=str(payload.get("importedAt") or utc_now_iso()),
        )


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    kind: str
    basename: str
    relative_path: str
    sha256: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_id(self.artifact_id, "artifactId")
        validate_id(self.kind, "kind")
        validate_basename(self.basename)
        validate_relative_path(self.relative_path)
        validate_sha256(self.sha256)
        if self.size_bytes < 0:
            raise DomainValidationError("sizeBytes must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "artifactId": self.artifact_id,
                "kind": self.kind,
                "basename": self.basename,
                "relativePath": self.relative_path,
                "sha256": self.sha256,
                "mediaType": self.media_type,
                "sizeBytes": self.size_bytes,
                "createdAt": self.created_at,
                "metadata": self.metadata,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Artifact:
        return cls(
            artifact_id=str(payload["artifactId"]),
            kind=str(payload["kind"]),
            basename=str(payload["basename"]),
            relative_path=str(payload["relativePath"]),
            sha256=str(payload["sha256"]),
            media_type=str(payload.get("mediaType") or "application/octet-stream"),
            size_bytes=int(payload.get("sizeBytes") or 0),
            created_at=str(payload.get("createdAt") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class QualityMetric:
    name: str
    value: int | float | str | bool | None
    unit: str | None = None
    target: int | float | str | bool | None = None
    passed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "name": self.name,
                "value": self.value,
                "unit": self.unit,
                "target": self.target,
                "passed": self.passed,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> QualityMetric:
        return cls(
            name=str(payload["name"]),
            value=payload.get("value"),
            unit=str(payload["unit"]) if payload.get("unit") is not None else None,
            target=payload.get("target"),
            passed=payload.get("passed") if isinstance(payload.get("passed"), bool) else None,
        )


@dataclass(frozen=True)
class JobError:
    code: str
    message: str
    retryable: bool = False
    next_steps: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_id(self.code, "error.code")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "nextSteps": list(self.next_steps),
                "details": self.details,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> JobError:
        return cls(
            code=str(payload["code"]),
            message=str(payload["message"]),
            retryable=bool(payload.get("retryable", False)),
            next_steps=tuple(str(item) for item in payload.get("nextSteps") or ()),
            details=dict(payload.get("details") or {}),
        )


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    adapter: str
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    validation: tuple[str, ...] = ()
    requires_confirmation: bool = False
    optional: bool = False
    retry_policy: dict[str, Any] = field(default_factory=dict)
    rollback_policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_id(self.step_id, "stepId")
        validate_id(self.adapter, "adapter")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "stepId": self.step_id,
                "adapter": self.adapter,
                "input": self.input_data,
                "output": self.output_data,
                "validation": list(self.validation),
                "requiresConfirmation": self.requires_confirmation,
                "optional": self.optional,
                "retryPolicy": self.retry_policy,
                "rollbackPolicy": self.rollback_policy,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowStep:
        return cls(
            step_id=str(payload["stepId"]),
            adapter=str(payload["adapter"]),
            input_data=dict(payload.get("input") or {}),
            output_data=dict(payload.get("output") or {}),
            validation=tuple(str(item) for item in payload.get("validation") or ()),
            requires_confirmation=bool(payload.get("requiresConfirmation", False)),
            optional=bool(payload.get("optional", False)),
            retry_policy=dict(payload.get("retryPolicy") or {}),
            rollback_policy=dict(payload.get("rollbackPolicy") or {}),
        )


@dataclass(frozen=True)
class WorkflowPlan:
    plan_id: str
    workflow_id: str
    revision: int
    steps: tuple[WorkflowStep, ...]
    plan_hash: str
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        validate_id(self.plan_id, "planId")
        validate_id(self.workflow_id, "workflowId")
        validate_sha256(self.plan_hash)
        if self.revision < 1:
            raise DomainValidationError("revision must be positive")
        if not self.steps:
            raise DomainValidationError("a workflow plan must contain at least one step")

    def to_dict(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "workflowId": self.workflow_id,
            "revision": self.revision,
            "steps": [step.to_dict() for step in self.steps],
            "planHash": self.plan_hash,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowPlan:
        return cls(
            plan_id=str(payload["planId"]),
            workflow_id=str(payload["workflowId"]),
            revision=int(payload["revision"]),
            steps=tuple(WorkflowStep.from_dict(item) for item in payload["steps"]),
            plan_hash=str(payload["planHash"]),
            created_at=str(payload.get("createdAt") or utc_now_iso()),
        )


@dataclass(frozen=True)
class CreativeJob:
    schema_version: ClassVar[int] = 1

    job_id: str
    project_id: str
    workflow_id: str
    status: str = "queued"
    current_step: str = "queued"
    progress: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    artifacts: tuple[Artifact, ...] = ()
    warnings: tuple[str, ...] = ()
    error: JobError | None = None
    evidence_id: str | None = None

    def __post_init__(self) -> None:
        validate_id(self.job_id, "jobId")
        validate_id(self.project_id, "projectId")
        validate_id(self.workflow_id, "workflowId")
        if self.status not in VALID_JOB_STATUSES:
            raise DomainValidationError("status must be a canonical CreativeJob state")
        if not 0 <= self.progress <= 100:
            raise DomainValidationError("progress must be between 0 and 100")
        if self.evidence_id is not None:
            validate_id(self.evidence_id, "evidenceId")
        if self.status in TERMINAL_JOB_STATUSES and not self.completed_at:
            raise DomainValidationError("terminal jobs require completedAt")
        if self.status == "failed" and self.error is None:
            raise DomainValidationError("failed jobs require a structured error")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "schemaVersion": self.schema_version,
                "jobId": self.job_id,
                "projectId": self.project_id,
                "workflowId": self.workflow_id,
                "status": self.status,
                "currentStep": self.current_step,
                "progress": self.progress,
                "createdAt": self.created_at,
                "updatedAt": self.updated_at,
                "completedAt": self.completed_at,
                "artifacts": [artifact.to_dict() for artifact in self.artifacts],
                "warnings": list(self.warnings),
                "error": self.error.to_dict() if self.error else None,
                "evidenceId": self.evidence_id,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CreativeJob:
        error_payload = payload.get("error")
        return cls(
            job_id=str(payload["jobId"]),
            project_id=str(payload["projectId"]),
            workflow_id=str(payload["workflowId"]),
            status=str(payload["status"]),
            current_step=str(payload.get("currentStep") or "queued"),
            progress=int(payload.get("progress") or 0),
            created_at=str(payload.get("createdAt") or utc_now_iso()),
            updated_at=str(payload.get("updatedAt") or utc_now_iso()),
            completed_at=(
                str(payload["completedAt"]) if payload.get("completedAt") is not None else None
            ),
            artifacts=tuple(Artifact.from_dict(item) for item in payload.get("artifacts") or ()),
            warnings=tuple(str(item) for item in payload.get("warnings") or ()),
            error=JobError.from_dict(error_payload) if isinstance(error_payload, dict) else None,
            evidence_id=(
                str(payload["evidenceId"]) if payload.get("evidenceId") is not None else None
            ),
        )


@dataclass(frozen=True)
class JobHistoryEvent:
    event_id: str
    job_id: str
    status: str
    step_id: str
    message: str
    created_at: str = field(default_factory=utc_now_iso)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_id(self.event_id, "eventId")
        validate_id(self.job_id, "jobId")
        if self.status not in VALID_JOB_STATUSES:
            raise DomainValidationError("history status must be canonical")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "eventId": self.event_id,
                "jobId": self.job_id,
                "status": self.status,
                "stepId": self.step_id,
                "message": self.message,
                "createdAt": self.created_at,
                "details": self.details,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> JobHistoryEvent:
        return cls(
            event_id=str(payload["eventId"]),
            job_id=str(payload["jobId"]),
            status=str(payload["status"]),
            step_id=str(payload.get("stepId") or "unknown"),
            message=str(payload.get("message") or ""),
            created_at=str(payload.get("createdAt") or utc_now_iso()),
            details=dict(payload.get("details") or {}),
        )


@dataclass(frozen=True)
class Project:
    schema_version: ClassVar[int] = 1

    project_id: str
    project_name: str
    workflow_id: str
    description: str = ""
    source_assets: tuple[SourceAsset, ...] = ()
    current_job: str | None = None
    job_history: tuple[str, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    quality_reports: tuple[QualityMetric, ...] = ()
    evidence: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        validate_id(self.project_id, "projectId")
        validate_id(self.workflow_id, "workflowId")
        if not self.project_name.strip():
            raise DomainValidationError("projectName must not be empty")
        if self.current_job is not None:
            validate_id(self.current_job, "currentJob")
        for job_id in self.job_history:
            validate_id(job_id, "jobHistory")
        for evidence_id in self.evidence:
            validate_id(evidence_id, "evidence")

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "schemaVersion": self.schema_version,
                "projectId": self.project_id,
                "projectName": self.project_name,
                "workflowId": self.workflow_id,
                "description": self.description,
                "sourceAssets": [asset.to_dict() for asset in self.source_assets],
                "currentJob": self.current_job,
                "jobHistory": list(self.job_history),
                "artifacts": [artifact.to_dict() for artifact in self.artifacts],
                "qualityReports": [report.to_dict() for report in self.quality_reports],
                "evidence": list(self.evidence),
                "createdAt": self.created_at,
                "updatedAt": self.updated_at,
            }
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Project:
        return cls(
            project_id=str(payload["projectId"]),
            project_name=str(payload["projectName"]),
            workflow_id=str(payload["workflowId"]),
            description=str(payload.get("description") or ""),
            source_assets=tuple(
                SourceAsset.from_dict(item) for item in payload.get("sourceAssets") or ()
            ),
            current_job=(
                str(payload["currentJob"]) if payload.get("currentJob") is not None else None
            ),
            job_history=tuple(str(item) for item in payload.get("jobHistory") or ()),
            artifacts=tuple(Artifact.from_dict(item) for item in payload.get("artifacts") or ()),
            quality_reports=tuple(
                QualityMetric.from_dict(item) for item in payload.get("qualityReports") or ()
            ),
            evidence=tuple(str(item) for item in payload.get("evidence") or ()),
            created_at=str(payload.get("createdAt") or utc_now_iso()),
            updated_at=str(payload.get("updatedAt") or utc_now_iso()),
        )
