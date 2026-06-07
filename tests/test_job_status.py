from __future__ import annotations

import unittest

from starbridge_mcp.core.job_status import JobStatus


class JobStatusTests(unittest.TestCase):
    def test_all_status_values_are_accepted(self) -> None:
        for status in ("queued", "running", "completed", "failed", "cancelled", "needs_user"):
            with self.subTest(status=status):
                payload = JobStatus(job_id="job_1", bridge="starbridge", action="demo", status=status).to_dict()
                self.assertEqual(status, payload["status"])

    def test_progress_must_be_bounded(self) -> None:
        with self.assertRaises(ValueError):
            JobStatus(job_id="job_1", bridge="starbridge", action="demo", status="queued", progress=101)
