from __future__ import annotations

import json
import unittest

from starbridge_mcp.core.control_planner import build_control_plan
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request


class ControlPlannerTests(unittest.TestCase):
    def test_routes_common_codex_goals_to_each_software_bridge(self) -> None:
        cases = {
            "给商品图做 Photoshop 抠图和图层整理": "photoshop",
            "检查 Illustrator 矢量画板和 SVG 导出风险": "illustrator",
            "搭建 ComfyUI 文生图 workflow": "comfyui",
            "从公开尺寸生成 CAD 工程图和 DXF": "autocad_dxf",
            "规划 Blender 三维场景和渲染机位": "blender",
            "检查剪映视频字幕和时间线草稿结构": "jianying_capcut",
        }
        for goal, expected_bridge in cases.items():
            with self.subTest(bridge=expected_bridge):
                result = build_control_plan(goal=goal)
                self.assertEqual(expected_bridge, result["bridge"])
                self.assertTrue(result["dry_run"])
                self.assertFalse(result["safety_boundary"]["launches_software"])
                self.assertFalse(result["safety_boundary"]["writes_files"])

    def test_ambiguous_goal_requests_bridge_clarification(self) -> None:
        result = build_control_plan(goal="帮我优化这个设计")

        self.assertEqual("all", result["bridge"])
        self.assertTrue(result["needs_clarification"])
        self.assertGreaterEqual(len(result["bridge_options"]), 6)

    def test_guarded_candidate_is_opt_in_and_never_executed(self) -> None:
        default = build_control_plan(goal="Photoshop 抠图")
        expanded = build_control_plan(goal="Photoshop 抠图", include_guarded_candidates=True)

        self.assertNotIn(
            "confirmed_action_candidate", [phase["phase"] for phase in default["phases"]]
        )
        candidate = expanded["phases"][-1]
        self.assertEqual("confirmed_action_candidate", candidate["phase"])
        self.assertTrue(candidate["requires_confirmation"])
        self.assertEqual(["photoshop.recipe_run"], candidate["tools"])
        self.assertFalse(expanded["safety_boundary"]["writes_files"])

    def test_explicit_autocad_preference_uses_safe_headless_route(self) -> None:
        result = build_control_plan(goal="检查图纸规格", preferred_bridge="autocad")

        self.assertEqual("autocad_dxf", result["bridge"])
        self.assertEqual("autocad_dxf.create_dxf_plan", result["phases"][1]["tools"][0])

    def test_evidence_preview_is_bound_to_selected_software_recipe(self) -> None:
        result = build_control_plan(goal="用 Blender 规划三维场景")
        review = result["phases"][3]

        self.assertEqual(["starbridge.recipe_evidence"], review["tools"])
        self.assertEqual(
            "blender_scene_evidence",
            review["tool_arguments"]["starbridge.recipe_evidence"]["recipe_id"],
        )

        capcut = build_control_plan(goal="检查剪映视频草稿")
        self.assertEqual(["starbridge.evidence_init"], capcut["phases"][3]["tools"])

    def test_comfyui_route_includes_visual_review_before_evidence(self) -> None:
        result = build_control_plan(goal="搭建 ComfyUI 文生图 workflow")
        phases = [phase["phase"] for phase in result["phases"]]

        self.assertEqual(
            ["discover", "plan", "visual_review", "observe", "review"],
            phases,
        )
        self.assertEqual(["comfy.workflow_visualize"], result["phases"][2]["tools"])
        self.assertIn("comfyui.queue_snapshot", result["phases"][0]["tools"])
        self.assertFalse(result["phases"][0]["tool_arguments"]["comfyui.queue_snapshot"]["probe"])
        self.assertIn("queue_backpressure_reviewed", result["quality_gates"])

    def test_every_selected_route_includes_operation_context_observation(self) -> None:
        for bridge in (
            "photoshop",
            "illustrator",
            "comfyui",
            "autocad_dxf",
            "blender",
            "jianying_capcut",
        ):
            with self.subTest(bridge=bridge):
                result = build_control_plan(goal="公开测试", preferred_bridge=bridge)
                observe = next(phase for phase in result["phases"] if phase["phase"] == "observe")
                self.assertEqual(["starbridge.operation_context"], observe["tools"])
                self.assertEqual(
                    ["before_state", "after_state"],
                    observe["required_arguments"],
                )
                self.assertIn("operation_context_captured", result["quality_gates"])

    def test_result_redacts_private_path_text(self) -> None:
        result = build_control_plan(goal="Photoshop 处理 C:\\Users\\private\\client.psd")
        text = json.dumps(result, ensure_ascii=False)

        self.assertNotIn("C:\\Users\\private", text)
        self.assertIn("<REDACTED_PATH>", text)

    def test_tool_is_registered_with_safe_schema_and_capability_metadata(self) -> None:
        by_name = {tool["name"]: tool for tool in TOOL_DEFINITIONS}
        tool = by_name["starbridge.control_plan"]

        self.assertEqual(["goal"], tool["inputSchema"]["required"])
        self.assertEqual(500, tool["inputSchema"]["properties"]["goal"]["maxLength"])
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["safeDefault"])
        self.assertFalse(tool["annotations"]["requiresConfirmation"])
        self.assertEqual(
            "control_plan",
            tool["outputSchema"]["properties"]["action"]["const"],
        )

        capabilities = {item["name"]: item for item in list_capabilities()}
        self.assertEqual("safe_read_only", capabilities["starbridge.control_plan"]["risk_level"])

    def test_mcp_call_returns_structured_control_plan(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 91,
                "method": "tools/call",
                "params": {
                    "name": "starbridge.control_plan",
                    "arguments": {"goal": "用 Blender 规划公开产品三维场景"},
                },
            }
        )
        assert response is not None
        structured = response["result"]["structuredContent"]

        self.assertFalse(response["result"]["isError"])
        self.assertEqual("control_plan", structured["action"])
        self.assertEqual("blender", structured["bridge"])


if __name__ == "__main__":
    unittest.main()
