from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from examples.comfy_bridge.validate_workflow import (
    DEFAULT_WORKFLOW,
    detect_workflow_format,
    validate_workflow_file,
    validate_workflow_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")
VISUAL_WORKFLOW = REPO_ROOT / "examples" / "comfy_bridge" / "workflows" / "txt2img_basic_visual.json"


class ComfyWorkflowValidateTests(unittest.TestCase):
    def assert_no_private_paths(self, text: str) -> None:
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_api_workflow_validates(self) -> None:
        result = validate_workflow_file(DEFAULT_WORKFLOW)
        self.assertTrue(result["ok"])
        self.assertEqual("workflow_validate", result["action"])
        self.assertEqual("api", result["details"]["format"])
        self.assertGreater(result["details"]["node_count"], 0)
        self.assertIn("KSampler", result["details"]["class_types"])

    def test_visual_workflow_is_detected_but_not_api_submittable(self) -> None:
        result = validate_workflow_file(VISUAL_WORKFLOW)
        self.assertFalse(result["ok"])
        self.assertEqual("visual", result["details"]["format"])
        self.assertTrue(result["next_steps"])

    def test_broken_api_link_is_reported(self) -> None:
        workflow = json.loads(DEFAULT_WORKFLOW.read_text(encoding="utf-8"))
        broken = copy.deepcopy(workflow)
        broken["3"]["inputs"]["model"] = ["missing-node", 0]

        result = validate_workflow_payload(broken, workflow_name="broken.json")

        self.assertFalse(result["ok"])
        self.assertTrue(any("missing-node" in error for error in result["details"]["errors"]))

    def test_format_detector_rejects_non_object(self) -> None:
        self.assertEqual("invalid", detect_workflow_format([]))

    def test_cli_output_is_json_and_safe(self) -> None:
        completed = subprocess.run(
            [sys.executable, "examples\\comfy_bridge\\validate_workflow.py", "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assert_no_private_paths(completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
