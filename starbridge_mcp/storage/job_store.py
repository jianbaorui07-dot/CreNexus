from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

from starbridge_mcp.domain.errors import RecordNotFoundError
from starbridge_mcp.domain.models import CreativeJob, JobHistoryEvent, WorkflowPlan, validate_id
from starbridge_mcp.storage.atomic_json import atomic_write_json, read_json


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def job_directory(self, job_id: str) -> Path:
        validate_id(job_id, "jobId")
        return self.root / job_id

    def job_file(self, job_id: str) -> Path:
        return self.job_directory(job_id) / "job.json"

    def events_file(self, job_id: str) -> Path:
        return self.job_directory(job_id) / "events.jsonl"

    def plan_file(self, job_id: str) -> Path:
        return self.job_directory(job_id) / "plan.json"

    def save(self, job: CreativeJob, *, create_only: bool = False) -> CreativeJob:
        target = self.job_file(job.job_id)
        with self._lock:
            if create_only and target.exists():
                raise FileExistsError(f"job already exists: {job.job_id}")
            atomic_write_json(target, job.to_dict())
        return job

    def get(self, job_id: str) -> CreativeJob:
        target = self.job_file(job_id)
        with self._lock:
            if not target.is_file():
                raise RecordNotFoundError(f"job not found: {job_id}")
            return CreativeJob.from_dict(read_json(target))

    def list(self) -> list[CreativeJob]:
        jobs: list[CreativeJob] = []
        with self._lock:
            for target in sorted(self.root.glob("*/job.json")):
                try:
                    jobs.append(CreativeJob.from_dict(read_json(target)))
                except (KeyError, TypeError, ValueError):
                    continue
        return sorted(jobs, key=lambda job: job.updated_at, reverse=True)

    def append_event(self, event: JobHistoryEvent) -> None:
        target = self.events_file(event.job_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock, target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def save_plan(self, job_id: str, plan: WorkflowPlan) -> None:
        if plan.workflow_id != self.get(job_id).workflow_id:
            raise ValueError("plan workflowId does not match the job")
        with self._lock:
            atomic_write_json(self.plan_file(job_id), plan.to_dict())

    def get_plan(self, job_id: str) -> WorkflowPlan:
        target = self.plan_file(job_id)
        with self._lock:
            if not target.is_file():
                raise RecordNotFoundError(f"workflow plan not found for job: {job_id}")
            return WorkflowPlan.from_dict(read_json(target))

    def events(self, job_id: str) -> list[JobHistoryEvent]:
        target = self.events_file(job_id)
        if not target.is_file():
            return []
        events: list[JobHistoryEvent] = []
        with self._lock, target.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        events.append(JobHistoryEvent.from_dict(payload))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
        return events
