from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.domain.models import CreativeJob, JobHistoryEvent
from starbridge_mcp.storage.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def test_job_and_append_only_events_survive_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = JobStore(root / "jobs")
            job = CreativeJob(
                job_id="job-1",
                project_id="project-1",
                workflow_id="vector-delivery-v1",
            )
            store.save(job, create_only=True)
            store.append_event(
                JobHistoryEvent(
                    event_id="event-1",
                    job_id=job.job_id,
                    status="queued",
                    step_id="queued",
                    message="任务已建立",
                )
            )
            store.append_event(
                JobHistoryEvent(
                    event_id="event-2",
                    job_id=job.job_id,
                    status="running",
                    step_id="validate-input",
                    message="开始校验",
                )
            )

            reloaded = JobStore(root / "jobs")
            events = reloaded.events(job.job_id)
            reloaded_job = reloaded.get(job.job_id)

        self.assertEqual(job, reloaded_job)
        self.assertEqual(["queued", "running"], [event.status for event in events])


if __name__ == "__main__":
    unittest.main()
