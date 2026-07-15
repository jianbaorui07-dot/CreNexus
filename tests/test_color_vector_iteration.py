from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.core.color_vector_repair import advance_color_vector_iteration
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT / "examples" / "illustrator_bridge" / "protocols" / "color_vector_iteration.v1.schema.json"
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
        "reference_id": "public-iteration-01",
        "reference_authorized": True,
        "executed_round": 1,
        "max_repair_rounds": 3,
        "source_media_type": "image/png",
        "strategy": "hybrid",
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


class ColorVectorIterationTests(unittest.TestCase):
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
        self.assertTrue(safety["bounded_iteration"]["const"])
        self.assert_no_path_or_script(schema)

    def test_repair_needed_advances_exactly_one_round(self) -> None:
        first = advance_color_vector_iteration(base_arguments())
        second = advance_color_vector_iteration(base_arguments())

        self.assertEqual(first, second)
        self.assertTrue(first["ok"])
        self.assertEqual("repair_planned", first["state"])
        self.assertFalse(first["terminal"])
        self.assertEqual(2, first["next_repair_round"])
        self.assertEqual(2, first["remaining_rounds"])
        repair = first["next_repair_plan"]
        self.assertEqual("planned", repair["verdict"])
        self.assertEqual(2, repair["repair_round"])
        self.assertEqual(3, repair["max_repair_rounds"])
        self.assertTrue(repair["next_execute_template"]["dry_run"])
        self.assert_no_path_or_script(first)

    def test_pass_completes_without_starting_adobe(self) -> None:
        arguments = base_arguments()
        arguments["comparison"] = {
            "verdict": "pass",
            "hard_gates": hard_gates(),
            "findings": [finding("icc_profile_fallback", "info")],
        }

        with patch(
            "starbridge_mcp.mcp_server.subprocess.run",
            side_effect=AssertionError("iteration advance must not start Adobe"),
        ):
            result = call_tool("illustrator.color_vectorize_advance", arguments)

        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual("complete", structured["state"])
        self.assertTrue(structured["terminal"])
        self.assertIsNone(structured["next_repair_round"])
        self.assertIsNone(structured["next_repair_plan"])

    def test_last_round_stops_even_when_finding_is_actionable(self) -> None:
        arguments = base_arguments()
        arguments.update({"executed_round": 3, "max_repair_rounds": 3})

        result = advance_color_vector_iteration(arguments)

        self.assertFalse(result["ok"])
        self.assertEqual("needs_user", result["state"])
        self.assertTrue(result["terminal"])
        self.assertEqual(0, result["remaining_rounds"])
        self.assertIsNone(result["next_repair_round"])
        self.assertIsNone(result["next_repair_plan"])
        self.assertIn("budget", result["warnings"][0].lower())

    def test_failed_hard_gate_stops_without_repair(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["verdict"] = "blocked"
        arguments["comparison"]["hard_gates"]["topology_valid"] = False
        arguments["comparison"]["findings"] = [finding("hard_gate_topology_valid", "critical")]

        result = advance_color_vector_iteration(arguments)

        self.assertFalse(result["ok"])
        self.assertEqual("needs_user", result["state"])
        self.assertTrue(result["terminal"])
        self.assertIsNone(result["next_repair_plan"])

    def test_unknown_finding_stops_instead_of_guessing(self) -> None:
        arguments = base_arguments()
        arguments["comparison"]["findings"] = [finding("future_unknown_finding")]

        result = advance_color_vector_iteration(arguments)

        self.assertFalse(result["ok"])
        self.assertEqual("needs_user", result["state"])
        self.assertTrue(result["terminal"])
        self.assertIsNone(result["next_repair_plan"])

    def test_authorization_short_circuits_untrusted_payload(self) -> None:
        arguments = base_arguments()
        arguments["reference_authorized"] = False
        arguments["comparison"] = {"private_path": "C:\\private\\source.png"}
        arguments["current_trace"] = {"private": "do not inspect"}

        result = advance_color_vector_iteration(arguments)

        self.assertFalse(result["ok"])
        self.assertEqual("blocked", result["state"])
        self.assertIsNone(result["comparison_verdict"])
        self.assertNotIn("private", json.dumps(result).lower())

    def test_executed_round_cannot_exceed_budget(self) -> None:
        arguments = base_arguments()
        arguments.update({"executed_round": 3, "max_repair_rounds": 2})

        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            advance_color_vector_iteration(arguments)

    def test_tool_and_registry_expose_safe_read_only_route(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        name = "illustrator.color_vectorize_advance"
        self.assertIn(name, tools)
        self.assertTrue(tools[name]["annotations"]["readOnlyHint"])
        schema_text = json.dumps(tools[name]["inputSchema"]).lower()
        self.assert_no_path_or_script(schema_text)

        capabilities = {
            item["name"]: item
            for item in list_capabilities(bridge="illustrator", include_guarded=True)
        }
        self.assertTrue(capabilities[name]["safe_default"])
        self.assertFalse(capabilities[name]["requires_confirmation"])
        self.assertFalse(capabilities[name]["requires_local_software"])


if __name__ == "__main__":
    unittest.main()
