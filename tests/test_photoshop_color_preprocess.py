from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.core.color_preprocess import build_color_preprocess_plan
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT / "examples" / "photoshop_bridge" / "protocols" / "color_vector_preprocess.v1.schema.json"
)
SCRIPT = ROOT / "examples" / "photoshop_bridge" / "scripts" / "color_vector_preprocess.ps1"
JSX = ROOT / "examples" / "photoshop_bridge" / "jsx" / "color_vector_preprocess.jsx"


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


def base_arguments() -> dict:
    return {
        "recipe_id": "prepare_vector_trace",
        "reference_id": "public-vector-source-01",
        "reference_authorized": True,
        "source_media_type": "image/jpeg",
        "source_width": 5000,
        "source_height": 3200,
        "max_dimension": 4096,
        "median_radius": 2,
        "normalize_srgb": True,
    }


class PhotoshopColorPreprocessTests(unittest.TestCase):
    def assert_no_private_path(self, payload: object, private_path: str = "") -> None:
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("C:\\Users\\", serialized)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("/home/", serialized)
        if private_path:
            self.assertNotIn(private_path, serialized)

    def test_protocol_schema_is_closed_and_copy_first(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            "^[a-z0-9][a-z0-9_-]{0,63}$",
            schema["properties"]["reference_id"]["pattern"],
        )
        settings = schema["properties"]["settings"]["properties"]
        self.assertEqual(5, settings["median_radius"]["maximum"])
        self.assertTrue(settings["preserve_alpha"]["const"])
        safety = schema["properties"]["safety"]["properties"]
        self.assertTrue(safety["sandbox_copy_before_photoshop"]["const"])
        self.assertFalse(safety["original_modified"]["const"])
        self.assertFalse(safety["arbitrary_script"]["const"])

    def test_plan_is_dry_run_and_reads_no_pixels(self) -> None:
        plan = build_color_preprocess_plan(base_arguments())

        self.assertTrue(plan["ok"])
        self.assertEqual("planned", plan["verdict"])
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["source"]["pixels_read_by_plan"])
        self.assertEqual(4096, plan["settings"]["max_dimension"])
        self.assertEqual(2, plan["settings"]["median_radius"])
        self.assertTrue(plan["settings"]["normalize_srgb"])
        self.assertEqual("examples/output/photoshop", plan["outputs"]["output_dir"])
        self.assertNotIn("input_path", json.dumps(plan))

    def test_plan_requires_authorization_before_file_use(self) -> None:
        arguments = base_arguments()
        arguments["reference_authorized"] = False
        arguments["input_path"] = "private-does-not-exist.png"

        plan = build_color_preprocess_plan(arguments)

        self.assertFalse(plan["ok"])
        self.assertEqual("authorization_required", plan["error_code"])
        self.assertNotIn("private-does-not-exist", json.dumps(plan))

    def test_recipe_list_exposes_vector_trace_preparation(self) -> None:
        result = call_tool("photoshop.recipe_list", {})
        recipe_ids = {item["recipe_id"] for item in result["structuredContent"]["recipes"]}

        self.assertIn("prepare_vector_trace", recipe_ids)

    def test_recipe_schemas_expose_typed_preprocess_controls(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        for name in (
            "photoshop.recipe_plan",
            "photoshop.recipe_validate",
            "photoshop.recipe_run",
        ):
            properties = tools[name]["inputSchema"]["properties"]
            self.assertIn("reference_id", properties)
            self.assertIn("reference_authorized", properties)
            self.assertIn("max_dimension", properties)
            self.assertIn("median_radius", properties)
            self.assertIn("normalize_srgb", properties)
        run_properties = tools["photoshop.recipe_run"]["inputSchema"]["properties"]
        self.assertIn("input_path", run_properties)
        self.assertIn("confirm_export", run_properties)

    def test_recipe_run_dry_run_never_starts_photoshop(self) -> None:
        with patch(
            "starbridge_mcp.mcp_server.subprocess.run",
            side_effect=AssertionError("Photoshop must not start during dry-run"),
        ):
            result = call_tool("photoshop.recipe_run", base_arguments())

        structured = result["structuredContent"]
        self.assertFalse(result["isError"])
        self.assertTrue(structured["ok"])
        self.assertTrue(structured["dry_run"])
        self.assertEqual("color_preprocess_plan", structured["preprocess_plan"]["action"])

    def test_real_recipe_requires_authorization_before_reading_input(self) -> None:
        arguments = base_arguments()
        arguments.update(
            {
                "reference_authorized": False,
                "input_path": "private-does-not-exist.png",
                "dry_run": False,
                "confirm_write": True,
                "confirm_export": True,
            }
        )

        with patch(
            "starbridge_mcp.mcp_server.subprocess.run",
            side_effect=AssertionError("unauthorized input must not reach Photoshop"),
        ):
            result = call_tool("photoshop.recipe_run", arguments)

        structured = result["structuredContent"]
        self.assertFalse(result["isError"])
        self.assertFalse(structured["ok"])
        self.assertEqual("authorization_required", structured["error_code"])
        self.assertNotIn("private-does-not-exist", json.dumps(structured))

    def test_real_recipe_requires_write_and_export_confirmation(self) -> None:
        arguments = base_arguments()
        arguments.update({"dry_run": False, "input_path": "source.png"})

        result = call_tool("photoshop.recipe_run", arguments)

        structured = result["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertIn("confirm_write", structured["warnings"][0])
        arguments["confirm_write"] = True
        result = call_tool("photoshop.recipe_run", arguments)
        self.assertIn("confirm_export", result["structuredContent"]["warnings"][0])

    def test_string_confirmations_cannot_enable_preprocess(self) -> None:
        arguments = base_arguments()
        arguments.update(
            {
                "dry_run": False,
                "input_path": "source.png",
                "confirm_write": "true",
                "confirm_export": "true",
            }
        )

        result = call_tool("photoshop.recipe_run", arguments)

        self.assertFalse(result["structuredContent"]["ok"])
        self.assertIn("confirm_write", result["structuredContent"]["warnings"][0])

    def test_confirmed_recipe_records_redacted_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.jpg"
            source.write_bytes(b"public-test-placeholder")
            arguments = base_arguments()
            arguments.update(
                {
                    "input_path": str(source),
                    "dry_run": False,
                    "confirm_write": True,
                    "confirm_export": True,
                }
            )
            photoshop_result = {
                "ok": True,
                "bridge": "photoshop",
                "action": "color_preprocess",
                "reference_id": "public-vector-source-01",
                "input_sha256": "a" * 64,
                "source_copy_sha256": "a" * 64,
                "output_sha256": "b" * 64,
                "outputs": {
                    "source_copy": "examples/output/photoshop/public-vector-source-01_source.jpg",
                    "prepared_png": "examples/output/photoshop/public-vector-source-01_vector_source.png",
                },
                "safety": {
                    "source_copy_verified": True,
                    "output_sandboxed": True,
                },
            }
            evidence_path = (
                ROOT
                / "examples"
                / "output"
                / "evidence"
                / "public-vector-source-01.color_preprocess.json"
            )

            with (
                patch(
                    "starbridge_mcp.mcp_server._run_powershell_json",
                    return_value=photoshop_result,
                ) as runner,
                patch(
                    "starbridge_mcp.mcp_server.save_manifest",
                    return_value=evidence_path,
                ) as save,
            ):
                result = call_tool("photoshop.recipe_run", arguments)

        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual(
            "examples/output/evidence/public-vector-source-01.color_preprocess.json",
            structured["evidence_path"],
        )
        runner.assert_called_once()
        save.assert_called_once()
        manifest = save.call_args.args[0].to_dict()
        self.assertEqual("completed", manifest["status"])
        self.assertTrue(
            next(item for item in manifest["validation"] if item["name"] == "source_copy_verified")[
                "ok"
            ]
        )
        self.assert_no_private_path(structured, temp_dir)
        self.assert_no_private_path(manifest, temp_dir)

    def test_output_escape_is_rejected(self) -> None:
        arguments = base_arguments()
        arguments["output_dir"] = "examples/output/illustrator"

        result = call_tool("photoshop.recipe_plan", arguments)

        self.assertTrue(result["isError"])
        self.assertIn("output_dir must stay inside", result["structuredContent"]["error"])

    def test_fixed_scripts_copy_then_preprocess_without_arbitrary_code(self) -> None:
        powershell = SCRIPT.read_text(encoding="utf-8")
        jsx = JSX.read_text(encoding="utf-8")

        self.assertIn("GetActiveObject", powershell)
        self.assertIn("Copy-Item", powershell)
        self.assertIn("Get-FileHash", powershell)
        self.assertNotIn("New-Object -ComObject", powershell)
        self.assertNotIn("Invoke-Expression", powershell)
        self.assertIn("convertProfile", jsx)
        self.assertIn("resizeImage", jsx)
        self.assertIn("applyMedianNoise", jsx)
        self.assertIn("PNGSaveOptions", jsx)
        self.assertIn("DONOTSAVECHANGES", jsx)
        self.assertNotIn("eval(", jsx)

    def test_illustrator_plan_declares_photoshop_preprocess_settings(self) -> None:
        arguments = base_arguments()
        arguments.pop("recipe_id")
        arguments["photoshop_preprocess"] = True

        result = call_tool("illustrator.color_vectorize_plan", arguments)
        structured = result["structuredContent"]

        self.assertTrue(structured["ok"])
        self.assertTrue(structured["preprocess"]["enabled"])
        self.assertEqual(2, structured["preprocess"]["median_radius"])
        photoshop_stage = next(
            item for item in structured["application_matrix"] if item["app"] == "photoshop"
        )
        self.assertTrue(photoshop_stage["enabled"])

    def test_confirmed_illustrator_chain_uses_prepared_sandbox_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.png"
            source.write_bytes(b"public-test-placeholder")
            arguments = base_arguments()
            arguments.pop("recipe_id")
            arguments.update(
                {
                    "input_path": str(source),
                    "photoshop_preprocess": True,
                    "dry_run": False,
                    "confirm_write": True,
                    "confirm_export": True,
                }
            )
            preprocess_result = {
                "ok": True,
                "bridge": "photoshop",
                "action": "color_preprocess",
                "reference_id": "public-vector-source-01",
                "input_sha256": "a" * 64,
                "output_sha256": "b" * 64,
                "outputs": {
                    "prepared_png": "examples/output/photoshop/public-vector-source-01_vector_source.png"
                },
                "evidence_path": "examples/output/evidence/public-vector-source-01.color_preprocess.json",
            }
            illustrator_result = {
                "ok": True,
                "bridge": "illustrator",
                "task": "color_vectorize",
                "verdict": "needs_visual_review",
            }

            with (
                patch(
                    "starbridge_mcp.mcp_server._execute_photoshop_color_preprocess",
                    return_value=preprocess_result,
                ) as preprocess,
                patch(
                    "starbridge_mcp.mcp_server._run_powershell_json",
                    return_value=illustrator_result,
                ) as illustrator,
            ):
                result = call_tool("illustrator.color_vectorize_execute", arguments)

        structured = result["structuredContent"]
        self.assertTrue(structured["ok"])
        self.assertEqual("photoshop_to_illustrator", structured["application_chain"])
        self.assertEqual("a" * 64, structured["preprocess"]["input_sha256"])
        preprocess.assert_called_once()
        illustrator_args = illustrator.call_args.args[1]
        self.assertTrue(
            any(
                "public-vector-source-01_vector_source.png" in str(item)
                for item in illustrator_args
            )
        )
        self.assert_no_private_path(structured, temp_dir)


if __name__ == "__main__":
    unittest.main()
