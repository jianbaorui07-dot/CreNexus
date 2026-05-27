from __future__ import annotations

import unittest

from starbridge_mcp.core.result_schema import REQUIRED_RESULT_FIELDS, make_result, validate_result
from starbridge_mcp.server import BRIDGE_PROFILES, normalize_legacy_status


class StarBridgeSchemaTests(unittest.TestCase):
    def test_make_result_contains_required_fields(self) -> None:
        result = make_result(ok=True, bridge="comfyui", action="status", message="ready")
        self.assertEqual(tuple(result.keys()), REQUIRED_RESULT_FIELDS)
        validate_result(result)

    def test_legacy_status_normalizes_to_schema(self) -> None:
        result = normalize_legacy_status(
            {
                "name": "ComfyUI",
                "label": "ComfyUI 图像生成桥",
                "status": "warn",
                "status_label": "需配置",
                "details": ["处理建议：先启动 ComfyUI。"],
                "data": {"base_url": "http://127.0.0.1:8188"},
            }
        )
        validate_result(result)
        self.assertFalse(result["ok"])
        self.assertEqual(result["bridge"], "comfyui")
        self.assertEqual(result["action"], "status")
        self.assertEqual(result["details"]["probe_type"], "HTTP read-only probe")
        self.assertIn("status", result["details"]["current_actions"])
        self.assertIn("probe", result["details"]["current_actions"])
        self.assertTrue(result["next_steps"])

    def test_all_bridge_profiles_are_normalized_to_schema(self) -> None:
        legacy_names = {
            "ComfyUI": "comfyui",
            "Photoshop": "photoshop",
            "Illustrator": "illustrator",
            "Blender": "blender",
            "CAD": "autocad",
            "JianyingCapCut": "jianying_capcut",
        }
        self.assertTrue(set(legacy_names.values()).issubset(set(BRIDGE_PROFILES)))
        self.assertIn("autocad_dxf", BRIDGE_PROFILES)
        for legacy_name, bridge_id in legacy_names.items():
            with self.subTest(bridge=bridge_id):
                result = normalize_legacy_status(
                    {
                        "name": legacy_name,
                        "label": legacy_name,
                        "status": "warn",
                        "status_label": "需配置",
                        "details": ["处理建议：配置本机环境。"],
                        "data": {},
                    }
                )
                validate_result(result)
                self.assertEqual(result["bridge"], bridge_id)
                self.assertIn("required_env", result["details"])
                self.assertIn("ready_when", result["details"])
                self.assertIn("safety_boundary", result["details"])
                self.assertIn("probe", result["details"]["current_actions"])


if __name__ == "__main__":
    unittest.main()
