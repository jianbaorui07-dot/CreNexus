from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from starbridge_mcp.backend import StarBridgeBackend


class BackendProjectsWorkflowTests(unittest.TestCase):
    def test_photoshop_project_creates_a_fixed_redacted_job_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = StarBridgeBackend(app_data_dir=root / "app-data")
            source = root / "customer-input.png"
            Image.new("RGB", (24, 24), (80, 120, 160)).save(source)
            workflows = backend.route("GET", "/api/workflows")
            photoshop = next(
                item
                for item in workflows.body["data"]["workflows"]
                if item["workflowId"] == "photoshop-production-v1"
            )
            self.assertEqual("experimental", photoshop["capabilityStatus"])
            self.assertTrue(photoshop["requiresConfirmation"])

            created = backend.route(
                "POST",
                "/api/projects",
                json.dumps(
                    {
                        "projectName": "Photoshop 安全副本",
                        "workflowId": "photoshop-production-v1",
                    }
                ).encode("utf-8"),
            )
            project_id = created.body["data"]["projectId"]
            imported = backend.route(
                "POST",
                f"/api/projects/{project_id}/assets",
                json.dumps({"inputPath": str(source), "confirmImport": True}).encode("utf-8"),
            )
            asset_id = imported.body["data"]["asset"]["assetId"]
            job = backend.route(
                "POST",
                "/api/jobs",
                json.dumps(
                    {
                        "projectId": project_id,
                        "workflowId": "photoshop-production-v1",
                        "sourceAssetId": asset_id,
                        "outputFormats": ["png", "jpeg", "psd"],
                        "resizeCanvas": True,
                        "canvasWidth": 1080,
                        "canvasHeight": 1080,
                        "brightness": 5,
                        "contrast": 3,
                        "saturation": 4,
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(201, job.status)
            plan_file = next((root / "app-data" / "jobs").rglob("plan.json"))
            plan_text = plan_file.read_text(encoding="utf-8")

        self.assertNotIn(str(root), plan_text)
        self.assertNotIn("customer-input.png", plan_text)
        self.assertNotIn("descriptor", plan_text.lower())
        self.assertIn('"execute-production"', plan_text)

    def test_comfyui_job_plan_does_not_persist_prompt_or_model_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = StarBridgeBackend(app_data_dir=root / "app-data")
            workflows = backend.route("GET", "/api/workflows")
            workflow_ids = {item["workflowId"] for item in workflows.body["data"]["workflows"]}
            self.assertIn("comfyui-generation-v1", workflow_ids)

            created = backend.route(
                "POST",
                "/api/projects",
                json.dumps(
                    {
                        "projectName": "本机生成项目",
                        "workflowId": "comfyui-generation-v1",
                    }
                ).encode("utf-8"),
            )
            project_id = created.body["data"]["projectId"]
            private_prompt = "private customer launch visual"
            private_model = "private-checkpoint.safetensors"
            created_job = backend.route(
                "POST",
                "/api/jobs",
                json.dumps(
                    {
                        "projectId": project_id,
                        "workflowId": "comfyui-generation-v1",
                        "prompt": private_prompt,
                        "checkpointName": private_model,
                        "width": 512,
                        "height": 512,
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(201, created_job.status)
            persisted = "\n".join(
                path.read_text(encoding="utf-8") for path in (root / "app-data").rglob("*.json")
            )

        self.assertNotIn(private_prompt, persisted)
        self.assertNotIn(private_model, persisted)

    def test_project_asset_job_and_delivery_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = StarBridgeBackend(app_data_dir=root / "app-data")
            source = root / "selected-source.png"
            image = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
            image.paste((0, 255, 0, 255), (16, 0, 32, 16))
            image.paste((0, 0, 255, 255), (0, 16, 16, 32))
            image.paste((255, 255, 0, 255), (16, 16, 32, 32))
            image.save(source)

            workflows = backend.route("GET", "/api/workflows")
            self.assertEqual(200, workflows.status)
            self.assertFalse(workflows.body["data"]["workflows"][0]["imageTraceFallback"])

            created = backend.route(
                "POST",
                "/api/projects",
                json.dumps(
                    {
                        "projectName": "测试交付项目",
                        "workflowId": "vector-delivery-v1",
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(201, created.status)
            project_id = created.body["data"]["projectId"]

            rejected = backend.route(
                "POST",
                f"/api/projects/{project_id}/assets",
                json.dumps({"inputPath": str(source)}).encode("utf-8"),
            )
            self.assertEqual(400, rejected.status)
            self.assertEqual("confirmation_required", rejected.body["error"]["code"])

            imported = backend.route(
                "POST",
                f"/api/projects/{project_id}/assets",
                json.dumps({"inputPath": str(source), "confirmImport": True}).encode("utf-8"),
            )
            self.assertEqual(201, imported.status)
            asset = imported.body["data"]["asset"]
            self.assertNotIn(str(root), str(imported.body))

            created_job = backend.route(
                "POST",
                "/api/jobs",
                json.dumps(
                    {
                        "projectId": project_id,
                        "workflowId": "vector-delivery-v1",
                        "sourceAssetId": asset["assetId"],
                        "drawingMode": "lightweight",
                    }
                ).encode("utf-8"),
            )
            self.assertEqual(201, created_job.status)
            job_id = created_job.body["data"]["jobId"]

            result = backend.route("POST", f"/api/jobs/{job_id}/run", b"{}")
            for _ in range(8):
                if result.body["data"]["job"]["status"] != "needs_user":
                    break
                approval = result.body["data"]["approval"]
                result = backend.route(
                    "POST",
                    f"/api/jobs/{job_id}/run",
                    json.dumps(
                        {
                            "approvalRef": approval["approvalRef"],
                            "confirmExecute": True,
                        }
                    ).encode("utf-8"),
                )

            self.assertEqual("completed", result.body["data"]["job"]["status"])
            events = backend.route("GET", f"/api/jobs/{job_id}/events")
            delivery = backend.route("GET", f"/api/projects/{project_id}/delivery")
            self.assertGreater(events.body["data"]["eventCount"], 6)
            self.assertIn("SVG", delivery.body["data"]["formats"])
            self.assertFalse(delivery.body["data"]["fabricatedOutputs"])
            self.assertNotIn(str(root), str(delivery.body))

            reloaded = StarBridgeBackend(app_data_dir=root / "app-data")
            persisted_job = reloaded.route("GET", f"/api/jobs/{job_id}")
            persisted_project = reloaded.route("GET", f"/api/projects/{project_id}")

        self.assertEqual("completed", persisted_job.body["data"]["status"])
        self.assertEqual(project_id, persisted_project.body["data"]["projectId"])

    def test_legacy_vector_job_shape_projects_into_generic_task_center(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = StarBridgeBackend(app_data_dir=Path(directory) / "app-data")
            legacy = {
                "job_id": "vector-1",
                "status": "queued",
                "progress": 1,
                "stage": "准备",
                "mode": "smart",
                "created_at": "2026-07-18T00:00:00Z",
            }
            public = backend._vector_job_public(legacy)

        for field in (
            "jobId",
            "projectId",
            "workflowId",
            "status",
            "currentStep",
            "progress",
            "artifacts",
            "warnings",
            "evidenceId",
        ):
            self.assertIn(field, public)


if __name__ == "__main__":
    unittest.main()
