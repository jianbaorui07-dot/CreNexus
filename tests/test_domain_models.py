from __future__ import annotations

import unittest

from starbridge_mcp.domain.errors import DomainValidationError
from starbridge_mcp.domain.models import CreativeJob, JobError, Project, SourceAsset, utc_now_iso

SHA256 = "a" * 64


class DomainModelTests(unittest.TestCase):
    def test_project_round_trip_uses_public_camel_case_contract(self) -> None:
        source = SourceAsset(
            asset_id="asset-1",
            basename="source.png",
            relative_path="projects/project-1/source/asset-1.png",
            sha256=SHA256,
            media_type="image/png",
            size_bytes=10,
        )
        project = Project(
            project_id="project-1",
            project_name="示例项目",
            workflow_id="vector-delivery-v1",
            source_assets=(source,),
        )

        payload = project.to_dict()
        restored = Project.from_dict(payload)

        self.assertEqual(project, restored)
        self.assertEqual("project-1", payload["projectId"])
        self.assertNotIn("project_id", payload)
        self.assertNotIn("C:\\", str(payload))

    def test_creative_job_supports_all_six_states(self) -> None:
        for status in ("queued", "running", "needs_user"):
            job = CreativeJob(
                job_id=f"job-{status}",
                project_id="project-1",
                workflow_id="vector-delivery-v1",
                status=status,
            )
            self.assertEqual(status, CreativeJob.from_dict(job.to_dict()).status)

        for status in ("completed", "cancelled"):
            job = CreativeJob(
                job_id=f"job-{status}",
                project_id="project-1",
                workflow_id="vector-delivery-v1",
                status=status,
                progress=100,
                completed_at=utc_now_iso(),
            )
            self.assertEqual(status, job.status)

        failed = CreativeJob(
            job_id="job-failed",
            project_id="project-1",
            workflow_id="vector-delivery-v1",
            status="failed",
            progress=100,
            completed_at=utc_now_iso(),
            error=JobError(code="adapter_failed", message="执行失败"),
        )
        self.assertEqual("adapter_failed", failed.to_dict()["error"]["code"])

    def test_absolute_or_parent_paths_are_rejected(self) -> None:
        for relative_path in ("C:/private/source.png", "../source.png", "/tmp/source.png"):
            with (
                self.subTest(relative_path=relative_path),
                self.assertRaises(DomainValidationError),
            ):
                SourceAsset(
                    asset_id="asset-1",
                    basename="source.png",
                    relative_path=relative_path,
                    sha256=SHA256,
                    media_type="image/png",
                    size_bytes=1,
                )

    def test_failed_and_terminal_jobs_require_complete_structured_state(self) -> None:
        with self.assertRaises(DomainValidationError):
            CreativeJob(
                job_id="job-failed",
                project_id="project-1",
                workflow_id="vector-delivery-v1",
                status="failed",
                completed_at=utc_now_iso(),
            )
        with self.assertRaises(DomainValidationError):
            CreativeJob(
                job_id="job-completed",
                project_id="project-1",
                workflow_id="vector-delivery-v1",
                status="completed",
            )


if __name__ == "__main__":
    unittest.main()
