from __future__ import annotations

import json
import unittest
from pathlib import Path

from starbridge_mcp.core.color_vectorization import (
    build_color_vectorization_plan,
    validate_color_vectorization_metrics,
)
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "examples"
    / "illustrator_bridge"
    / "protocols"
    / "color_vectorization.v1.schema.json"
)
SCRIPT = ROOT / "examples" / "illustrator_bridge" / "scripts" / "color_vectorize.ps1"
JSX = ROOT / "examples" / "illustrator_bridge" / "jsx" / "color_vectorize.jsx"


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


def base_plan_arguments() -> dict:
    return {
        "reference_id": "public-sample-01",
        "reference_authorized": True,
        "source_media_type": "image/png",
        "source_width": 1200,
        "source_height": 800,
    }


def passing_metrics() -> dict:
    return {
        "silhouette_iou": 0.98,
        "mean_delta_e": 2.5,
        "p95_delta_e": 7.0,
        "perceptual_similarity": 0.97,
        "anchor_count": 12000,
        "used_color_count": 48,
    }


def passing_hard_gates() -> dict:
    return {
        "reference_authorized": True,
        "primary_silhouette_present": True,
        "topology_valid": True,
        "editable_vector_present": True,
        "safe_output_scope": True,
    }


class ColorVectorizationTests(unittest.TestCase):
    def test_protocol_schema_is_closed_and_local_first(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            "^[a-z0-9][a-z0-9_-]{0,63}$",
            schema["properties"]["reference_id"]["pattern"],
        )
        safety = schema["properties"]["safety"]["properties"]
        self.assertFalse(safety["cloud_upload"]["const"])
        self.assertFalse(safety["recursive_scan"]["const"])
        self.assertFalse(safety["arbitrary_script"]["const"])
        trace = schema["properties"]["trace"]["properties"]
        self.assertEqual(2, trace["max_colors"]["minimum"])
        self.assertEqual(256, trace["max_colors"]["maximum"])
        self.assertFalse(trace["ignore_white"]["default"])

    def test_plan_preserves_color_and_does_not_read_pixels(self) -> None:
        plan = build_color_vectorization_plan(base_plan_arguments())

        self.assertTrue(plan["ok"])
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["source"]["pixels_read_by_plan"])
        self.assertEqual("color", plan["trace"]["mode"])
        self.assertFalse(plan["trace"]["ignore_white"])
        self.assertTrue(plan["trace"]["output_to_swatches"])
        self.assertFalse(plan["safety"]["cloud_upload"])
        apps = [item["app"] for item in plan["application_matrix"]]
        self.assertIn("photoshop", apps)
        self.assertIn("illustrator", apps)

    def test_plan_requires_reference_authorization(self) -> None:
        arguments = base_plan_arguments()
        arguments["reference_authorized"] = False

        plan = build_color_vectorization_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("blocked", plan["verdict"])

    def test_metric_validator_passes_only_complete_evidence(self) -> None:
        result = validate_color_vectorization_metrics(
            metrics=passing_metrics(), hard_gates=passing_hard_gates()
        )
        self.assertTrue(result["ok"])
        self.assertEqual("pass", result["verdict"])
        self.assertEqual([], result["findings"])

    def test_metric_validator_requests_repair_for_color_or_complexity(self) -> None:
        metrics = passing_metrics()
        metrics.update({"mean_delta_e": 9.0, "anchor_count": 300000})

        result = validate_color_vectorization_metrics(
            metrics=metrics, hard_gates=passing_hard_gates()
        )

        self.assertTrue(result["ok"])
        self.assertEqual("repair_needed", result["verdict"])
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("mean_delta_e_high", codes)
        self.assertIn("anchor_count_high", codes)

    def test_metric_validator_blocks_failed_hard_gate(self) -> None:
        hard_gates = passing_hard_gates()
        hard_gates["editable_vector_present"] = False

        result = validate_color_vectorization_metrics(
            metrics=passing_metrics(), hard_gates=hard_gates
        )

        self.assertFalse(result["ok"])
        self.assertEqual("blocked", result["verdict"])

    def test_mcp_tools_are_registered_with_safe_defaults(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        for name in (
            "illustrator.color_vectorize_plan",
            "illustrator.color_vectorize_validate",
            "illustrator.color_vectorize_execute",
        ):
            self.assertIn(name, tools)
        self.assertTrue(tools["illustrator.color_vectorize_plan"]["annotations"]["readOnlyHint"])
        self.assertTrue(
            tools["illustrator.color_vectorize_validate"]["annotations"]["readOnlyHint"]
        )
        execute = tools["illustrator.color_vectorize_execute"]
        self.assertFalse(execute["annotations"]["readOnlyHint"])
        self.assertIn("confirm_write", execute["inputSchema"]["properties"])
        self.assertIn("confirm_export", execute["inputSchema"]["properties"])

    def test_execute_defaults_to_plan_without_input_path(self) -> None:
        result = call_tool("illustrator.color_vectorize_execute", base_plan_arguments())
        structured = result["structuredContent"]

        self.assertFalse(result["isError"])
        self.assertTrue(structured["ok"])
        self.assertTrue(structured["dry_run"])
        self.assertNotIn("input_path", json.dumps(structured))

    def test_real_execute_requires_both_confirmations(self) -> None:
        arguments = base_plan_arguments()
        arguments.update({"dry_run": False, "input_path": "sample.png"})

        result = call_tool("illustrator.color_vectorize_execute", arguments)

        self.assertFalse(result["structuredContent"]["ok"])
        self.assertIn("confirm_write", result["structuredContent"]["warnings"][0])

    def test_string_confirmation_cannot_enable_real_execution(self) -> None:
        arguments = base_plan_arguments()
        arguments.update(
            {
                "dry_run": False,
                "input_path": "sample.png",
                "confirm_write": "true",
                "confirm_export": "true",
            }
        )

        result = call_tool("illustrator.color_vectorize_execute", arguments)

        self.assertFalse(result["structuredContent"]["ok"])
        self.assertIn("confirm_write", result["structuredContent"]["warnings"][0])

    def test_execute_rejects_output_escape(self) -> None:
        arguments = base_plan_arguments()
        arguments["output_dir"] = "../outside"

        result = call_tool("illustrator.color_vectorize_execute", arguments)

        self.assertTrue(result["isError"])
        self.assertIn("output_dir must stay inside", result["structuredContent"]["error"])

    def test_local_executor_is_fixed_and_color_trace_only(self) -> None:
        powershell = SCRIPT.read_text(encoding="utf-8")
        jsx = JSX.read_text(encoding="utf-8")

        self.assertIn("GetActiveObject", powershell)
        self.assertIn("Get-FileHash", powershell)
        self.assertNotIn("Invoke-Expression", powershell)
        self.assertNotIn("ScriptText", powershell)
        self.assertIn("doc.placedItems.add()", jsx)
        self.assertIn("TRACINGMODECOLOR", jsx)
        self.assertIn("expandTracing(false)", jsx)
        self.assertIn("app.redraw()", jsx)
        self.assertNotIn("eval(", jsx)

    def test_capability_registry_exposes_safe_and_guarded_routes(self) -> None:
        capabilities = {
            item["name"]: item
            for item in list_capabilities(bridge="illustrator", include_guarded=True)
        }
        self.assertTrue(capabilities["illustrator.color_vectorize_plan"]["safe_default"])
        self.assertTrue(capabilities["illustrator.color_vectorize_validate"]["safe_default"])
        self.assertFalse(capabilities["illustrator.color_vectorize_execute"]["safe_default"])
        self.assertTrue(
            capabilities["illustrator.color_vectorize_execute"]["requires_confirmation"]
        )


if __name__ == "__main__":
    unittest.main()
