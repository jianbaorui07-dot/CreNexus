from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from starbridge_mcp.core.app_data import resolve_app_data_paths
from starbridge_mcp.storage.asset_store import AssetStore
from starbridge_mcp.storage.evidence_store import EvidenceStore
from starbridge_mcp.storage.job_store import JobStore
from starbridge_mcp.storage.project_store import ProjectStore
from starbridge_mcp.vectorization.engine import VectorizationError
from starbridge_mcp.workflows.engine import EngineResult, WorkflowEngine
from starbridge_mcp.workflows.registry import WorkflowRegistry
from starbridge_mcp.workflows.vector_delivery_pipeline import (
    WORKFLOW_ID,
    create_vector_delivery_plan,
    register_vector_delivery_workflow,
)


class VectorDeliveryPipelineTests(unittest.TestCase):
    def create_runtime(self, root: Path):
        paths = resolve_app_data_paths(root)
        projects = ProjectStore(paths.projects)
        jobs = JobStore(paths.jobs)
        registry = WorkflowRegistry()
        register_vector_delivery_workflow(registry)
        engine = WorkflowEngine(
            registry=registry,
            project_store=projects,
            job_store=jobs,
            evidence_store=EvidenceStore(paths.evidence),
            app_paths=paths,
        )
        project = projects.create("矢量交付测试", WORKFLOW_ID)
        source = root / "source.png"
        image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        image.paste((0, 255, 0, 255), (16, 0, 32, 16))
        image.paste((0, 0, 255, 255), (0, 16, 16, 32))
        image.paste((255, 255, 0, 255), (16, 16, 32, 32))
        image.save(source)
        asset = AssetStore(paths.projects).import_source(
            project.project_id, source, confirm_import=True
        )
        project = projects.save(replace(project, source_assets=(asset,)))
        return engine, project, asset

    @staticmethod
    def confirm_until_terminal(engine: WorkflowEngine, result: EngineResult) -> EngineResult:
        for _ in range(8):
            if result.job.status != "needs_user":
                return result
            assert result.approval is not None
            result = engine.run(
                result.job.job_id,
                approval_ref=result.approval.approval_ref,
                confirm_execute=True,
            )
        raise AssertionError("workflow did not reach a terminal state")

    def test_plan_always_places_exact_reconstruction_before_drawing(self) -> None:
        plan = create_vector_delivery_plan(
            {
                "sourceAssetRelativePath": "projects/project-1/source/asset-1.png",
                "drawingMode": "artisan",
            }
        )
        step_ids = [step.step_id for step in plan.steps]

        self.assertLess(step_ids.index("exact-reconstruction"), step_ids.index("draw-vector"))
        exact_step = plan.steps[step_ids.index("verify-exact-baseline")]
        self.assertIn("image-trace-not-used", exact_step.validation)
        self.assertTrue(plan.steps[step_ids.index("exact-reconstruction")].requires_confirmation)
        self.assertTrue(plan.steps[step_ids.index("draw-vector")].requires_confirmation)
        self.assertTrue(plan.steps[step_ids.index("review-result")].requires_confirmation)

    def test_plan_preserves_customer_selected_exact_safety_parameters(self) -> None:
        plan = create_vector_delivery_plan(
            {
                "sourceAssetRelativePath": "projects/project-1/source/asset-1.png",
                "drawingMode": "artisan",
                "parameters": {"exact": {"maxDimension": 1024, "maxSvgSizeMb": 128}},
            }
        )

        exact_step = next(step for step in plan.steps if step.step_id == "exact-reconstruction")
        self.assertEqual(
            {"maxDimension": 1024, "maxSvgSizeMb": 128},
            exact_step.input_data["parameters"],
        )

    def test_exact_mode_stops_after_verified_pixel_delivery(self) -> None:
        plan = create_vector_delivery_plan(
            {
                "sourceAssetRelativePath": "projects/project-1/source/asset-1.png",
                "drawingMode": "exact",
            }
        )

        self.assertEqual(
            [
                "validate-source",
                "exact-reconstruction",
                "verify-exact-baseline",
                "review-result",
                "collect-delivery",
            ],
            [step.step_id for step in plan.steps],
        )
        review_step = next(step for step in plan.steps if step.step_id == "review-result")
        self.assertEqual("pixel-reconstruction", review_step.input_data["review"])

    def test_plan_rejects_unbounded_exact_svg_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "maxSvgSizeMb"):
            create_vector_delivery_plan(
                {
                    "sourceAssetRelativePath": "projects/project-1/source/asset-1.png",
                    "parameters": {"exact": {"maxSvgSizeMb": 512}},
                }
            )

    def test_real_small_image_completes_exact_then_lightweight_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, project, asset = self.create_runtime(root)
            job = engine.create_job(
                project.project_id,
                WORKFLOW_ID,
                {
                    "sourceAssetRelativePath": asset.relative_path,
                    "drawingMode": "lightweight",
                },
            )
            result = self.confirm_until_terminal(engine, engine.run(job.job_id))
            self.assertEqual(
                "completed",
                result.job.status,
                result.job.error.to_dict() if result.job.error else result.job.to_dict(),
            )
            evidence = engine.evidence_store.get(result.job.evidence_id or "missing")

            exact_svg = (
                root / "artifacts" / project.project_id / job.job_id / "exact" / "vector.svg"
            )
            drawing_svg = (
                root / "artifacts" / project.project_id / job.job_id / "lightweight" / "vector.svg"
            )

            self.assertTrue(exact_svg.is_file())
            self.assertTrue(drawing_svg.is_file())
            self.assertNotIn("<image", exact_svg.read_text(encoding="utf-8").lower())
            self.assertGreaterEqual(len(result.job.artifacts), 10)
            self.assertEqual(
                [
                    "vectorization",
                    "vectorization",
                    "vectorization",
                    "vectorization",
                    "vectorization",
                    "user-review",
                    "local-delivery",
                ],
                [step["adapter"] for step in evidence["steps"]],
            )
            self.assertNotIn(str(root), str(result.job.to_dict()))

    def test_real_small_image_completes_exact_only_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, project, asset = self.create_runtime(root)
            job = engine.create_job(
                project.project_id,
                WORKFLOW_ID,
                {
                    "sourceAssetRelativePath": asset.relative_path,
                    "drawingMode": "exact",
                    "parameters": {"exact": {"maxDimension": 512, "maxSvgSizeMb": 64}},
                },
            )
            result = self.confirm_until_terminal(engine, engine.run(job.job_id))
            self.assertEqual(
                "completed",
                result.job.status,
                result.job.error.to_dict() if result.job.error else result.job.to_dict(),
            )
            evidence = engine.evidence_store.get(result.job.evidence_id or "missing")
            artifact_root = root / "artifacts" / project.project_id / job.job_id
            exact_svg = artifact_root / "exact" / "vector.svg"

            self.assertTrue(exact_svg.is_file())
            self.assertNotIn("<image", exact_svg.read_text(encoding="utf-8").lower())
            self.assertFalse((artifact_root / "artisan").exists())
            self.assertFalse((artifact_root / "smart").exists())
            self.assertFalse((artifact_root / "lightweight").exists())
            self.assertEqual(
                [
                    "vectorization",
                    "vectorization",
                    "vectorization",
                    "user-review",
                    "local-delivery",
                ],
                [step["adapter"] for step in evidence["steps"]],
            )
            self.assertNotIn(str(root), str(result.job.to_dict()))

    def test_exact_failure_stops_without_drawing_or_image_trace_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, project, asset = self.create_runtime(root)
            job = engine.create_job(
                project.project_id,
                WORKFLOW_ID,
                {
                    "sourceAssetRelativePath": asset.relative_path,
                    "drawingMode": "artisan",
                },
            )
            paused = engine.run(job.job_id)
            assert paused.approval is not None
            with patch(
                "starbridge_mcp.adapters.vectorization.adapter.run_vectorization",
                side_effect=VectorizationError("vector_too_complex", "精确重建超限。"),
            ):
                failed = engine.run(
                    job.job_id,
                    approval_ref=paused.approval.approval_ref,
                    confirm_execute=True,
                )

            drawing_directory = root / "artifacts" / project.project_id / job.job_id / "artisan"

        self.assertEqual("failed", failed.job.status)
        self.assertEqual("vector_too_complex", failed.job.error.code if failed.job.error else None)
        self.assertFalse(drawing_directory.exists())
        self.assertIn("不会自动回退到 Image Trace", str(failed.job.error.to_dict()))


if __name__ == "__main__":
    unittest.main()
