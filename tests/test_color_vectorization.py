from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, PngImagePlugin

from starbridge_mcp.core.color_vector_compare import compare_color_vectorization_files
from starbridge_mcp.core.color_vectorization import (
    build_color_vectorization_plan,
    validate_color_vectorization_metrics,
)
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT / "examples" / "illustrator_bridge" / "protocols" / "color_vectorization.v1.schema.json"
)
COMPARISON_SCHEMA = (
    ROOT
    / "examples"
    / "illustrator_bridge"
    / "protocols"
    / "color_vector_comparison.v1.schema.json"
)
SANDBOX = ROOT / "examples" / "output" / "illustrator"
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
        "aspect_ratio_error": 0.005,
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


def trace_evidence() -> dict:
    return {
        "anchor_count": 12000,
        "used_color_count": 48,
        "open_path_count": 0,
        "embedded_raster_count": 0,
    }


def write_fixture(
    path: Path,
    *,
    fill: str = "#d94841",
    offset: int = 0,
    metadata: str = "reference",
) -> None:
    image = Image.new("RGB", (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((12 + offset, 10, 50 + offset, 54), fill=fill)
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("fixture", metadata)
    image.save(path, pnginfo=pnginfo)


class ColorVectorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        SANDBOX.mkdir(parents=True, exist_ok=True)

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
        quality_gates = schema["properties"]["quality_gates"]
        self.assertIn("aspect_ratio_error_max", quality_gates["required"])

    def test_comparison_schema_is_closed_and_never_returns_paths_or_pixels(self) -> None:
        schema = json.loads(COMPARISON_SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        safety = schema["properties"]["safety"]["properties"]
        self.assertFalse(safety["recursive_scan"]["const"])
        self.assertFalse(safety["paths_returned"]["const"])
        self.assertFalse(safety["pixels_retained"]["const"])
        self.assertFalse(safety["metadata_returned"]["const"])
        serialized = json.dumps(schema)
        self.assertNotIn("reference_path", serialized)
        self.assertNotIn("candidate_preview_path", serialized)

    def test_plan_preserves_color_and_does_not_read_pixels(self) -> None:
        plan = build_color_vectorization_plan(base_plan_arguments())

        self.assertTrue(plan["ok"])
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["source"]["pixels_read_by_plan"])
        self.assertEqual("color", plan["trace"]["mode"])
        self.assertFalse(plan["trace"]["ignore_white"])
        self.assertTrue(plan["trace"]["output_to_swatches"])
        self.assertEqual(0.02, plan["quality_gates"]["aspect_ratio_error_max"])
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
        metrics.update({"aspect_ratio_error": 0.2, "mean_delta_e": 9.0, "anchor_count": 300000})

        result = validate_color_vectorization_metrics(
            metrics=metrics, hard_gates=passing_hard_gates()
        )

        self.assertTrue(result["ok"])
        self.assertEqual("repair_needed", result["verdict"])
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("aspect_ratio_error_high", codes)
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
            "illustrator.color_vectorize_compare",
        ):
            self.assertIn(name, tools)
        self.assertTrue(tools["illustrator.color_vectorize_plan"]["annotations"]["readOnlyHint"])
        self.assertTrue(
            tools["illustrator.color_vectorize_validate"]["annotations"]["readOnlyHint"]
        )
        self.assertTrue(tools["illustrator.color_vectorize_compare"]["annotations"]["readOnlyHint"])
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
        self.assertIn("open_path_count", jsx)
        self.assertIn("editable_vector_present", jsx)
        self.assertNotIn("eval(", jsx)

    def test_compare_identical_pixels_with_distinct_artifacts_passes(self) -> None:
        with (
            tempfile.TemporaryDirectory() as reference_dir,
            tempfile.TemporaryDirectory(prefix="compare-test-", dir=SANDBOX) as candidate_dir,
        ):
            reference = Path(reference_dir) / "reference.png"
            candidate = Path(candidate_dir) / "candidate.png"
            write_fixture(reference, metadata="reference")
            write_fixture(candidate, metadata="candidate")

            result = compare_color_vectorization_files(
                {
                    "reference_id": "public-sample-01",
                    "reference_authorized": True,
                    "reference_path": str(reference),
                    "candidate_preview_path": str(candidate),
                    "trace_evidence": trace_evidence(),
                    "max_dimension": 256,
                },
                repo_root=ROOT,
            )

        self.assertTrue(result["ok"])
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(1.0, result["metrics"]["silhouette_iou"])
        self.assertEqual(0.0, result["metrics"]["mean_delta_e"])
        self.assertEqual(1.0, result["metrics"]["perceptual_similarity"])
        self.assertTrue(result["artifacts"]["candidate_distinct"])
        serialized = json.dumps(result)
        self.assertNotIn("reference.png", serialized)
        self.assertNotIn("candidate.png", serialized)
        self.assertNotIn(reference_dir, serialized)

    def test_compare_color_and_geometry_mismatch_requests_repair(self) -> None:
        with (
            tempfile.TemporaryDirectory() as reference_dir,
            tempfile.TemporaryDirectory(prefix="compare-test-", dir=SANDBOX) as candidate_dir,
        ):
            reference = Path(reference_dir) / "reference.png"
            candidate = Path(candidate_dir) / "candidate.png"
            write_fixture(reference, fill="#d94841", metadata="reference")
            write_fixture(candidate, fill="#2864d7", offset=5, metadata="candidate")

            result = compare_color_vectorization_files(
                {
                    "reference_id": "public-sample-02",
                    "reference_authorized": True,
                    "reference_path": str(reference),
                    "candidate_preview_path": str(candidate),
                    "trace_evidence": trace_evidence(),
                },
                repo_root=ROOT,
            )

        self.assertTrue(result["ok"])
        self.assertEqual("repair_needed", result["verdict"])
        codes = {finding["code"] for finding in result["findings"]}
        self.assertTrue({"silhouette_iou_low", "mean_delta_e_high"} & codes)

    def test_compare_blocks_identical_file_hashes(self) -> None:
        with (
            tempfile.TemporaryDirectory() as reference_dir,
            tempfile.TemporaryDirectory(prefix="compare-test-", dir=SANDBOX) as candidate_dir,
        ):
            reference = Path(reference_dir) / "reference.png"
            candidate = Path(candidate_dir) / "candidate.png"
            write_fixture(reference)
            candidate.write_bytes(reference.read_bytes())

            result = compare_color_vectorization_files(
                {
                    "reference_id": "public-sample-03",
                    "reference_authorized": True,
                    "reference_path": str(reference),
                    "candidate_preview_path": str(candidate),
                    "trace_evidence": trace_evidence(),
                },
                repo_root=ROOT,
            )

        self.assertFalse(result["ok"])
        self.assertEqual("blocked", result["verdict"])
        self.assertFalse(result["artifacts"]["candidate_distinct"])

    def test_compare_requires_authorization_before_reading_paths(self) -> None:
        result = call_tool(
            "illustrator.color_vectorize_compare",
            {
                "reference_id": "public-sample-04",
                "reference_authorized": False,
                "reference_path": "does-not-exist.png",
                "candidate_preview_path": "also-does-not-exist.png",
                "trace_evidence": trace_evidence(),
            },
        )
        structured = result["structuredContent"]
        self.assertFalse(result["isError"])
        self.assertFalse(structured["ok"])
        self.assertEqual("authorization_required", structured["error_code"])
        self.assertNotIn("does-not-exist", json.dumps(structured))

    def test_compare_rejects_candidate_outside_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as outside_dir:
            reference = Path(outside_dir) / "reference.png"
            candidate = Path(outside_dir) / "candidate.png"
            write_fixture(reference, metadata="reference")
            result = call_tool(
                "illustrator.color_vectorize_compare",
                {
                    "reference_id": "public-sample-05",
                    "reference_authorized": True,
                    "reference_path": str(reference),
                    "candidate_preview_path": str(candidate),
                    "trace_evidence": trace_evidence(),
                    "soft_exit": False,
                },
            )

        self.assertTrue(result["isError"])
        self.assertIn("candidate preview must stay inside", result["structuredContent"]["error"])
        self.assertNotIn(outside_dir, json.dumps(result))

    def test_capability_registry_exposes_safe_and_guarded_routes(self) -> None:
        capabilities = {
            item["name"]: item
            for item in list_capabilities(bridge="illustrator", include_guarded=True)
        }
        self.assertTrue(capabilities["illustrator.color_vectorize_plan"]["safe_default"])
        self.assertTrue(capabilities["illustrator.color_vectorize_validate"]["safe_default"])
        self.assertTrue(capabilities["illustrator.color_vectorize_compare"]["safe_default"])
        self.assertFalse(capabilities["illustrator.color_vectorize_execute"]["safe_default"])
        self.assertTrue(
            capabilities["illustrator.color_vectorize_execute"]["requires_confirmation"]
        )


if __name__ == "__main__":
    unittest.main()
