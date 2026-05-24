import json
import unittest
from unittest.mock import patch

from starbridge_mcp.bridges import comfyui


class ComfyUIBridgeTests(unittest.TestCase):
    def assert_schema(self, result, action):
        self.assertIsInstance(result, dict)
        self.assertEqual(result["bridge"], "comfyui")
        self.assertEqual(result["action"], action)
        for key in ("ok", "message", "details", "warnings", "next_steps"):
            self.assertIn(key, result)

    def test_status_schema_when_service_may_be_missing(self):
        result = comfyui.status()
        self.assert_schema(result, "status")
        self.assertIn("url", result["details"])

    def test_probe_schema_when_service_may_be_missing(self):
        result = comfyui.probe()
        self.assert_schema(result, "probe")

    def test_validate_workflow_rejects_empty_dict(self):
        result = comfyui.validate_workflow({})
        self.assert_schema(result, "validate_workflow")
        self.assertFalse(result["ok"])

    def test_validate_workflow_rejects_invalid_json(self):
        result = comfyui.validate_workflow("{not valid json")
        self.assert_schema(result, "validate_workflow")
        self.assertFalse(result["ok"])

    def test_validate_workflow_accepts_minimal_api_workflow(self):
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "PLACEHOLDER"}},
            "2": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
        }
        result = comfyui.validate_workflow(workflow)
        self.assert_schema(result, "validate_workflow")
        self.assertTrue(result["ok"])
        self.assertEqual(result["details"]["format"], "api")

    def test_queue_workflow_dry_run_does_not_submit(self):
        workflow = {"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}}}
        result = comfyui.queue_workflow(json.dumps(workflow), dry_run=True)
        self.assert_schema(result, "queue_workflow")
        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["dry_run"])

    def test_queue_workflow_without_dry_run_requires_env_gate(self):
        workflow = {"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}}}
        with patch.dict("os.environ", {comfyui.ALLOW_QUEUE_ENV: ""}):
            result = comfyui.queue_workflow(workflow, dry_run=False)
        self.assert_schema(result, "queue_workflow")
        self.assertFalse(result["ok"])
        self.assertIn("disabled", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
