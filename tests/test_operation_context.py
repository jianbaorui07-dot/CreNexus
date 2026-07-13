from __future__ import annotations

import json
import unittest

from starbridge_mcp.core.operation_context import (
    build_operation_context,
    operation_context_contract,
)
from starbridge_mcp.core.operation_context_schema import SCHEMA_VERSION
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request


def call_tool(arguments: dict) -> dict:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "starbridge.operation_context", "arguments": arguments},
        }
    )
    assert response is not None
    return response["result"]


def private_windows_path(filename: str) -> str:
    return "\\".join(("C:", "Users", "private", "Desktop", filename))


class OperationContextTests(unittest.TestCase):
    def sample_arguments(self) -> dict:
        return {
            "bridge": "photoshop",
            "action": "recipe_preview",
            "phase": "completed",
            "before_state": {
                "document_open": True,
                "layer_count": 2,
                "selection_count": 0,
                "progress": 0,
                "status": "ready",
            },
            "after_state": {
                "document_open": True,
                "layer_count": 3,
                "selection_count": 0,
                "progress": 100,
                "status": "ready",
            },
            "evidence_refs": ["recipe::photoshop_preview_export"],
        }

    def test_builds_deterministic_before_after_delta(self) -> None:
        first = build_operation_context(**self.sample_arguments())
        second = build_operation_context(**self.sample_arguments())

        self.assertTrue(first["ok"])
        self.assertEqual(SCHEMA_VERSION, first["schema_version"])
        self.assertEqual(first["context_id"], second["context_id"])
        self.assertRegex(first["context_id"], r"^ctx_[0-9a-f]{12}$")
        self.assertTrue(first["state"]["has_changes"])
        self.assertEqual(2, first["state"]["change_count"])
        changed = {item["field"]: item for item in first["state"]["delta"]["changed"]}
        self.assertEqual(
            (2, 3), (changed["layer_count"]["before"], changed["layer_count"]["after"])
        )
        self.assertEqual((0, 100), (changed["progress"]["before"], changed["progress"]["after"]))
        self.assertIn("document_open", first["state"]["delta"]["unchanged_fields"])
        self.assertFalse(first["safety"]["local_reads"])
        self.assertFalse(first["safety"]["local_writes"])

    def test_contexts_can_form_a_safe_chain(self) -> None:
        parent = build_operation_context(**self.sample_arguments())
        child_args = self.sample_arguments() | {
            "operation_id": "second_step",
            "parent_context_id": parent["context_id"],
        }
        child = build_operation_context(**child_args)

        self.assertEqual(parent["context_id"], child["parent_context_id"])
        self.assertNotEqual(parent["context_id"], child["context_id"])

    def test_unknown_or_private_state_is_rejected_without_echo(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown state fields"):
            build_operation_context(
                bridge="photoshop",
                action="inspect",
                before_state={"document_name": "private"},
                after_state={},
            )

        private_value = private_windows_path("client.psd")
        with self.assertRaisesRegex(ValueError, "safe identifier") as caught:
            build_operation_context(
                bridge="photoshop",
                action="inspect",
                before_state={"status": private_value},
                after_state={},
            )
        self.assertNotIn(private_value, str(caught.exception))

    def test_warning_is_sanitized_and_evidence_paths_are_refused(self) -> None:
        secret_fragment = "".join(("to", "ken", "=", "abc"))
        private_warning = f"source={private_windows_path('client.psd')} {secret_fragment}"
        payload = build_operation_context(
            **(self.sample_arguments() | {"warnings": [private_warning]})
        )
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["redactions_applied"])
        self.assertNotIn("private", serialized)
        self.assertNotIn("client.psd", serialized)
        self.assertNotIn(secret_fragment, serialized)

        with self.assertRaisesRegex(ValueError, "logical evidence id"):
            build_operation_context(
                **(
                    self.sample_arguments()
                    | {"evidence_refs": [private_windows_path("manifest.json")]}
                )
            )

    def test_contract_lists_only_whitelisted_state_fields(self) -> None:
        contract = operation_context_contract()

        self.assertEqual("starbridge.operation_context", contract["tool"])
        self.assertEqual(SCHEMA_VERSION, contract["schema_version"])
        self.assertIn("layer_count", contract["state_fields"])
        self.assertNotIn("document_name", contract["state_fields"])
        self.assertEqual("logical_ids_only", contract["evidence_ref_policy"])

    def test_tool_schema_registry_and_mcp_call_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        definition = definitions["starbridge.operation_context"]
        self.assertTrue(definition["annotations"]["safeDefault"])
        self.assertTrue(definition["annotations"]["readOnlyHint"])
        self.assertEqual(
            ["bridge", "action", "before_state", "after_state"],
            definition["inputSchema"]["required"],
        )
        self.assertEqual(
            SCHEMA_VERSION, definition["outputSchema"]["properties"]["schema_version"]["const"]
        )

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=False)}
        self.assertIn("starbridge.operation_context", capabilities)

        result = call_tool(self.sample_arguments())
        self.assertFalse(result["isError"])
        self.assertEqual(SCHEMA_VERSION, result["structuredContent"]["schema_version"])

    def test_invalid_mcp_call_is_structured_and_does_not_leak(self) -> None:
        private_value = private_windows_path("client.psd")
        result = call_tool(
            {
                "bridge": "photoshop",
                "action": "inspect",
                "before_state": {"status": private_value},
                "after_state": {},
            }
        )
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["isError"])
        self.assertFalse(result["structuredContent"]["ok"])
        self.assertNotIn(private_value, serialized)
        self.assertNotIn("\\".join(("C:", "Users", "")), serialized)

    def test_cross_bridge_recipe_plan_and_evidence_reference_context_contract(self) -> None:
        plan_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "starbridge.recipe_plan",
                    "arguments": {"recipe_id": "blender_scene_evidence"},
                },
            }
        )
        assert plan_response is not None
        plan = plan_response["result"]["structuredContent"]["plan"]
        self.assertEqual(SCHEMA_VERSION, plan["operation_context"]["schema_version"])
        self.assertEqual(
            "starbridge.operation_context",
            plan["action_plan"]["observation_tool"],
        )

        evidence_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "starbridge.recipe_evidence",
                    "arguments": {"recipe_id": "blender_scene_evidence"},
                },
            }
        )
        assert evidence_response is not None
        manifest = evidence_response["result"]["structuredContent"]["manifest"]
        self.assertEqual(
            SCHEMA_VERSION,
            manifest["input_summary"]["operation_context_schema"],
        )
        self.assertTrue(
            manifest["safety_decision"]["operation_context_required_after_major_action"]
        )


if __name__ == "__main__":
    unittest.main()
