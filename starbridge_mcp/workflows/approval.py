from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ApprovalRequest:
    approval_ref: str
    job_id: str
    workflow_id: str
    step_id: str
    plan_hash: str
    revision: int
    safe_root_ref: str
    expires_at: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "approvalRef": self.approval_ref,
            "jobId": self.job_id,
            "workflowId": self.workflow_id,
            "stepId": self.step_id,
            "planHash": self.plan_hash,
            "revision": self.revision,
            "safeRootRef": self.safe_root_ref,
            "expiresAt": self.expires_at,
        }


@dataclass
class _ApprovalRecord:
    request: ApprovalRequest
    expires_at: datetime
    used: bool = False


class ApprovalGate:
    def __init__(self, *, lifetime_seconds: int = 900) -> None:
        if lifetime_seconds < 1:
            raise ValueError("approval lifetime must be positive")
        self.lifetime_seconds = lifetime_seconds
        self._records: dict[str, _ApprovalRecord] = {}

    @staticmethod
    def _key(approval_ref: str) -> str:
        return hashlib.sha256(approval_ref.encode("utf-8")).hexdigest()

    def issue(
        self,
        *,
        job_id: str,
        workflow_id: str,
        step_id: str,
        plan_hash: str,
        revision: int,
        safe_root_ref: str,
    ) -> ApprovalRequest:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self.lifetime_seconds)
        approval_ref = f"approval-{secrets.token_urlsafe(24)}"
        request = ApprovalRequest(
            approval_ref=approval_ref,
            job_id=job_id,
            workflow_id=workflow_id,
            step_id=step_id,
            plan_hash=plan_hash,
            revision=revision,
            safe_root_ref=safe_root_ref,
            expires_at=expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        self._records[self._key(approval_ref)] = _ApprovalRecord(request, expires_at)
        return request

    def consume(
        self,
        approval_ref: str,
        *,
        confirm_execute: bool,
        job_id: str,
        workflow_id: str,
        step_id: str,
        plan_hash: str,
        revision: int,
        safe_root_ref: str,
    ) -> bool:
        if not confirm_execute:
            return False
        record = self._records.get(self._key(approval_ref))
        if record is None or record.used or datetime.now(timezone.utc) >= record.expires_at:
            return False
        expected = record.request
        if (
            expected.job_id != job_id
            or expected.workflow_id != workflow_id
            or expected.step_id != step_id
            or expected.plan_hash != plan_hash
            or expected.revision != revision
            or expected.safe_root_ref != safe_root_ref
        ):
            return False
        record.used = True
        return True
