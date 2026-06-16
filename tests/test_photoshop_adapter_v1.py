from __future__ import annotations

import json
import unittest
from pathlib import Path

from starbridge_mcp.mcp_server import handle_request


REPO_ROOT = Path(__file__).resolve().parents[1]


def request(message_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_request(payload)
    assert response is not None
    return response


class PhotoshopAdapterV1Tests(unittest.TestCase):
    def test_ps_tools_have_required_schema_fields(self) -> None:
        response = request(1, "tools/list")
        by_name = {tool["name"]: tool for tool in response["result"]["tools"]}

        for tool_name in (
            "ps.probe",
            "ps.document.info",
            "ps.layers.list",
            "ps.selection.subject",
            "ps.layer.rename",
            "ps.layer.move",
            "ps.layer.visibility",
            "ps.preview.export",
            "ps.camera_raw.tune",
            "ps.evidence.capture",
            "ps.batchplay.validate",
        ):
            with self.subTest(tool=tool_name):
                schema = by_name[tool_name]["inputSchema"]["properties"]
                for key in (
                    "risk_level",
                    "requires_confirmation",
                    "dry_run",
                    "writes_files",
                    "touches_user_psd",
                    "bridge_kind",
                    "output_dir",
                ):
                    self.assertIn(key, schema)

    def test_mock_document_and_layers_are_available_without_photoshop(self) -> None:
        info = request(2, "tools/call", {"name": "ps.document.info", "arguments": {"bridge_kind": "mock"}})
        layers = request(3, "tools/call", {"name": "ps.layers.list", "arguments": {"bridge_kind": "mock"}})

        info_payload = info["result"]["structuredContent"]
        layers_payload = layers["result"]["structuredContent"]
        self.assertTrue(info_payload["ok"])
        self.assertTrue(layers_payload["ok"])
        self.assertEqual("mock", info_payload["details"]["bridge_kind"])
        self.assertGreater(layers_payload["details"]["layer_count"], 0)

    def test_preview_export_defaults_to_dry_run(self) -> None:
        response = request(4, "tools/call", {"name": "ps.preview.export", "arguments": {"bridge_kind": "mock"}})
        payload = response["result"]["structuredContent"]

        self.assertTrue(payload["ok"])
        manifest = payload["details"]["evidence_manifest"]
        self.assertTrue(manifest["dry_run"])
        self.assertIsNone(payload["details"]["evidence_path"])
        self.assertEqual([], payload["details"]["preview_files"])

    def test_camera_raw_tune_defaults_to_dry_run_plan(self) -> None:
        response = request(45, "tools/call", {"name": "ps.camera_raw.tune", "arguments": {"bridge_kind": "mock"}})
        payload = response["result"]["structuredContent"]

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["details"]["dry_run"])
        self.assertFalse(payload["details"]["confirm_apply"])
        self.assertEqual("blue_artwork_clean", payload["details"]["plan"]["preset"])
        self.assertEqual(4800, payload["details"]["plan"]["params"]["temperature"])
        self.assertIsNone(payload["details"]["evidence_path"])

    def test_camera_raw_tune_rejects_out_of_range_params(self) -> None:
        response = request(
            46,
            "tools/call",
            {"name": "ps.camera_raw.tune", "arguments": {"params": {"exposure": 8}}},
        )
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("params.exposure", " ".join(payload["details"]["errors"]))

    def test_camera_raw_tune_requires_confirm_apply_for_real_apply(self) -> None:
        response = request(
            47,
            "tools/call",
            {"name": "ps.camera_raw.tune", "arguments": {"dry_run": False}},
        )
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("confirm_apply", payload["message"])

    def test_camera_raw_tune_blocks_when_descriptor_is_missing(self) -> None:
        response = request(
            48,
            "tools/call",
            {"name": "ps.camera_raw.tune", "arguments": {"dry_run": False, "confirm_apply": True}},
        )
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertEqual("camera_raw_batchplay_descriptor_not_recorded", payload["details"]["blocked_reason"])
        self.assertIn("Record a verified Camera Raw Filter descriptor", payload["details"]["next_step"])

    def test_camera_raw_tune_output_dir_cannot_escape_photoshop_output(self) -> None:
        response = request(
            49,
            "tools/call",
            {"name": "ps.camera_raw.tune", "arguments": {"output_dir": "sandbox"}},
        )
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("examples/output/photoshop", payload["error"])

    def test_selection_subject_mock_plan_is_available(self) -> None:
        response = request(41, "tools/call", {"name": "ps.selection.subject", "arguments": {"bridge_kind": "mock"}})
        payload = response["result"]["structuredContent"]

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["details"]["plan_only"])
        self.assertTrue(payload["details"]["evidence_manifest"]["dry_run"])

    def test_layer_write_tools_refuse_real_write_without_confirmation(self) -> None:
        for tool_name, arguments in (
            ("ps.layer.rename", {"layer_id": "layer-text", "layer_name": "Renamed"}),
            ("ps.layer.move", {"layer_id": "layer-text", "target_index": 1}),
            ("ps.layer.visibility", {"layer_id": "layer-text", "visible": False}),
        ):
            with self.subTest(tool=tool_name):
                response = request(
                    42,
                    "tools/call",
                    {"name": tool_name, "arguments": {"bridge_kind": "mock", "dry_run": False, **arguments}},
                )
                payload = response["result"]["structuredContent"]
                self.assertFalse(payload["ok"])
                self.assertIn("requires_confirmation", payload["message"])

    def test_layer_write_tools_confirmed_path_stays_disabled(self) -> None:
        response = request(
            43,
            "tools/call",
            {
                "name": "ps.layer.rename",
                "arguments": {
                    "bridge_kind": "mock",
                    "dry_run": False,
                    "requires_confirmation": True,
                    "layer_id": "layer-text",
                    "layer_name": "Renamed",
                },
            },
        )
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["details"]["plan_only"])
        self.assertIn("sandbox-safe", " ".join(payload["warnings"]).lower())

    def test_preview_export_requires_confirmation_for_real_write(self) -> None:
        response = request(
            5,
            "tools/call",
            {
                "name": "ps.preview.export",
                "arguments": {"bridge_kind": "mock", "dry_run": False, "writes_files": True},
            },
        )
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("requires_confirmation", payload["message"])

    def test_confirmed_mock_preview_writes_manifest_and_png(self) -> None:
        response = request(
            6,
            "tools/call",
            {
                "name": "ps.preview.export",
                "arguments": {
                    "bridge_kind": "mock",
                    "dry_run": False,
                    "writes_files": True,
                    "requires_confirmation": True,
                    "output_dir": "sandbox",
                },
            },
        )
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        manifest_path = payload["details"]["evidence_path"]
        preview_files = payload["details"]["preview_files"]
        self.assertIsNotNone(manifest_path)
        self.assertEqual(1, len(preview_files))
        self.assertTrue((REPO_ROOT / manifest_path).exists())
        self.assertTrue((REPO_ROOT / preview_files[0]).exists())

    def test_evidence_manifest_fields_are_complete(self) -> None:
        response = request(
            7,
            "tools/call",
            {"name": "ps.batchplay.validate", "arguments": {"bridge_kind": "mock", "descriptor": {"_obj": "make"}}},
        )
        payload = response["result"]["structuredContent"]
        manifest = payload["details"]["evidence_manifest"]

        self.assertTrue(payload["ok"])
        for key in (
            "job_id",
            "created_at",
            "adapter_name",
            "adapter_version",
            "tool_name",
            "risk_level",
            "requires_confirmation",
            "dry_run",
            "input_summary",
            "output_files",
            "preview_files",
            "source_files",
            "photoshop_available",
            "bridge_kind",
            "node_proxy_status",
            "uxp_status",
            "photoshop_host",
            "layers_snapshot",
            "history_state",
            "descriptor_summary",
            "validation_result",
            "status",
            "warnings",
            "errors",
        ):
            self.assertIn(key, manifest)

    def test_destructive_tools_are_disabled(self) -> None:
        for tool_name in ("ps.history.undo", "ps.mask.refine", "ps.smartobject.place", "ps.adjustment.apply"):
            with self.subTest(tool=tool_name):
                response = request(8, "tools/call", {"name": tool_name, "arguments": {"bridge_kind": "mock"}})
                payload = response["result"]["structuredContent"]
                self.assertFalse(payload["ok"])
                self.assertIn("disabled", payload["details"]["status"])

    def test_execute_confirmed_requires_confirmation(self) -> None:
        response = request(80, "tools/call", {"name": "ps.batchplay.execute_confirmed", "arguments": {"bridge_kind": "mock"}})
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["ok"])
        self.assertIn("requires_confirmation", payload["message"])

    def test_execute_and_history_schemas_require_confirmation_by_default(self) -> None:
        response = request(44, "tools/list")
        by_name = {tool["name"]: tool for tool in response["result"]["tools"]}
        for tool_name in ("ps.batchplay.execute_confirmed", "ps.history.undo"):
            with self.subTest(tool=tool_name):
                schema = by_name[tool_name]["inputSchema"]["properties"]
                self.assertTrue(schema["requires_confirmation"]["default"])
                self.assertTrue(schema["dry_run"]["default"])

    def test_batchplay_validate_flags_destructive_methods(self) -> None:
        response = request(
            9,
            "tools/call",
            {"name": "ps.batchplay.validate", "arguments": {"descriptor": {"_obj": "delete"}}},
        )
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertIn("delete", json.dumps(payload["details"], ensure_ascii=False))
        self.assertTrue(payload["warnings"])
        self.assertFalse(payload["details"]["validation_result"]["ok"])


if __name__ == "__main__":
    unittest.main()
