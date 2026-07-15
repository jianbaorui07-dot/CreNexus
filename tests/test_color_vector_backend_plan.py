from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.core.color_vector_backend import build_color_vector_backend_plan
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import handle_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "examples/illustrator_bridge/protocols/color_vector_backend_plan.v1.schema.json"


def base_arguments() -> dict:
    return {
        "reference_id": "public-flat-01",
        "reference_authorized": True,
        "backend_preference": "auto",
        "artwork_kind": "flat_artwork",
        "requires_gradient_fidelity": False,
        "requires_transparency": False,
        "requires_text_editability": False,
        "illustrator_available": False,
        "headless_dependencies_available": True,
    }


class ColorVectorBackendPlanTests(unittest.TestCase):
    def assert_no_path_or_script(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False).lower()
        for forbidden in (
            "input_path",
            "output_path",
            "c:\\users\\",
            "/users/",
            "/home/",
            "jsx",
            "powershell",
            "subprocess",
        ):
            self.assertNotIn(forbidden, text)

    def test_schema_is_closed_and_side_effect_free(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(schema["properties"]["dry_run"]["const"])
        self.assertFalse(schema["properties"]["side_effects"]["const"])
        safety = schema["properties"]["safety"]["properties"]
        self.assertFalse(safety["reads_files"]["const"])
        self.assertFalse(safety["writes_files"]["const"])
        self.assertFalse(safety["starts_adobe"]["const"])
        self.assertFalse(safety["arbitrary_script"]["const"])
        self.assertFalse(safety["silent_quality_degradation"]["const"])
        self.assert_no_path_or_script(schema)

    def test_auto_uses_headless_only_for_safe_flat_artwork(self) -> None:
        first = build_color_vector_backend_plan(base_arguments())
        self.assertEqual(first, build_color_vector_backend_plan(base_arguments()))
        self.assertTrue(first["ok"])
        self.assertEqual("headless_svg", first["selected_backend"])
        self.assertEqual("headless_trace_preview", first["next_action"]["kind"])
        self.assert_no_path_or_script(first)

    def test_photo_cannot_silently_fall_back(self) -> None:
        arguments = base_arguments()
        arguments["artwork_kind"] = "photo"
        result = build_color_vector_backend_plan(arguments)
        self.assertFalse(result["ok"])
        self.assertEqual("needs_user", result["state"])
        self.assertIsNone(result["selected_backend"])
        self.assertIn("native_backend_required", result["reason_codes"])

    def test_fidelity_features_require_native_backend(self) -> None:
        for field in (
            "requires_gradient_fidelity",
            "requires_transparency",
            "requires_text_editability",
        ):
            with self.subTest(field=field):
                arguments = base_arguments()
                arguments[field] = True
                result = build_color_vector_backend_plan(arguments)
                self.assertEqual("needs_user", result["state"])
                self.assertIsNone(result["selected_backend"])

    def test_explicit_unsafe_headless_request_is_rejected(self) -> None:
        arguments = base_arguments()
        arguments.update({"backend_preference": "headless_svg", "artwork_kind": "mixed"})
        result = build_color_vector_backend_plan(arguments)
        self.assertEqual("needs_user", result["state"])
        self.assertIn("headless_outside_supported_scope", result["reason_codes"])

    def test_explicit_safe_headless_request_is_truthfully_labeled(self) -> None:
        arguments = base_arguments()
        arguments.update({"backend_preference": "headless_svg", "illustrator_available": True})
        result = build_color_vector_backend_plan(arguments)
        self.assertEqual("headless_svg", result["selected_backend"])
        self.assertIn("headless_backend_requested", result["reason_codes"])
        self.assertNotIn("native_backend_unavailable", result["reason_codes"])

    def test_native_is_selected_when_required_and_available(self) -> None:
        arguments = base_arguments()
        arguments.update({"artwork_kind": "photo", "illustrator_available": True})
        result = build_color_vector_backend_plan(arguments)
        self.assertEqual("native_illustrator", result["selected_backend"])
        self.assertEqual("illustrator.color_vectorize_execute", result["next_action"]["tool"])

    def test_authorization_short_circuits_untrusted_traits(self) -> None:
        arguments = {
            "reference_id": "blocked-01",
            "reference_authorized": False,
            "artwork_kind": {"private_path": "C:\\private.png"},
        }
        result = build_color_vector_backend_plan(arguments)
        self.assertEqual("blocked", result["state"])
        self.assertNotIn("private", json.dumps(result).lower())

    def test_tool_and_registry_are_read_only(self) -> None:
        with patch(
            "starbridge_mcp.mcp_server.subprocess.run",
            side_effect=AssertionError("must not execute"),
        ):
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "illustrator.color_vectorize_backend_plan",
                        "arguments": base_arguments(),
                    },
                }
            )
        self.assertEqual(
            "headless_svg", response["result"]["structuredContent"]["selected_backend"]
        )
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {item["name"]: item for item in listed["result"]["tools"]}
        self.assertTrue(
            tools["illustrator.color_vectorize_backend_plan"]["annotations"]["readOnlyHint"]
        )
        caps = {
            item["name"]: item
            for item in list_capabilities(bridge="illustrator", include_guarded=True)
        }
        cap = caps["illustrator.color_vectorize_backend_plan"]
        self.assertTrue(cap["safe_default"])
        self.assertFalse(cap["requires_confirmation"])
        self.assertFalse(cap["requires_local_software"])


if __name__ == "__main__":
    unittest.main()
