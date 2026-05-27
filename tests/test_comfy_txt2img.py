from __future__ import annotations

import copy
import unittest

from examples.comfy_bridge import run_txt2img


class ComfyTxt2ImgWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = run_txt2img.load_workflow(run_txt2img.WORKFLOW_PATH)

    def test_bundled_workflow_passes_node_validation(self) -> None:
        run_txt2img.validate_workflow(self.workflow)

    def test_missing_node_returns_structured_error(self) -> None:
        workflow = copy.deepcopy(self.workflow)
        workflow.pop("3")

        with self.assertRaises(run_txt2img.BridgeError) as context:
            run_txt2img.validate_workflow(workflow)

        payload = context.exception.to_payload()
        self.assertFalse(payload["ok"])
        self.assertEqual("missing_node", payload["error"])

    def test_wrong_class_type_returns_structured_error(self) -> None:
        workflow = copy.deepcopy(self.workflow)
        workflow["3"]["class_type"] = "CLIPTextEncode"

        with self.assertRaises(run_txt2img.BridgeError) as context:
            run_txt2img.validate_workflow(workflow)

        self.assertEqual("invalid_node_class", context.exception.to_payload()["error"])

    def test_checkpoint_must_be_explicit_without_opt_in(self) -> None:
        args = run_txt2img.parse_args(["--prompt", "demo"])

        with self.assertRaises(run_txt2img.BridgeError) as context:
            run_txt2img.resolve_checkpoint(args, ["demo.safetensors"])

        self.assertEqual("missing_checkpoint", context.exception.to_payload()["error"])

    def test_missing_prompt_is_json_error(self) -> None:
        with self.assertRaises(run_txt2img.BridgeError) as context:
            run_txt2img.parse_args([])

        self.assertEqual("invalid_arguments", context.exception.to_payload()["error"])

    def test_build_prompt_applies_cli_parameters(self) -> None:
        args = run_txt2img.parse_args(
            [
                "--prompt",
                "demo",
                "--ckpt",
                "demo.safetensors",
                "--seed",
                "123",
                "--steps",
                "24",
                "--cfg",
                "6.5",
                "--sampler",
                "dpmpp_2m",
                "--scheduler",
                "karras",
                "--width",
                "640",
                "--height",
                "768",
            ]
        )

        prompt, seed = run_txt2img.build_prompt(args, self.workflow, "demo.safetensors")

        self.assertEqual(123, seed)
        self.assertEqual("demo.safetensors", prompt["4"]["inputs"]["ckpt_name"])
        self.assertEqual(640, prompt["5"]["inputs"]["width"])
        self.assertEqual(768, prompt["5"]["inputs"]["height"])
        self.assertEqual(24, prompt["3"]["inputs"]["steps"])
        self.assertEqual(6.5, prompt["3"]["inputs"]["cfg"])
        self.assertEqual("dpmpp_2m", prompt["3"]["inputs"]["sampler_name"])
        self.assertEqual("karras", prompt["3"]["inputs"]["scheduler"])


if __name__ == "__main__":
    unittest.main()
