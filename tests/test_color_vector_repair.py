from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.core.color_vector_repair import build_color_vector_repair_plan
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT / "examples" / "illustrator_bridge" / "protocols" / "color_vector_repair.v1.schema.json"
)


def call_tool(name: str, arguments: dict) -> dict:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    return response["result"]


def hard_gates() -> dict:
    return {
        "reference_authorized": True,
        "primary_silhouette_present": True,
        "topology_valid": True,
        "editable_vector_present": True,
        "safe_output_scope": True,
    }


def finding(code: str, severity: str = "warn") -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": f"Sanitized finding: {code}.",
    }


def base_arguments() -> dict:
    return {
        "reference_id": "public-repair-01",
        "reference_authorized": True,
        "repair_round": 1,
        "max_repair_rounds": 2,
        "comparison": {
            "verdict": "repair_needed",
            "hard_gates": hard_gates(),
            "findings": [
                finding("silhouette_iou_low"),
                finding("mean_delta_e_high"),
            ],
        },
        "current_trace": {
            "max_colors": 64,
            "path_fitting": 1.5,
            "min_area": 2,
            "preprocess_blur": 0.4,
            "ignore_white": False,
            "output_to_swatches": True,
        },
        "current_preprocess": {
            "photoshop_preprocess": False,
            "normalize_srgb": False,
            "max_dimension": 4096,
            "median_radius": 2,
        },
    }


class ColorVectorRepairTests(unittest.TestCase):
    def assert_no_path_or_script(self, payload: object) -> None:
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        for forbidden in (
            "input_path",
            "output_path",
            "reference_path",
            "candidate_preview_path",
            "c:\\users\\",
            "/users/",
            "/home/",
            "scripttext",
            "jsx",
            "batchplay",
            "powershell",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_protocol_schema_is_closed_and_side_effect_free(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(schema["properties"]["dry_run"]["const"])
        self.assertFalse(schema["properties"]["side_effects"]["const"])
        safety = schema["properties"]["safety"]["properties"]
        self.assertFalse(safety["reads_files"]["const"])
        self.assertFalse(safety["writes_files"]["const"])
        self.assertFalse(safety["starts_adobe"]["const"])
        self.assertFalse(safety["arbitrary_script"]["const"])
        self.assertFalse(safety["quality_gates_relaxed"]["const"])
        self.assertTrue(safety["bounded_repair"]["const"])
        self.assert_no_path_or_script(schema)

    def test_fidelity_and_color_findings_get_bounded_deterministic_changes(self) -> None:
        first = build_color_vector_repair_plan(base_arguments())
        second = build_color_vector_repair_plan(base_arguments())

        self.assertEqual(first, second)
        self.assertTrue(first["ok"])
        self.assertEqual("planned", first["verdict"])
        self.assertTrue(first["requires_execute"])
        self.assertEqual("illustrator.color_vectorize_execute", first["suggested_next_tool"])
        self.assertGreater(first["next_settings"]["trace"]["max_colors"], 64)
        self.assertLess(first["next_settings"]["trace"]["path_fitting"], 1.5)
        self.assertEqual(0, first["next_settings"]["trace"]["preprocess_blur"])
        self.assertTrue(first["next_settings"]["preprocess"]["photoshop_preprocess"])
        self.assertTrue(first["next_settings"]["preprocess"]["normalize_srgb"])
        self.assertEqual(0, first["next_settings"]["preprocess"]["median_radius"])
        self.assertEqual(
            {"silhouette_iou_low", "mean_delta_e_high"},
            set(first["addressed_findings"]),
        )
        self.assert_no_path_or_script(first)

    def test_anchor_only_repair_reduces_complexity_without_more_colors(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["findings"] = [finding("anchor_count_high")]

        plan = build_color_vector_repair_plan(arguments)

        self.assertTrue(plan["ok"])
        self.assertEqual(64, plan["next_settings"]["trace"]["max_colors"])
        self.assertGreater(plan["next_settings"]["trace"]["path_fitting"], 1.5)
        self.assertGreater(plan["next_settings"]["trace"]["min_area"], 2)
        self.assertGreater(plan["next_settings"]["trace"]["preprocess_blur"], 0.4)
        self.assertEqual(["anchor_count_high"], plan["addressed_findings"])

    def test_conflicting_fidelity_and_anchor_findings_preserve_unresolved_signal(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["findings"] = [
            finding("silhouette_iou_low"),
            finding("anchor_count_high"),
        ]

        plan = build_color_vector_repair_plan(arguments)

        self.assertTrue(plan["ok"])
        self.assertIn("silhouette_iou_low", plan["addressed_findings"])
        self.assertIn("anchor_count_high", plan["unresolved_findings"])
        self.assertTrue(plan["requires_user_review"])

    def test_pass_is_noop_and_does_not_start_adobe(self) -> None:
        arguments = base_arguments()
        arguments["comparison"] = {
            "verdict": "pass",
            "hard_gates": hard_gates(),
            "findings": [finding("icc_profile_fallback", "info")],
        }

        with patch(
            "starbridge_mcp.mcp_server.subprocess.run",
            side_effect=AssertionError("repair plan must not start Adobe"),
        ):
            result = call_tool("illustrator.color_vectorize_repair_plan", arguments)

        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual("pass_through", structured["verdict"])
        self.assertFalse(structured["requires_execute"])
        self.assertEqual([], structured["changes"])
        self.assertIsNone(structured["suggested_next_tool"])

    def test_failed_hard_gate_never_relaxes_quality_or_suggests_execution(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["verdict"] = "blocked"
        arguments["comparison"]["hard_gates"]["topology_valid"] = False
        arguments["comparison"]["findings"] = [finding("hard_gate_topology_valid", "critical")]

        plan = build_color_vector_repair_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("needs_user", plan["verdict"])
        self.assertEqual([], plan["changes"])
        self.assertFalse(plan["requires_execute"])
        self.assertTrue(plan["requires_user_review"])
        self.assertIsNone(plan["suggested_next_tool"])
        self.assertFalse(plan["safety"]["quality_gates_relaxed"])

    def test_exhausted_budget_stops_without_repair(self) -> None:
        arguments = base_arguments()
        arguments.update({"repair_round": 3, "max_repair_rounds": 2})

        plan = build_color_vector_repair_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("needs_user", plan["verdict"])
        self.assertEqual([], plan["changes"])
        self.assertIn("repair budget", plan["warnings"][0].lower())

    def test_non_actionable_or_unknown_findings_stop_for_user(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["findings"] = [
            finding("aspect_ratio_error_high"),
            finding("future_unknown_finding"),
        ]

        plan = build_color_vector_repair_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("needs_user", plan["verdict"])
        self.assertEqual(
            {"aspect_ratio_error_high", "future_unknown_finding"},
            set(plan["unresolved_findings"]),
        )

    def test_authorization_is_checked_before_comparison_payload(self) -> None:
        arguments = base_arguments()
        arguments["reference_authorized"] = False
        arguments["comparison"] = {"private_path": "C:\\private\\source.png"}

        plan = build_color_vector_repair_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("blocked", plan["verdict"])
        self.assertNotIn("private", json.dumps(plan).lower())

    def test_tool_and_registry_expose_safe_read_only_route(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        name = "illustrator.color_vectorize_repair_plan"
        self.assertIn(name, tools)
        self.assertTrue(tools[name]["annotations"]["readOnlyHint"])
        schema_text = json.dumps(tools[name]["inputSchema"]).lower()
        for forbidden in (
            "input_path",
            "output_path",
            "reference_path",
            "candidate_preview_path",
            "scripttext",
            "arbitrary_script",
        ):
            self.assertNotIn(forbidden, schema_text)

        capabilities = {
            item["name"]: item
            for item in list_capabilities(bridge="illustrator", include_guarded=True)
        }
        self.assertTrue(capabilities[name]["safe_default"])
        self.assertFalse(capabilities[name]["requires_confirmation"])
        self.assertFalse(capabilities[name]["requires_local_software"])


if __name__ == "__main__":
    unittest.main()
