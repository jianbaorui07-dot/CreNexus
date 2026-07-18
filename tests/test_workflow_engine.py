from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CreativeAdapter,
    ProbeResult,
    ValidationReport,
)
from starbridge_mcp.core.app_data import resolve_app_data_paths
from starbridge_mcp.domain.models import JobError, WorkflowStep
from starbridge_mcp.storage.evidence_store import EvidenceStore
from starbridge_mcp.storage.job_store import JobStore
from starbridge_mcp.storage.project_store import ProjectStore
from starbridge_mcp.workflows.engine import WorkflowEngine
from starbridge_mcp.workflows.registry import WorkflowRegistry, build_workflow_plan


class FakeAdapter(CreativeAdapter):
    def __init__(
        self,
        adapter_id: str,
        *,
        available: bool = True,
        result: AdapterResult | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.available = available
        self.result = result or AdapterResult(status="completed")
        self.execute_count = 0
        self.rollback_count = 0

    def probe(self, context: AdapterContext) -> ProbeResult:
        return ProbeResult(
            available=self.available,
            connection_state="available" if self.available else "not_running",
            message="adapter ready" if self.available else "adapter is unavailable",
        )

    def plan(self, context: AdapterContext) -> dict[str, object]:
        return {"stepId": context.step.step_id, "writes": context.step.requires_confirmation}

    def validate(self, context: AdapterContext) -> ValidationReport:
        return ValidationReport(ok=True)

    def execute(self, context: AdapterContext) -> AdapterResult:
        self.execute_count += 1
        return self.result

    def rollback(self, context: AdapterContext, result: AdapterResult) -> bool:
        self.rollback_count += 1
        return True


class WorkflowEngineTests(unittest.TestCase):
    def create_engine(self, root: Path, *, write_result: AdapterResult | None = None):
        paths = resolve_app_data_paths(root)
        projects = ProjectStore(paths.projects)
        jobs = JobStore(paths.jobs)
        evidence = EvidenceStore(paths.evidence)
        registry = WorkflowRegistry()
        read_adapter = FakeAdapter("read-adapter")
        write_adapter = FakeAdapter("write-adapter", result=write_result)
        registry.register_adapter(read_adapter)
        registry.register_adapter(write_adapter)
        registry.register_workflow(
            "workflow-1",
            lambda inputs: build_workflow_plan(
                "workflow-1",
                (
                    WorkflowStep(step_id="validate", adapter="read-adapter"),
                    WorkflowStep(
                        step_id="write",
                        adapter="write-adapter",
                        requires_confirmation=True,
                        retry_policy={"maxAttempts": 1},
                        rollback_policy={"enabled": True},
                    ),
                ),
            ),
        )
        engine = WorkflowEngine(
            registry=registry,
            project_store=projects,
            job_store=jobs,
            evidence_store=evidence,
            app_paths=paths,
        )
        project = projects.create("测试项目", "workflow-1")
        return engine, project, read_adapter, write_adapter

    def test_engine_pauses_before_write_and_resumes_with_bound_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine, project, read_adapter, write_adapter = self.create_engine(Path(directory))
            job = engine.create_job(project.project_id, "workflow-1", {})

            paused = engine.run(job.job_id)

            self.assertEqual("needs_user", paused.job.status)
            self.assertIsNotNone(paused.approval)
            self.assertEqual(1, read_adapter.execute_count)
            self.assertEqual(0, write_adapter.execute_count)

            completed = engine.run(
                job.job_id,
                approval_ref=paused.approval.approval_ref,
                confirm_execute=True,
            )
            persisted_project = engine.project_store.get(project.project_id)
            evidence = engine.evidence_store.get(completed.job.evidence_id or "missing")

        self.assertEqual("completed", completed.job.status)
        self.assertEqual(1, write_adapter.execute_count)
        self.assertIsNone(persisted_project.current_job)
        self.assertEqual(completed.job.evidence_id, persisted_project.evidence[-1])
        self.assertEqual(
            ["read-adapter", "write-adapter"], [step["adapter"] for step in evidence["steps"]]
        )

    def test_confirmation_is_explicit_and_single_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine, project, _, write_adapter = self.create_engine(Path(directory))
            job = engine.create_job(project.project_id, "workflow-1", {})
            first = engine.run(job.job_id)
            assert first.approval is not None

            still_paused = engine.run(
                job.job_id,
                approval_ref=first.approval.approval_ref,
                confirm_execute=False,
            )
            assert still_paused.approval is not None
            completed = engine.run(
                job.job_id,
                approval_ref=still_paused.approval.approval_ref,
                confirm_execute=True,
            )

        self.assertEqual("completed", completed.job.status)
        self.assertEqual(1, write_adapter.execute_count)

    def test_failed_write_runs_declared_rollback_and_returns_structured_error(self) -> None:
        failed_result = AdapterResult(
            status="failed",
            error=JobError(code="write_failed", message="写入失败"),
        )
        with tempfile.TemporaryDirectory() as directory:
            engine, project, _, write_adapter = self.create_engine(
                Path(directory), write_result=failed_result
            )
            job = engine.create_job(project.project_id, "workflow-1", {})
            paused = engine.run(job.job_id)
            assert paused.approval is not None
            failed = engine.run(
                job.job_id,
                approval_ref=paused.approval.approval_ref,
                confirm_execute=True,
            )

        self.assertEqual("failed", failed.job.status)
        self.assertEqual("write_failed", failed.job.error.code if failed.job.error else None)
        self.assertEqual(1, write_adapter.rollback_count)

    def test_cancelled_job_is_persisted_and_project_is_released(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            engine, project, _, _ = self.create_engine(Path(directory))
            job = engine.create_job(project.project_id, "workflow-1", {})
            cancelled = engine.cancel(job.job_id)
            persisted_project = engine.project_store.get(project.project_id)

        self.assertEqual("cancelled", cancelled.status)
        self.assertIsNone(persisted_project.current_job)

    def test_non_write_user_pause_resumes_without_an_approval_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = resolve_app_data_paths(Path(directory))
            projects = ProjectStore(paths.projects)
            jobs = JobStore(paths.jobs)
            registry = WorkflowRegistry()
            adapter = FakeAdapter(
                "poll-adapter",
                result=AdapterResult(
                    status="needs_user",
                    output={"message": "任务仍在运行，请稍后刷新。"},
                ),
            )
            registry.register_adapter(adapter)
            registry.register_workflow(
                "poll-workflow",
                lambda inputs: build_workflow_plan(
                    "poll-workflow", (WorkflowStep(step_id="poll", adapter="poll-adapter"),)
                ),
            )
            engine = WorkflowEngine(
                registry=registry,
                project_store=projects,
                job_store=jobs,
                evidence_store=EvidenceStore(paths.evidence),
                app_paths=paths,
            )
            project = projects.create("轮询测试", "poll-workflow")
            job = engine.create_job(project.project_id, "poll-workflow", {})

            paused = engine.run(job.job_id)
            adapter.result = AdapterResult(status="completed")
            completed = engine.run(job.job_id)

        self.assertEqual("needs_user", paused.job.status)
        self.assertIsNone(paused.approval)
        self.assertEqual("completed", completed.job.status)
        self.assertEqual(2, adapter.execute_count)


if __name__ == "__main__":
    unittest.main()
