from __future__ import annotations

import copy
import unittest

from examples.comfy_bridge.workflow_agent import workflow_build, workflow_repair


class ComfyWorkflowRepairTests(unittest.TestCase):
    def test_missing_nodes_and_bad_values_are_repaired(self) -> None:
        built = workflow_build(
            {"goal": "国风 Q版 明代街市", "checkpoint": "placeholder.safetensors"}
        )
        broken = copy.deepcopy(built["workflow"])

        broken.pop("5")
        broken.pop("9")
        broken["6"]["inputs"]["text"] = ""
        broken["7"]["inputs"]["text"] = ""
        broken["3"]["inputs"]["steps"] = "bad"
        broken["3"]["inputs"]["cfg"] = "bad"
        broken["3"]["inputs"]["seed"] = "bad"
        broken["3"]["inputs"]["positive"] = ["missing", 0]

        result = workflow_repair(
            {
                "workflow": broken,
                "goal": "生成一张国风 Q版 明代街市人物场景图",
                "width": -1,
                "height": 99999,
                "checkpoint": "placeholder.safetensors",
            }
        )

        repaired = result["workflow"]
        self.assertTrue(result["ok"])
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual("EmptyLatentImage", repaired["5"]["class_type"])
        self.assertEqual("SaveImage", repaired["9"]["class_type"])
        self.assertTrue(repaired["6"]["inputs"]["text"])
        self.assertTrue(repaired["7"]["inputs"]["text"])
        self.assertIsInstance(repaired["3"]["inputs"]["steps"], int)
        self.assertIsInstance(repaired["3"]["inputs"]["cfg"], float)
        self.assertIsInstance(repaired["3"]["inputs"]["seed"], int)
        self.assertEqual(["6", 0], repaired["3"]["inputs"]["positive"])
        self.assertGreaterEqual(repaired["5"]["inputs"]["width"], 64)
        self.assertLessEqual(repaired["5"]["inputs"]["height"], 4096)


if __name__ == "__main__":
    unittest.main()
