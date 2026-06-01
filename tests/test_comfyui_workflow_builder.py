from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from examples.comfy_bridge.validate_workflow import validate_workflow_file, validate_workflow_payload
from examples.comfy_bridge.workflow_agent import workflow_build, workflow_build_plan, workflow_compose, workflow_draft
from examples.comfy_bridge.workflow_template_registry import (
    REGISTRY_PATH,
    RECOGNIZED_COMPOSER_MODULES,
    compose_from_template,
    get_workflow_template,
    list_workflow_templates,
    validate_workflow_template,
    validate_workflow_template_registry,
)
from starbridge_mcp.mcp_server import handle_request


REPO_ROOT = Path(__file__).resolve().parents[1]


class ComfyWorkflowBuilderTests(unittest.TestCase):
    def test_goal_generates_workflow_build_plan(self) -> None:
        result = workflow_build_plan(
            {
                "goal": "生成一张国风 Q版 明代街市人物场景图",
                "workflow_type": "txt2img",
                "style": "Q版3D半动漫国风",
                "width": 1344,
                "height": 768,
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertEqual("txt2img", result["workflow_type"])
        self.assertIn("KSampler", result["required_nodes"])
        self.assertEqual("txt2img", result["task_type"])
        self.assertIn("input_requirements", result)
        self.assertIn("workflow_requirements", result)
        self.assertIn("safety_notes", result)
        self.assertIn("expected_outputs", result)
        self.assertIn("blocked_reasons", result)
        self.assertFalse(result["will_build"])

    def test_img2img_inpaint_and_upscale_generate_plan_only(self) -> None:
        for workflow_type in ("img2img", "inpaint", "upscale"):
            with self.subTest(workflow_type=workflow_type):
                result = workflow_build_plan({"goal": "安全测试计划", "workflow_type": workflow_type})

                self.assertTrue(result["ok"])
                self.assertEqual("dry_run", result["mode"])
                self.assertEqual(workflow_type, result["task_type"])
                self.assertFalse(result["will_submit"])
                self.assertTrue(result["blocked_reasons"])
                self.assertIn("input_requirements", result)
                self.assertIn("workflow_requirements", result)
                self.assertIn("safety_notes", result)
                self.assertIn("expected_outputs", result)

    def test_dry_run_plan_does_not_access_filesystem(self) -> None:
        with patch("builtins.open", side_effect=AssertionError("filesystem access blocked")):
            result = workflow_build_plan(
                {
                    "goal": "安全 img2img 计划",
                    "workflow_type": "img2img",
                    "source_image_path": "C:" + "\\Users" + "\\Someone" + "\\Pictures\\private.png",
                }
            )

        self.assertTrue(result["ok"])
        self.assertEqual("img2img", result["task_type"])
        self.assertFalse(result["will_submit"])

    def test_non_txt2img_build_returns_plan_without_workflow(self) -> None:
        result = workflow_build({"goal": "安全 upscale 计划", "workflow_type": "upscale"})

        self.assertFalse(result["ok"])
        self.assertEqual("upscale", result["task_type"])
        self.assertIsNone(result["workflow"])
        self.assertIn("build_plan", result)

    def test_workflow_build_outputs_valid_json_hash_and_summary(self) -> None:
        result = workflow_build(
            {
                "goal": "生成一张国风 Q版 明代街市人物场景图",
                "style": "Q版3D半动漫国风",
                "width": 1344,
                "height": 768,
                "checkpoint": "model-placeholder.safetensors",
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertEqual(64, len(result["workflow_hash"]))
        self.assertIn("workflow", result)
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual(7, result["node_summary"]["node_count"])
        self.assertEqual("CheckpointLoaderSimple", result["workflow"]["4"]["class_type"])
        self.assertEqual(1344, result["workflow"]["5"]["inputs"]["width"])
        self.assertEqual(768, result["workflow"]["5"]["inputs"]["height"])

    def test_workflow_draft_all_task_types_validate(self) -> None:
        for task_type in ("txt2img", "img2img", "inpaint", "upscale"):
            with self.subTest(task_type=task_type):
                result = workflow_draft(
                    {
                        "task_type": task_type,
                        "prompt": "public placeholder prompt",
                        "negative_prompt": "low quality",
                        "width": 768,
                        "height": 512,
                        "seed": 42,
                        "steps": 12,
                        "cfg": 6.5,
                        "sampler": "euler",
                        "scheduler": "normal",
                    }
                )

                self.assertTrue(result["valid"], result["validation_report"])
                self.assertTrue(result["validation_report"]["ok"])
                self.assertEqual(task_type, result["task_type"])
                self.assertIn("workflow", result)
                self.assertEqual("StarBridgeDraftMetadata", result["workflow"]["1"]["class_type"])
                self.assertFalse(result["workflow"]["1"]["inputs"]["production_ready"])

    def test_workflow_draft_replaces_real_paths_and_checkpoint_filenames(self) -> None:
        private_root = "C:" + "\\Users" + "\\RealUser"
        result = workflow_draft(
            {
                "task_type": "img2img",
                "prompt": "public placeholder prompt",
                "checkpoint": private_root + "\\ComfyUI\\models\\checkpoints\\private-model." + "ckpt",
                "source_image_path": private_root + "\\Pictures\\private-source.png",
            }
        )
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["valid"])
        self.assertNotIn("RealUser", encoded)
        self.assertNotIn("private-model", encoded)
        self.assertNotIn(".ckpt", encoded.lower())
        self.assertNotIn("Pictures", encoded)
        self.assertEqual("__checkpoint_placeholder__", result["workflow"]["2"]["inputs"]["ckpt_name"])

    def test_workflow_draft_does_not_submit_or_access_filesystem_or_network(self) -> None:
        with patch("builtins.open", side_effect=AssertionError("filesystem access blocked")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("network access blocked")
        ), patch("examples.comfy_bridge.workflow_agent.submit_workflow", side_effect=AssertionError("submit blocked")):
            result = workflow_draft({"task_type": "inpaint", "prompt": "public placeholder prompt"})

        self.assertTrue(result["valid"])
        self.assertEqual("dry_run", result["mode"])

    def test_mcp_workflow_draft_tool_schema_and_call(self) -> None:
        listed = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert listed is not None
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        self.assertIn("comfy.workflow_draft", tools)
        self.assertIn("task_type", tools["comfy.workflow_draft"]["inputSchema"]["properties"])

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "comfy.workflow_draft",
                    "arguments": {"task_type": "upscale", "prompt": "public placeholder prompt"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["valid"])
        self.assertFalse(payload["workflow"]["1"]["inputs"]["production_ready"])

    def test_public_draft_workflow_examples_validate(self) -> None:
        for filename in (
            "txt2img_draft_workflow.example.json",
            "img2img_draft_workflow.example.json",
            "inpaint_draft_workflow.example.json",
            "upscale_draft_workflow.example.json",
        ):
            with self.subTest(filename=filename):
                result = validate_workflow_file(REPO_ROOT / "examples" / "comfy_bridge" / "workflows" / filename)

                self.assertTrue(result["ok"], result["details"])
                self.assertTrue(result["details"]["valid"])

    def test_workflow_compose_all_task_types_validate_and_have_unique_nodes(self) -> None:
        for task_type in ("txt2img", "img2img", "inpaint", "upscale"):
            with self.subTest(task_type=task_type):
                result = workflow_compose(
                    {
                        "task_type": task_type,
                        "prompt": "public placeholder prompt",
                        "negative_prompt": "low quality",
                        "width": 768,
                        "height": 512,
                        "seed": 42,
                        "steps": 12,
                        "cfg": 6.5,
                        "sampler": "euler",
                        "scheduler": "normal",
                        "scale": 2.0,
                    }
                )

                self.assertTrue(result["valid"], result["validation_report"])
                self.assertTrue(result["validation_report"]["ok"])
                self.assertEqual(task_type, result["task_type"])
                node_ids = list(result["workflow"])
                self.assertEqual(len(node_ids), len(set(node_ids)))
                metadata = result["workflow"]["1"]["inputs"]
                self.assertTrue(metadata["draft"])
                self.assertTrue(metadata["safe_placeholder"])

    def test_workflow_compose_has_expected_core_chains(self) -> None:
        expectations = {
            "txt2img": {"CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage"},
            "img2img": {"LoadImage", "VAEEncode", "KSampler", "VAEDecode", "SaveImage"},
            "inpaint": {"LoadImage", "LoadImageMask", "VAEEncodeForInpaint", "KSampler", "VAEDecode", "SaveImage"},
            "upscale": {"LoadImage", "UpscaleModelLoader", "ImageUpscaleWithModel", "ImageScale", "SaveImage"},
        }
        for task_type, required_classes in expectations.items():
            with self.subTest(task_type=task_type):
                result = workflow_compose({"task_type": task_type, "prompt": "public placeholder prompt"})
                class_types = set(result["node_summary"]["class_types"])

                self.assertTrue(required_classes <= class_types)

    def test_workflow_compose_replaces_real_paths_and_checkpoint_filenames(self) -> None:
        private_root = "C:" + "\\Users" + "\\RealUser"
        result = workflow_compose(
            {
                "task_type": "txt2img",
                "prompt": "public placeholder prompt",
                "checkpoint": private_root + "\\ComfyUI\\models\\checkpoints\\private-model." + "ckpt",
            }
        )
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["valid"])
        self.assertNotIn("RealUser", encoded)
        self.assertNotIn("private-model", encoded)
        self.assertNotIn(".ckpt", encoded.lower())
        self.assertNotIn("C:" + "\\Users", encoded)
        self.assertEqual("__checkpoint_placeholder__", result["workflow"]["2"]["inputs"]["ckpt_name"])

    def test_workflow_compose_does_not_submit_or_access_filesystem_or_network(self) -> None:
        with patch("builtins.open", side_effect=AssertionError("filesystem access blocked")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("network access blocked")
        ), patch("examples.comfy_bridge.workflow_agent.submit_workflow", side_effect=AssertionError("submit blocked")):
            result = workflow_compose({"task_type": "img2img", "prompt": "public placeholder prompt"})

        self.assertTrue(result["valid"])
        self.assertEqual("dry_run", result["mode"])

    def test_mcp_workflow_compose_tool_schema_and_call(self) -> None:
        listed = handle_request({"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}})
        assert listed is not None
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        self.assertIn("comfy.workflow_compose", tools)
        self.assertIn("task_type", tools["comfy.workflow_compose"]["inputSchema"]["properties"])

        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "comfy.workflow_compose",
                    "arguments": {"task_type": "upscale", "prompt": "public placeholder prompt"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["valid"])
        self.assertTrue(payload["workflow"]["1"]["inputs"]["safe_placeholder"])

    def test_public_composed_workflow_examples_validate(self) -> None:
        for filename in (
            "txt2img_composed_workflow.example.json",
            "img2img_composed_workflow.example.json",
            "inpaint_composed_workflow.example.json",
            "upscale_composed_workflow.example.json",
            "complex_creative_poster_composed_workflow.example.json",
        ):
            with self.subTest(filename=filename):
                path = REPO_ROOT / "examples" / "comfy_bridge" / "workflows" / filename
                result = validate_workflow_file(path)
                workflow = json.loads(path.read_text(encoding="utf-8"))

                self.assertTrue(result["ok"], result["details"])
                self.assertTrue(result["details"]["valid"])
                self.assertEqual(len(workflow), len(set(workflow)))
                self.assertTrue(workflow["1"]["inputs"]["draft"] or workflow["1"]["inputs"]["safe_placeholder"])

    def test_workflow_template_registry_file_loads(self) -> None:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

        self.assertEqual("starbridge_comfy_workflow_template_registry", payload["registry_id"])
        self.assertEqual(5, len(payload["templates"]))

    def test_workflow_template_ids_are_unique(self) -> None:
        result = validate_workflow_template_registry()

        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["template_ids"]), len(set(result["template_ids"])))

    def test_workflow_template_required_modules_are_recognized(self) -> None:
        result = list_workflow_templates()

        self.assertTrue(result["ok"], result["registry_validation"])
        for template_report in result["registry_validation"]["templates"]:
            template = get_workflow_template(template_report["template_id"])["template"]
            modules = set(template["required_modules"])
            self.assertTrue(modules <= RECOGNIZED_COMPOSER_MODULES)

    def test_workflow_template_required_inputs_exist(self) -> None:
        result = validate_workflow_template_registry()

        self.assertTrue(result["ok"], result["errors"])
        for template_report in result["templates"]:
            self.assertFalse(
                any("required_inputs" in error for error in template_report["errors"]),
                template_report,
            )

    def test_workflow_template_lint_rejects_forbidden_patterns(self) -> None:
        private_root = "C:" + "\\Users" + "\\PrivateUser"
        template = {
            "template_id": "bad_private_template",
            "version": "1.0.0",
            "task_type": "txt2img",
            "required_modules": ["checkpoint_loader_placeholder"],
            "optional_modules": [],
            "required_inputs": ["prompt", "negative_prompt", "width", "height", "seed", "steps", "cfg", "sampler", "scheduler"],
            "safe_placeholder_policy": {
                "model_policy": "placeholder_only",
                "asset_policy": "placeholder_only_no_private_files",
                "queue_submission": "disabled",
                "network": "disabled",
                "filesystem": "no_private_files",
            },
            "validation_status": "composed_validated",
            "safety_level": "safe_placeholder_only",
            "notes": private_root + "\\ComfyUI\\models\\checkpoints\\private-model." + "ckpt",
        }

        result = validate_workflow_template(template)

        self.assertFalse(result["ok"])
        self.assertTrue(any("forbidden pattern" in error for error in result["errors"]))

    def test_compose_from_template_generates_valid_workflows(self) -> None:
        for template_id in (
            "txt2img_basic_v1",
            "img2img_basic_v1",
            "inpaint_basic_v1",
            "upscale_basic_v1",
            "creative_poster_complex_v1",
        ):
            with self.subTest(template_id=template_id):
                result = compose_from_template(template_id, {"prompt": "public placeholder prompt"})

                self.assertTrue(result["ok"], result["validation_report"])
                self.assertTrue(result["valid"])
                self.assertEqual(template_id, result["template_id"])
                self.assertIn("workflow", result)
                validation = validate_workflow_payload(result["workflow"], workflow_name=f"{template_id}.json")
                self.assertTrue(validation["ok"], validation["details"])
                self.assertFalse(result["workflow"]["1"]["inputs"]["production_ready"])
                self.assertEqual("disabled", result["workflow"]["1"]["inputs"]["queue_submission"])

    def test_workflow_template_examples_compose_and_validate(self) -> None:
        for filename in (
            "txt2img_from_template.example.json",
            "img2img_from_template.example.json",
            "inpaint_from_template.example.json",
            "upscale_from_template.example.json",
            "creative_poster_from_template.example.json",
        ):
            with self.subTest(filename=filename):
                path = REPO_ROOT / "examples" / "comfy_bridge" / "templates" / filename
                payload = json.loads(path.read_text(encoding="utf-8"))
                result = compose_from_template(payload["template_id"], payload.get("arguments") or {})

                self.assertTrue(result["ok"], result["validation_report"])
                self.assertTrue(validate_workflow_payload(result["workflow"], workflow_name=filename)["ok"])

    def test_mcp_workflow_template_tool_schema_and_calls(self) -> None:
        listed = handle_request({"jsonrpc": "2.0", "id": 21, "method": "tools/list", "params": {}})
        assert listed is not None
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertIn("comfy.workflow_template_list", tools)
        self.assertIn("comfy.workflow_template_get", tools)
        self.assertIn("comfy.workflow_from_template", tools)
        self.assertEqual("safe_read_only", tools["comfy.workflow_from_template"]["annotations"]["riskLevel"])

        list_response = handle_request(
            {"jsonrpc": "2.0", "id": 22, "method": "tools/call", "params": {"name": "comfy.workflow_template_list", "arguments": {}}}
        )
        assert list_response is not None
        self.assertTrue(list_response["result"]["structuredContent"]["ok"])

        get_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {"name": "comfy.workflow_template_get", "arguments": {"template_id": "txt2img_basic_v1"}},
            }
        )
        assert get_response is not None
        self.assertEqual("txt2img_basic_v1", get_response["result"]["structuredContent"]["template"]["template_id"])

        compose_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "tools/call",
                "params": {
                    "name": "comfy.workflow_from_template",
                    "arguments": {"template_id": "creative_poster_complex_v1", "arguments": {"prompt": "public placeholder poster"}},
                },
            }
        )
        assert compose_response is not None
        payload = compose_response["result"]["structuredContent"]
        self.assertTrue(payload["valid"], payload["validation_report"])
        self.assertEqual("creative_poster_complex_v1", payload["template_id"])

    def test_workflow_from_template_does_not_submit_or_use_network_or_private_filesystem(self) -> None:
        list_workflow_templates()
        with patch("builtins.open", side_effect=AssertionError("filesystem access blocked")), patch(
            "pathlib.Path.read_text", side_effect=AssertionError("filesystem access blocked")
        ), patch("urllib.request.urlopen", side_effect=AssertionError("network access blocked")), patch(
            "examples.comfy_bridge.workflow_agent.submit_workflow", side_effect=AssertionError("submit blocked")
        ):
            result = compose_from_template("img2img_basic_v1", {"prompt": "public placeholder prompt"})

        self.assertTrue(result["ok"], result["validation_report"])
        self.assertEqual("safe_read_only", result["mode"])
        self.assertIn("No private filesystem paths", " ".join(result["safety_notes"]))


if __name__ == "__main__":
    unittest.main()
