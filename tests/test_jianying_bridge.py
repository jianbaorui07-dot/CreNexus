import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.bridges import jianying


class JianyingBridgeTests(unittest.TestCase):
    def assert_schema(self, result, action):
        self.assertIsInstance(result, dict)
        self.assertEqual(result["bridge"], "jianying")
        self.assertEqual(result["action"], action)
        for key in ("ok", "message", "details", "warnings", "next_steps"):
            self.assertIn(key, result)

    def test_status_schema_without_real_draft_env(self):
        result = jianying.status()
        self.assert_schema(result, "status")
        self.assertIn("draft_env", result["details"])

    def test_validate_draft_schema_rejects_empty(self):
        result = jianying.validate_draft_schema({})
        self.assert_schema(result, "validate_draft_schema")
        self.assertFalse(result["ok"])

    def test_create_draft_plan_from_minimal_spec(self):
        spec = {
            "name": "safe_test",
            "duration_ms": 1000,
            "clips": [{"source": "<placeholder>", "start_ms": 0, "duration_ms": 1000}],
            "texts": [],
            "audio": [],
            "subtitles": [],
        }
        result = jianying.create_draft_plan(spec)
        self.assert_schema(result, "create_draft_plan")
        self.assertTrue(result["ok"])
        plan = result["details"]["plan"]
        self.assertTrue(plan["safe_plan"])
        self.assertFalse(plan["draft"]["writes_real_draft"])

    def test_create_draft_plan_rejects_non_list_tracks(self):
        result = jianying.create_draft_plan({"clips": "not-a-list"})
        self.assert_schema(result, "create_draft_plan")
        self.assertFalse(result["ok"])

    def test_export_draft_plan_refuses_unsafe_path(self):
        created = jianying.create_draft_plan({"clips": [], "texts": [], "audio": [], "subtitles": []})
        unsafe_path = Path(tempfile.gettempdir()) / "starbridge_unsafe_draft_plan.json"
        result = jianying.export_draft_plan(created["details"]["plan"], unsafe_path)
        self.assert_schema(result, "export_draft_plan")
        self.assertFalse(result["ok"])
        self.assertFalse(unsafe_path.exists())

    def test_export_draft_plan_allows_examples_output(self):
        created = jianying.create_draft_plan({"clips": [], "texts": [], "audio": [], "subtitles": []})
        output_path = Path("examples") / "jianying" / "output" / "test_draft_plan.json"
        result = jianying.export_draft_plan(created["details"]["plan"], output_path)
        self.assert_schema(result, "export_draft_plan")
        self.assertTrue(result["ok"])
        self.assertTrue(output_path.exists())
        exported = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertTrue(exported["safe_plan"])
        output_path.unlink()


if __name__ == "__main__":
    unittest.main()
