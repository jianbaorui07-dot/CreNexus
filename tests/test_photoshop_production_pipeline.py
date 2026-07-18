from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from starbridge_mcp.adapters.photoshop.workflow_adapter import PhotoshopWorkflowAdapter
from starbridge_mcp.core.app_data import resolve_app_data_paths
from starbridge_mcp.storage import AssetStore, EvidenceStore, JobStore, ProjectStore
from starbridge_mcp.workflows.engine import WorkflowEngine
from starbridge_mcp.workflows.photoshop_production_pipeline import (
    WORKFLOW_ID,
    create_photoshop_production_plan,
    register_photoshop_production_workflow,
)
from starbridge_mcp.workflows.registry import WorkflowRegistry


class FakePhotoshopProxy:
    def __init__(self, *, connected: bool = True) -> None:
        self.connected = connected
        self.production_calls = 0

    def status(self) -> dict[str, object]:
        return {
            "ok": True,
            "node_proxy_running": True,
            "uxp_client_connected": self.connected,
            "photoshop_host_seen": self.connected,
            "photoshop_host": {"app": "Photoshop", "version": "27.0"},
        }

    def rpc(self, method: str, params: dict[str, object], **_kwargs: object) -> dict[str, object]:
        if method == "ps.document.info":
            return {
                "jsonrpc": "2.0",
                "id": "test",
                "result": {
                    "ok": True,
                    "document": {
                        "title": "Private Client Campaign.psd",
                        "width": 1600,
                        "height": 900,
                        "resolution": 300,
                        "layer_count": 12,
                    },
                    "photoshop_host": {"app": "Photoshop", "version": "27.0"},
                },
            }
        if method == "ps.production.execute_confirmed":
            self.production_calls += 1
            for output_path in dict(params["outputs"]).values():
                Path(str(output_path)).write_bytes(b"starbridge-photoshop-output")
            return {
                "jsonrpc": "2.0",
                "id": "test",
                "result": {
                    "ok": True,
                    "success": True,
                    "executed": True,
                    "sandbox_copy": True,
                    "source_overwritten": False,
                    "rollback_supported": True,
                    "warnings": [],
                },
            }
        raise AssertionError(f"unexpected method: {method}")


class PhotoshopProductionPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths = resolve_app_data_paths(Path(self.temporary.name) / "app-data")
        self.projects = ProjectStore(self.paths.projects)
        self.jobs = JobStore(self.paths.jobs)
        self.evidence = EvidenceStore(self.paths.evidence)
        self.project = self.projects.create("Photoshop 安全副本", WORKFLOW_ID)
        external = Path(self.temporary.name) / "input.png"
        external.write_bytes(b"explicit-project-image")
        asset = AssetStore(self.paths.projects).import_source(
            self.project.project_id, external, confirm_import=True
        )
        self.project = self.projects.save(replace(self.project, source_assets=(asset,)))
        self.asset = asset

    def _engine(self, proxy: FakePhotoshopProxy) -> WorkflowEngine:
        registry = WorkflowRegistry()
        register_photoshop_production_workflow(
            registry,
            adapter=PhotoshopWorkflowAdapter(
                status_reader=proxy.status,
                rpc_runner=proxy.rpc,
            ),
        )
        return WorkflowEngine(
            registry=registry,
            project_store=self.projects,
            job_store=self.jobs,
            evidence_store=self.evidence,
            app_paths=self.paths,
        )

    def _create_job(self, engine: WorkflowEngine):
        return engine.create_job(
            self.project.project_id,
            WORKFLOW_ID,
            {
                "sourceAssetRelativePath": self.asset.relative_path,
                "sourceAssetSha256": self.asset.sha256,
                "outputFormats": ["png", "jpeg", "psd"],
                "resizeCanvas": True,
                "canvasWidth": 1920,
                "canvasHeight": 1080,
                "brightness": 8,
                "contrast": 4,
                "saturation": 6,
                "exportSubject": False,
            },
        )

    def test_plan_is_fixed_copy_first_and_contains_no_absolute_path(self) -> None:
        plan = create_photoshop_production_plan(
            {
                "sourceAssetRelativePath": self.asset.relative_path,
                "sourceAssetSha256": self.asset.sha256,
                "outputFormats": ["png", "psd"],
            }
        )
        execute_step = next(step for step in plan.steps if step.step_id == "execute-production")
        self.assertTrue(execute_step.requires_confirmation)
        self.assertTrue(execute_step.rollback_policy["enabled"])
        self.assertIn("duplicate-before-write", execute_step.validation)
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False)
        self.assertNotIn(str(self.paths.root), serialized)
        self.assertNotIn("descriptor", serialized.lower())

    def test_unconnected_proxy_pauses_and_resumes_without_write_approval(self) -> None:
        proxy = FakePhotoshopProxy(connected=False)
        engine = self._engine(proxy)
        job = self._create_job(engine)

        paused = engine.run(job.job_id)
        self.assertEqual("needs_user", paused.job.status)
        self.assertEqual("probe-photoshop", paused.job.current_step)
        self.assertIsNone(paused.approval)
        self.assertEqual(0, proxy.production_calls)

        proxy.connected = True
        resumed = engine.run(job.job_id)
        self.assertEqual("needs_user", resumed.job.status)
        self.assertEqual("execute-production", resumed.job.current_step)
        self.assertIsNotNone(resumed.approval)
        self.assertEqual(0, proxy.production_calls)

    def test_full_simulated_workflow_writes_real_hashed_artifacts_and_redacted_evidence(
        self,
    ) -> None:
        proxy = FakePhotoshopProxy()
        engine = self._engine(proxy)
        job = self._create_job(engine)

        first = engine.run(job.job_id)
        self.assertEqual("execute-production", first.job.current_step)
        self.assertIsNotNone(first.approval)
        second = engine.run(
            job.job_id,
            approval_ref=first.approval.approval_ref,
            confirm_execute=True,
        )
        self.assertEqual("needs_user", second.job.status)
        self.assertEqual("review-result", second.job.current_step)
        self.assertEqual(1, proxy.production_calls)
        self.assertEqual(3, len(second.job.artifacts))
        self.assertEqual(
            {"photoshop-preview.png", "photoshop-preview.jpg", "photoshop-copy.psd"},
            {artifact.basename for artifact in second.job.artifacts},
        )
        for artifact in second.job.artifacts:
            self.assertEqual(64, len(artifact.sha256))

        final = engine.run(job.job_id)
        self.assertIsNotNone(final.approval)
        completed = engine.run(
            job.job_id,
            approval_ref=final.approval.approval_ref,
            confirm_execute=True,
        )
        self.assertEqual("completed", completed.job.status)

        runtime_text = (self.paths.jobs / job.job_id / "photoshop-runtime.json").read_text(
            encoding="utf-8"
        )
        evidence_text = self.evidence.manifest_file(str(completed.job.evidence_id)).read_text(
            encoding="utf-8"
        )
        for text in (runtime_text, evidence_text):
            self.assertNotIn("Private Client Campaign", text)
            self.assertNotIn(str(self.paths.root), text)
            self.assertNotIn(str(Path(self.temporary.name)), text)
        self.assertIn('"sourcePathPersisted": false', runtime_text)

    def test_invalid_format_is_rejected_before_job_creation(self) -> None:
        with self.assertRaises(ValueError):
            create_photoshop_production_plan(
                {
                    "sourceAssetRelativePath": self.asset.relative_path,
                    "sourceAssetSha256": self.asset.sha256,
                    "outputFormats": ["tiff"],
                }
            )

    def test_subject_export_registers_only_fixed_subject_and_requested_outputs(self) -> None:
        proxy = FakePhotoshopProxy()
        engine = self._engine(proxy)
        job = engine.create_job(
            self.project.project_id,
            WORKFLOW_ID,
            {
                "sourceAssetRelativePath": self.asset.relative_path,
                "sourceAssetSha256": self.asset.sha256,
                "outputFormats": ["png"],
                "exportSubject": True,
            },
        )

        approval = engine.run(job.job_id).approval
        self.assertIsNotNone(approval)
        executed = engine.run(
            job.job_id,
            approval_ref=approval.approval_ref,
            confirm_execute=True,
        )

        self.assertEqual("review-result", executed.job.current_step)
        self.assertEqual(
            {"photoshop-preview.png", "photoshop-subject.png"},
            {artifact.basename for artifact in executed.job.artifacts},
        )


if __name__ == "__main__":
    unittest.main()
