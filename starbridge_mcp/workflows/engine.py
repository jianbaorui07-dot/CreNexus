from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CancellationToken,
)
from starbridge_mcp.core.app_data import AppDataPaths
from starbridge_mcp.domain.errors import DomainValidationError
from starbridge_mcp.domain.models import (
    TERMINAL_JOB_STATUSES,
    Artifact,
    CreativeJob,
    JobError,
    JobHistoryEvent,
    Project,
)
from starbridge_mcp.storage.evidence_store import EvidenceStore
from starbridge_mcp.storage.job_store import JobStore
from starbridge_mcp.storage.project_store import ProjectStore
from starbridge_mcp.workflows.approval import ApprovalGate, ApprovalRequest
from starbridge_mcp.workflows.registry import WorkflowRegistry
from starbridge_mcp.workflows.state_machine import JobStateMachine


@dataclass(frozen=True)
class EngineResult:
    job: CreativeJob
    approval: ApprovalRequest | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job": self.job.to_dict(),
            "approval": self.approval.to_dict() if self.approval else None,
        }


class WorkflowEngine:
    def __init__(
        self,
        *,
        registry: WorkflowRegistry,
        project_store: ProjectStore,
        job_store: JobStore,
        evidence_store: EvidenceStore,
        app_paths: AppDataPaths,
        approval_gate: ApprovalGate | None = None,
    ) -> None:
        self.registry = registry
        self.project_store = project_store
        self.job_store = job_store
        self.evidence_store = evidence_store
        self.app_paths = app_paths
        self.approval_gate = approval_gate or ApprovalGate()
        self.state_machine = JobStateMachine(job_store)
        self._cancellations: dict[str, CancellationToken] = {}

    def create_job(self, project_id: str, workflow_id: str, inputs: dict[str, Any]) -> CreativeJob:
        project = self.project_store.get(project_id)
        if project.workflow_id != workflow_id:
            raise DomainValidationError("project workflowId does not match the requested workflow")
        plan = self.registry.create_plan(workflow_id, inputs)
        job = CreativeJob(
            job_id=f"job-{uuid4().hex[:16]}",
            project_id=project_id,
            workflow_id=workflow_id,
            current_step=plan.steps[0].step_id,
        )
        self.job_store.save(job, create_only=True)
        self.job_store.save_plan(job.job_id, plan)
        self.job_store.append_event(
            JobHistoryEvent(
                event_id=f"event-{uuid4().hex[:16]}",
                job_id=job.job_id,
                status="queued",
                step_id=job.current_step,
                message="工作流计划已建立，尚未执行写入。",
                details={"planId": plan.plan_id, "planHash": plan.plan_hash},
            )
        )
        self.project_store.save(
            replace(
                project,
                current_job=job.job_id,
                job_history=(*project.job_history, job.job_id),
            )
        )
        self._cancellations[job.job_id] = CancellationToken()
        return job

    def _token(self, job_id: str) -> CancellationToken:
        return self._cancellations.setdefault(job_id, CancellationToken())

    @staticmethod
    def _step_index(job: CreativeJob, step_ids: list[str]) -> int:
        try:
            return step_ids.index(job.current_step)
        except ValueError as exc:
            raise DomainValidationError(
                "job currentStep is not present in its persisted plan"
            ) from exc

    def _context(self, job: CreativeJob, step: Any) -> AdapterContext:
        return AdapterContext(
            job_id=job.job_id,
            project_id=job.project_id,
            workflow_id=job.workflow_id,
            step=step,
            app_paths=self.app_paths,
            cancellation=self._token(job.job_id),
        )

    def _fail(
        self,
        job: CreativeJob,
        *,
        step_id: str,
        error: JobError,
        warnings: tuple[str, ...] = (),
        details: dict[str, object] | None = None,
    ) -> EngineResult:
        failed = self.state_machine.transition(
            job,
            "failed",
            current_step=step_id,
            progress=max(job.progress, 1),
            message=error.message,
            warnings=(*job.warnings, *warnings),
            error=error,
            details=details,
        )
        self._clear_project_current_job(failed)
        return EngineResult(failed)

    def _clear_project_current_job(self, job: CreativeJob) -> Project:
        project = self.project_store.get(job.project_id)
        if project.current_job != job.job_id:
            return project
        return self.project_store.save(replace(project, current_job=None))

    def _request_approval(self, job: CreativeJob, step_id: str) -> EngineResult:
        plan = self.job_store.get_plan(job.job_id)
        request = self.approval_gate.issue(
            job_id=job.job_id,
            workflow_id=job.workflow_id,
            step_id=step_id,
            plan_hash=plan.plan_hash,
            revision=plan.revision,
            safe_root_ref="starbridge-app-data",
        )
        paused = self.state_machine.transition(
            job,
            "needs_user",
            current_step=step_id,
            progress=job.progress,
            message="此步骤会执行受控本地写入，等待用户确认。",
            details={
                "planHash": plan.plan_hash,
                "revision": plan.revision,
                "safeRootRef": "starbridge-app-data",
            },
        )
        return EngineResult(paused, request)

    def _pause_for_user(
        self, job: CreativeJob, step_id: str, result: AdapterResult
    ) -> EngineResult:
        message = str(
            result.output.get("message") or "此步骤尚未得到终态结果，请稍后继续读取同一任务。"
        )
        paused = self.state_machine.transition(
            job,
            "needs_user",
            current_step=step_id,
            progress=job.progress,
            message=message,
            warnings=(*job.warnings, *result.warnings),
            details={"userActionKind": "resume-read", "evidence": result.output},
        )
        return EngineResult(paused)

    def run(
        self,
        job_id: str,
        *,
        approval_ref: str | None = None,
        confirm_execute: bool = False,
    ) -> EngineResult:
        job = self.job_store.get(job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return EngineResult(job)
        plan = self.job_store.get_plan(job_id)
        step_ids = [step.step_id for step in plan.steps]
        start_index = self._step_index(job, step_ids)
        approved_step: str | None = None
        if job.status == "needs_user":
            current_step = plan.steps[start_index]
            if current_step.requires_confirmation:
                if not approval_ref or not self.approval_gate.consume(
                    approval_ref,
                    confirm_execute=confirm_execute,
                    job_id=job.job_id,
                    workflow_id=job.workflow_id,
                    step_id=job.current_step,
                    plan_hash=plan.plan_hash,
                    revision=plan.revision,
                    safe_root_ref="starbridge-app-data",
                ):
                    return self._request_approval(job, job.current_step)
                approved_step = job.current_step

        job = self.state_machine.transition(
            job,
            "running",
            current_step=job.current_step,
            progress=max(job.progress, 1),
            message="工作流开始执行。",
        )
        accumulated_artifacts: tuple[Artifact, ...] = job.artifacts
        accumulated_warnings = job.warnings
        evidence_steps: list[dict[str, Any]] = [
            evidence
            for event in self.job_store.events(job_id)
            if isinstance((evidence := event.details.get("evidence")), dict)
        ]

        for index in range(start_index, len(plan.steps)):
            step = plan.steps[index]
            if self._token(job_id).cancelled:
                cancelled = self.state_machine.transition(
                    job,
                    "cancelled",
                    current_step=step.step_id,
                    progress=job.progress,
                    message="任务已在安全点取消。",
                )
                self._clear_project_current_job(cancelled)
                return EngineResult(cancelled)
            try:
                adapter = self.registry.adapter(step.adapter)
            except KeyError:
                return self._fail(
                    job,
                    step_id=step.step_id,
                    error=JobError(
                        code="adapter_not_registered",
                        message="工作流所需适配器尚未注册。",
                        next_steps=("检查工作流和本机集成配置。",),
                    ),
                )
            context = self._context(job, step)
            try:
                probe = adapter.probe(context)
                adapter.plan(context)
                validation = adapter.validate(context)
            except (OSError, ValueError):
                return self._fail(
                    job,
                    step_id=step.step_id,
                    error=JobError(
                        code="adapter_preflight_failed",
                        message="适配器预检未完成。",
                        next_steps=("检查输入和本机软件状态后重试。",),
                    ),
                )
            if not probe.available:
                return self._fail(
                    job,
                    step_id=step.step_id,
                    error=JobError(
                        code="adapter_unavailable",
                        message=probe.message,
                        retryable=True,
                        next_steps=("启动或配置所需本机软件后重试。",),
                    ),
                )
            if not validation.ok:
                return self._fail(
                    job,
                    step_id=step.step_id,
                    error=validation.error
                    or JobError(code="validation_failed", message="步骤输入校验失败。"),
                    warnings=validation.warnings,
                )
            if step.requires_confirmation and approved_step != step.step_id:
                return self._request_approval(job, step.step_id)

            max_attempts = max(1, min(3, int(step.retry_policy.get("maxAttempts", 1))))
            result: AdapterResult | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = adapter.execute(context)
                except (OSError, ValueError):
                    result = AdapterResult(
                        status="failed",
                        error=JobError(
                            code="adapter_execution_failed",
                            message="适配器执行未完成。",
                            retryable=attempt < max_attempts,
                        ),
                        retryable=attempt < max_attempts,
                    )
                if result.status != "failed" or not result.retryable or attempt == max_attempts:
                    break
            assert result is not None
            if result.status == "needs_user":
                return self._pause_for_user(job, step.step_id, result)
            if result.status == "cancelled":
                cancelled = self.state_machine.transition(
                    job,
                    "cancelled",
                    current_step=step.step_id,
                    progress=job.progress,
                    message="适配器已取消任务。",
                    warnings=(*job.warnings, *result.warnings),
                )
                self._clear_project_current_job(cancelled)
                return EngineResult(cancelled)
            if result.status == "failed":
                rollback_requested = bool(step.rollback_policy.get("enabled", False))
                rolled_back = adapter.rollback(context, result) if rollback_requested else False
                return self._fail(
                    job,
                    step_id=step.step_id,
                    error=result.error
                    or JobError(code="adapter_failed", message="适配器执行失败。"),
                    warnings=result.warnings,
                    details={"rollbackRequested": rollback_requested, "rolledBack": rolled_back},
                )

            collected = adapter.collect_artifacts(context, result)
            accumulated_artifacts = (*accumulated_artifacts, *collected)
            accumulated_warnings = (
                *accumulated_warnings,
                *validation.warnings,
                *result.warnings,
            )
            step_evidence = adapter.collect_evidence(context, result)
            evidence_steps.append(step_evidence)
            next_step = (
                plan.steps[index + 1].step_id if index + 1 < len(plan.steps) else step.step_id
            )
            step_progress = min(99, round(((index + 1) / len(plan.steps)) * 100))
            if index + 1 < len(plan.steps):
                job = self.state_machine.transition(
                    job,
                    "running",
                    current_step=next_step,
                    progress=step_progress,
                    message=f"步骤 {step.step_id} 已完成。",
                    artifacts=accumulated_artifacts,
                    warnings=accumulated_warnings,
                    details={"evidence": step_evidence},
                )
            approved_step = None

        evidence_id = f"evidence-{uuid4().hex[:16]}"
        self.evidence_store.save(
            evidence_id,
            {
                "evidenceId": evidence_id,
                "jobId": job.job_id,
                "projectId": job.project_id,
                "workflowId": job.workflow_id,
                "planId": plan.plan_id,
                "planHash": plan.plan_hash,
                "status": "completed",
                "steps": evidence_steps,
                "artifactIds": [artifact.artifact_id for artifact in accumulated_artifacts],
                "warnings": list(accumulated_warnings),
            },
        )
        completed = self.state_machine.transition(
            job,
            "completed",
            current_step="completed",
            progress=100,
            message="工作流已完成。",
            artifacts=accumulated_artifacts,
            warnings=accumulated_warnings,
            evidence_id=evidence_id,
            details={"evidence": evidence_steps[-1] if evidence_steps else {}},
        )
        project = self.project_store.get(completed.project_id)
        self.project_store.save(
            replace(
                project,
                current_job=None,
                artifacts=(*project.artifacts, *accumulated_artifacts),
                evidence=(*project.evidence, evidence_id),
            )
        )
        return EngineResult(completed)

    def cancel(self, job_id: str) -> CreativeJob:
        job = self.job_store.get(job_id)
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        self._token(job_id).cancel()
        plan = self.job_store.get_plan(job_id)
        step = plan.steps[self._step_index(job, [item.step_id for item in plan.steps])]
        try:
            self.registry.adapter(step.adapter).cancel(self._context(job, step))
        except (KeyError, OSError, ValueError):
            pass
        cancelled = self.state_machine.transition(
            job,
            "cancelled",
            current_step=step.step_id,
            progress=job.progress,
            message="用户已取消任务。",
        )
        self._clear_project_current_job(cancelled)
        return cancelled
