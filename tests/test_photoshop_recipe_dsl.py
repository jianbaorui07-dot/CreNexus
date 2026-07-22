from __future__ import annotations

import ctypes
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starbridge_mcp.adapters.photoshop import TOOL_DEFINITIONS, TOOL_HANDLERS
from starbridge_mcp.adapters.photoshop.bridge import PhotoshopBridgeAdapter, _build_context
from starbridge_mcp.adapters.photoshop.recipe_dsl import (
    build_batch_plan,
    capability_manifest,
    compile_recipe,
    verify_result,
)


class PhotoshopRecipeDslTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows 8.3 path aliases are Windows-only")
    def test_context_normalizes_windows_short_repo_alias(self) -> None:
        with TemporaryDirectory() as directory:
            long_root = Path(directory) / "CreNexus Long Repository Name"
            (long_root / "sandbox").mkdir(parents=True)
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(str(long_root), buffer, len(buffer))
            if not length or Path(buffer.value) == long_root:
                self.skipTest("8.3 aliases are disabled on this volume")

            context = _build_context({}, Path(buffer.value), "ps.get_state")

        self.assertEqual("sandbox/evidence", context.output_dir)
        self.assertEqual("evidence", context.evidence_dir.name)

    def test_capabilities_separate_live_truth_from_static_support(self) -> None:
        result = capability_manifest()
        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["live_connection_verified"])
        self.assertFalse(result["details"]["arbitrary_batchplay"])
        self.assertEqual(result["details"]["max_repair_rounds"], 3)
        self.assertIn(
            "native_psd_reopen_validation",
            result["details"]["categories"]["managed_production"]["features"],
        )

    def test_simple_recipe_is_execution_ready_and_minimal(self) -> None:
        result = compile_recipe("simple-tone-export-v1")
        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["execution_ready"])
        self.assertEqual(result["details"]["progressive_profile"], "minimal")
        self.assertTrue(result["details"]["single_history_state"])

    def test_advanced_recipe_reports_planned_only_categories(self) -> None:
        result = compile_recipe(
            "product-composite-verified-v1",
            {"template_asset_id": "asset-template", "replacement_asset_id": "asset-replacement"},
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["execution_ready"])
        self.assertIn("smart_objects", result["details"]["planned_only_categories"])
        self.assertEqual(result["details"]["progressive_profile"], "advanced")

    def test_managed_advanced_recipe_routes_to_real_production_workflow(self) -> None:
        result = compile_recipe(
            "production-subject-delivery-v1",
            {"source_asset_id": "managed-source"},
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["execution_ready"])
        self.assertEqual(
            "workflow:photoshop-production-v1", result["details"]["execution_entrypoint"]
        )
        self.assertTrue(result["details"]["parameters"]["export_subject"])

    def test_batch_is_deterministic_fifo_and_resumable(self) -> None:
        items = [
            {
                "recipe_id": "batch-production-delivery-v1",
                "parameters": {"source_asset_id": "managed-source-a"},
            },
            {
                "recipe_id": "batch-production-delivery-v1",
                "parameters": {"source_asset_id": "managed-source-b"},
            },
        ]
        first = build_batch_plan(items)
        completed = [first["details"]["items"][0]["item_id"]]
        resumed = build_batch_plan(items, completed_item_ids=completed)

        self.assertEqual(first, build_batch_plan(items))
        self.assertEqual(resumed["details"]["concurrency_limit"], 1)
        self.assertEqual(len(resumed["details"]["pending_item_ids"]), 1)
        self.assertEqual(resumed["details"]["blocked_item_ids"], [])

    def test_planned_batch_is_not_queued_as_executable(self) -> None:
        result = build_batch_plan(
            [
                {
                    "recipe_id": "batch-smart-object-replace-v1",
                    "parameters": {
                        "template_asset_id": "template",
                        "replacement_asset_id": "replacement",
                    },
                }
            ]
        )

        self.assertEqual(result["details"]["pending_item_ids"], [])
        self.assertEqual(len(result["details"]["blocked_item_ids"]), 1)
        self.assertEqual(result["details"]["items"][0]["status"], "blocked_planned")

    def test_result_verification_requires_all_quality_gates(self) -> None:
        good = verify_result(
            {
                "before_state": {"document_id": "redacted"},
                "after_state": {
                    "sandbox_copy": True,
                    "source_overwritten": False,
                    "validated_after_reopen": True,
                },
                "artifacts": [{"basename": "result.psd", "sha256": "a" * 64, "size_bytes": 1024}],
            }
        )
        bad = verify_result(
            {
                "before_state": {},
                "after_state": {"sandbox_copy": False, "source_overwritten": False},
                "artifacts": [],
                "repair_round": 2,
            }
        )

        self.assertTrue(good["ok"])
        self.assertFalse(bad["ok"])
        self.assertTrue(bad["details"]["repair_allowed"])
        self.assertEqual(bad["details"]["next_repair_round"], 3)

    def test_new_tools_are_registered(self) -> None:
        names = {tool["name"] for tool in TOOL_DEFINITIONS}
        expected = {"ps.capabilities", "ps.recipe.compile", "ps.batch.plan", "ps.result.verify"}
        self.assertTrue(expected.issubset(names))
        self.assertTrue(expected.issubset(TOOL_HANDLERS))

    def test_get_state_rejects_mock_fallback_as_live_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            adapter = PhotoshopBridgeAdapter(Path(directory))
            with (
                patch(
                    "starbridge_mcp.adapters.photoshop.bridge._node_proxy_probe",
                    return_value={
                        "health": {"ok": False},
                        "status": {},
                        "node_proxy_running": False,
                        "uxp_client_connected": False,
                        "photoshop_host_seen": False,
                    },
                ),
                patch(
                    "starbridge_mcp.adapters.photoshop.bridge._probe_com",
                    return_value=(False, {"active_document": False}, None),
                ),
            ):
                result = adapter.get_state({"bridge_kind": "auto"})

        self.assertFalse(result["ok"])
        self.assertFalse(result["details"]["live_state_verified"])
        self.assertFalse(result["details"]["simulated_state_returned"])
        self.assertEqual({}, result["details"]["document"])

    def test_get_preview_never_fabricates_missing_preview(self) -> None:
        with TemporaryDirectory() as directory:
            adapter = PhotoshopBridgeAdapter(Path(directory))
            result = adapter.get_preview({"job_id": "missing-preview"})

        self.assertFalse(result["ok"])
        self.assertFalse(result["details"]["preview_available"])
        self.assertFalse(result["details"]["fabricated_preview"])
        self.assertIsNone(result["details"]["base64"])


if __name__ == "__main__":
    unittest.main()
