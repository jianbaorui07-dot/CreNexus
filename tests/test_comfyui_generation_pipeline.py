from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from starbridge_mcp.adapters.base import AdapterContext, CancellationToken
from starbridge_mcp.adapters.comfyui import ComfyUiAdapter, RuntimeInputVault
from starbridge_mcp.adapters.comfyui.adapter import _validate_generated_image_payload
from starbridge_mcp.core.app_data import resolve_app_data_paths
from starbridge_mcp.domain.models import WorkflowStep
from starbridge_mcp.storage.atomic_json import atomic_write_json
from starbridge_mcp.storage.evidence_store import EvidenceStore
from starbridge_mcp.storage.job_store import JobStore
from starbridge_mcp.storage.project_store import ProjectStore
from starbridge_mcp.workflows.comfyui_generation_pipeline import (
    WORKFLOW_ID,
    create_comfyui_generation_factory,
    register_comfyui_generation_workflow,
)
from starbridge_mcp.workflows.engine import WorkflowEngine
from starbridge_mcp.workflows.registry import WorkflowRegistry

PRIVATE_PROMPT = "private customer concept for launch"
PRIVATE_MODEL = "private-model.safetensors"


def job_inputs() -> dict[str, object]:
    return {
        "prompt": PRIVATE_PROMPT,
        "negativePrompt": "private negative",
        "checkpointName": PRIVATE_MODEL,
        "width": 512,
        "height": 512,
        "steps": 12,
        "cfg": 6.5,
        "sampler": "dpmpp_2m",
        "scheduler": "karras",
        "waitSeconds": 0,
    }


class ComfyUiGenerationPipelineTests(unittest.TestCase):
    def test_plan_keeps_prompt_model_and_workflow_out_of_persistence(self) -> None:
        vault = RuntimeInputVault()
        plan = create_comfyui_generation_factory(vault)(job_inputs())
        serialized = json.dumps(plan.to_dict(), ensure_ascii=False)

        self.assertNotIn(PRIVATE_PROMPT, serialized)
        self.assertNotIn(PRIVATE_MODEL, serialized)
        self.assertNotIn("CLIPTextEncode", serialized)
        self.assertIn("promptPersisted", serialized)
        self.assertTrue(plan.steps[2].requires_confirmation)
        self.assertTrue(plan.steps[4].requires_confirmation)

    def test_confirmed_loopback_run_registers_real_bytes_and_redacted_evidence(self) -> None:
        calls: list[dict[str, object]] = []
        result_reads = 0

        def fake_agent(arguments: dict[str, object]) -> dict[str, object]:
            calls.append(arguments)
            if not arguments.get("confirm_run"):
                return {
                    "ok": True,
                    "validation": {"ok": True},
                    "workflow_hash": "b" * 64,
                    "warnings": [],
                }
            return {
                "ok": True,
                "submitted": True,
                "prompt_id": "prompt-test",
                "job_status": {"state": "completed"},
                "warnings": [],
            }

        def fake_result(_arguments: dict[str, object]) -> dict[str, object]:
            nonlocal result_reads
            result_reads += 1
            if result_reads == 1:
                return {
                    "ok": True,
                    "state": "queued_or_running",
                    "terminal": False,
                    "result_ready": False,
                    "output_manifest": {"image_count": 0, "images": []},
                }
            return {
                "ok": True,
                "state": "completed",
                "terminal": True,
                "result_ready": True,
                "output_manifest": {
                    "image_count": 1,
                    "images": [
                        {
                            "asset_id": "asset_test",
                            "filename": "generated.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ],
                },
            }

        image_buffer = io.BytesIO()
        Image.new("RGB", (8, 8), (12, 34, 56)).save(image_buffer, format="PNG")
        output_bytes = image_buffer.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = resolve_app_data_paths(root)
            projects = ProjectStore(paths.projects)
            jobs = JobStore(paths.jobs)
            evidence_store = EvidenceStore(paths.evidence)
            vault = RuntimeInputVault()
            adapter = ComfyUiAdapter(
                vault,
                probe_runner=lambda _url, _timeout: {
                    "ok": True,
                    "detected": {
                        "system_stats": True,
                        "object_info": True,
                        "basic_nodes_checked": ["KSampler", "SaveImage"],
                    },
                },
                agent_runner=fake_agent,
                result_reader=fake_result,
                output_fetcher=lambda _url, _image, _timeout: output_bytes,
            )
            registry = WorkflowRegistry()
            register_comfyui_generation_workflow(registry, adapter=adapter, vault=vault)
            engine = WorkflowEngine(
                registry=registry,
                project_store=projects,
                job_store=jobs,
                evidence_store=evidence_store,
                app_paths=paths,
            )
            project = projects.create("ComfyUI 测试", WORKFLOW_ID)
            job = engine.create_job(project.project_id, WORKFLOW_ID, job_inputs())

            first_pause = engine.run(job.job_id)
            assert first_pause.approval is not None
            self.assertEqual("submit-generation", first_pause.approval.step_id)
            pending = engine.run(
                job.job_id,
                approval_ref=first_pause.approval.approval_ref,
                confirm_execute=True,
            )
            self.assertEqual("needs_user", pending.job.status)
            self.assertIsNone(pending.approval)
            second_pause = engine.run(job.job_id)
            assert second_pause.approval is not None
            self.assertEqual("review-result", second_pause.approval.step_id)
            completed = engine.run(
                job.job_id,
                approval_ref=second_pause.approval.approval_ref,
                confirm_execute=True,
            )
            evidence = evidence_store.get(completed.job.evidence_id or "missing")
            plan_text = jobs.plan_file(job.job_id).read_text(encoding="utf-8")
            evidence_text = json.dumps(evidence, ensure_ascii=False)
            artifact_path = root / completed.job.artifacts[0].relative_path
            artifact_bytes = artifact_path.read_bytes()

        self.assertEqual("completed", completed.job.status)
        self.assertEqual(output_bytes, artifact_bytes)
        self.assertEqual("generated.png", completed.job.artifacts[0].basename)
        self.assertNotIn(PRIVATE_PROMPT, plan_text)
        self.assertNotIn(PRIVATE_MODEL, plan_text)
        self.assertNotIn(PRIVATE_PROMPT, evidence_text)
        self.assertNotIn(PRIVATE_MODEL, evidence_text)
        self.assertEqual([False, True], [bool(call.get("confirm_run")) for call in calls])

    def test_output_validation_accepts_supported_images_and_rejects_spoofs(self) -> None:
        encoded: dict[str, bytes] = {}
        for image_format, basename in (
            ("PNG", "generated.png"),
            ("JPEG", "generated.jpg"),
            ("WEBP", "generated.webp"),
            ("GIF", "generated.gif"),
        ):
            image_buffer = io.BytesIO()
            Image.new("RGB", (8, 8), (12, 34, 56)).save(image_buffer, format=image_format)
            encoded[image_format] = image_buffer.getvalue()
            _validate_generated_image_payload(basename, encoded[image_format])

        png_bytes = encoded["PNG"]
        invalid_outputs = (
            ("generated.png", b"<html>local error</html>"),
            ("generated.jpg", png_bytes),
            ("generated.png", png_bytes[:-12]),
            ("generated.bmp", b"BM" + bytes(30)),
        )
        for basename, payload in invalid_outputs:
            with self.subTest(basename=basename), self.assertRaises(ValueError):
                _validate_generated_image_payload(basename, payload)

    def test_multi_output_failure_removes_files_written_by_the_same_batch(self) -> None:
        image_buffer = io.BytesIO()
        Image.new("RGB", (8, 8), (12, 34, 56)).save(image_buffer, format="PNG")
        png_bytes = image_buffer.getvalue()
        fetch_count = 0

        def fetch_output(_base_url: str, _image: dict[str, object], _timeout: int) -> bytes:
            nonlocal fetch_count
            fetch_count += 1
            return png_bytes if fetch_count == 1 else b"<html>local error</html>"

        result_payload = {
            "ok": True,
            "state": "completed",
            "terminal": True,
            "result_ready": True,
            "output_manifest": {
                "image_count": 2,
                "images": [
                    {"filename": "first.png", "subfolder": "", "type": "output"},
                    {"filename": "second.png", "subfolder": "", "type": "output"},
                ],
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            paths = resolve_app_data_paths(Path(directory))
            adapter = ComfyUiAdapter(
                RuntimeInputVault(),
                result_reader=lambda _arguments: result_payload,
                output_fetcher=fetch_output,
            )
            context = AdapterContext(
                job_id="job-output-rollback",
                project_id="project-output-rollback",
                workflow_id=WORKFLOW_ID,
                step=WorkflowStep(
                    step_id="collect-results",
                    adapter="comfyui",
                    input_data={"operation": "collect-results"},
                ),
                app_paths=paths,
                cancellation=CancellationToken(),
            )
            atomic_write_json(
                adapter._state_path(context),
                {"schemaVersion": 1, "submitted": True, "promptId": "prompt-test"},
            )

            result = adapter.execute(context)
            artifact_files = [path for path in paths.artifacts.rglob("*") if path.is_file()]

        self.assertEqual(2, fetch_count)
        self.assertEqual("failed", result.status)
        self.assertEqual("comfyui_output_fetch_failed", result.error.code if result.error else None)
        self.assertEqual((), result.artifacts)
        self.assertEqual([], artifact_files)

    def test_unavailable_service_soft_fails_without_prompt_submission(self) -> None:
        submit_calls = 0

        def fake_agent(arguments: dict[str, object]) -> dict[str, object]:
            nonlocal submit_calls
            if arguments.get("confirm_run"):
                submit_calls += 1
            return {
                "ok": True,
                "validation": {"ok": True},
                "workflow_hash": "c" * 64,
                "warnings": [],
            }

        with tempfile.TemporaryDirectory() as directory:
            paths = resolve_app_data_paths(Path(directory))
            projects = ProjectStore(paths.projects)
            vault = RuntimeInputVault()
            registry = WorkflowRegistry()
            register_comfyui_generation_workflow(
                registry,
                adapter=ComfyUiAdapter(
                    vault,
                    probe_runner=lambda _url, _timeout: {"ok": False, "status": "unavailable"},
                    agent_runner=fake_agent,
                ),
                vault=vault,
            )
            engine = WorkflowEngine(
                registry=registry,
                project_store=projects,
                job_store=JobStore(paths.jobs),
                evidence_store=EvidenceStore(paths.evidence),
                app_paths=paths,
            )
            project = projects.create("离线 ComfyUI", WORKFLOW_ID)
            job = engine.create_job(project.project_id, WORKFLOW_ID, job_inputs())
            result = engine.run(job.job_id)

        self.assertEqual("failed", result.job.status)
        self.assertEqual("comfyui_unavailable", result.job.error.code if result.job.error else None)
        self.assertEqual(0, submit_calls)


if __name__ == "__main__":
    unittest.main()
