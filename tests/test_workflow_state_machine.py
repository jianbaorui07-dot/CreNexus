from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.domain.errors import DomainValidationError
from starbridge_mcp.domain.models import CreativeJob
from starbridge_mcp.storage.job_store import JobStore
from starbridge_mcp.workflows.state_machine import JobStateMachine


class WorkflowStateMachineTests(unittest.TestCase):
    def test_six_state_lifecycle_and_terminal_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs")
            machine = JobStateMachine(store)
            job = CreativeJob(
                job_id="job-1",
                project_id="project-1",
                workflow_id="workflow-1",
            )
            store.save(job)
            running = machine.transition(
                job,
                "running",
                current_step="step-1",
                progress=10,
                message="running",
            )
            paused = machine.transition(
                running,
                "needs_user",
                current_step="step-1",
                progress=10,
                message="confirm",
            )
            resumed = machine.transition(
                paused,
                "running",
                current_step="step-1",
                progress=10,
                message="resumed",
            )
            completed = machine.transition(
                resumed,
                "completed",
                current_step="completed",
                progress=100,
                message="completed",
            )

            with self.assertRaises(DomainValidationError):
                machine.transition(
                    completed,
                    "running",
                    current_step="step-1",
                    progress=100,
                    message="invalid",
                )

            events = store.events(job.job_id)

        self.assertEqual(
            ["running", "needs_user", "running", "completed"],
            [event.status for event in events],
        )
        self.assertIsNotNone(completed.completed_at)

    def test_progress_cannot_move_backwards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs")
            machine = JobStateMachine(store)
            job = CreativeJob(
                job_id="job-1",
                project_id="project-1",
                workflow_id="workflow-1",
                status="running",
                progress=50,
            )
            with self.assertRaises(DomainValidationError):
                machine.transition(
                    job,
                    "running",
                    current_step="step-1",
                    progress=49,
                    message="invalid",
                )


if __name__ == "__main__":
    unittest.main()
