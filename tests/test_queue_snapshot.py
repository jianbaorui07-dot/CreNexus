from __future__ import annotations

import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from starbridge_mcp.core.control_planner import build_control_plan
from starbridge_mcp.core.queue_snapshot import build_queue_snapshot
from starbridge_mcp.core.queue_snapshot_schema import SCHEMA_VERSION
from starbridge_mcp.core.tool_registry import list_capabilities
from starbridge_mcp.mcp_server import TOOL_DEFINITIONS, handle_request


def sample_queue_payload() -> dict:
    return {
        "queue_running": [
            [91, "raw-running-001", {"1": {"inputs": {"text": "hidden"}}}, {}],
        ],
        "queue_pending": [
            [-7, "raw-pending-001", {"2": {"inputs": {"value": "hidden"}}}, {}],
            [9001, "raw-pending-002", {"3": {"inputs": {"value": "hidden"}}}, {}],
        ],
    }


def private_windows_path(filename: str) -> str:
    return "\\".join(("C:", "Users", "private", "Desktop", filename))


class QueueSnapshotTests(unittest.TestCase):
    def test_default_is_plan_only_and_does_not_call_network(self) -> None:
        def fail_if_called(_base_url: str, _timeout: int) -> dict:
            raise AssertionError("network fetch must not run")

        result = build_queue_snapshot(fetcher=fail_if_called)

        self.assertTrue(result["ok"])
        self.assertEqual("planned", result["mode"])
        self.assertEqual("planned", result["decision"])
        self.assertFalse(result["connected"])
        self.assertFalse(result["queue"]["safe_to_enqueue"])
        self.assertFalse(result["safety"]["network_access"])

    def test_live_snapshot_uses_authoritative_array_lengths_and_redacts_payloads(self) -> None:
        result = build_queue_snapshot(
            probe=True,
            max_items=10,
            fetcher=lambda _base_url, _timeout: sample_queue_payload(),
        )
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["ok"])
        self.assertEqual("live", result["mode"])
        self.assertEqual("backlog", result["decision"])
        self.assertEqual(1, result["queue"]["running_count"])
        self.assertEqual(2, result["queue"]["pending_count"])
        self.assertEqual(3, result["queue"]["depth"])
        self.assertTrue(result["queue"]["backlog"])
        self.assertEqual(1, result["queue"]["pending_jobs"][0]["position"])
        self.assertNotIn("raw-running-001", serialized)
        self.assertNotIn("raw-pending-001", serialized)
        self.assertNotIn("hidden", serialized)
        self.assertNotIn("inputs", serialized)

    def test_job_aliases_are_stable_and_output_limit_does_not_change_counts(self) -> None:
        first = build_queue_snapshot(
            probe=True,
            max_items=2,
            fetcher=lambda _base_url, _timeout: sample_queue_payload(),
        )
        second = build_queue_snapshot(
            probe=True,
            max_items=2,
            fetcher=lambda _base_url, _timeout: sample_queue_payload(),
        )

        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(
            first["queue"]["running_jobs"][0]["logical_job_id"],
            second["queue"]["running_jobs"][0]["logical_job_id"],
        )
        self.assertEqual(3, first["queue"]["depth"])
        self.assertEqual(1, len(first["queue"]["pending_jobs"]))
        self.assertTrue(first["queue"]["truncated"])

    def test_structured_progress_is_numeric_bounded_and_monotonic(self) -> None:
        result = build_queue_snapshot(progress={"current": 5, "total": 14, "previous": 4})

        self.assertTrue(result["progress"]["available"])
        self.assertEqual("caller_supplied", result["progress"]["source"])
        self.assertEqual(35.71, result["progress"]["percent"])
        self.assertTrue(result["progress"]["monotonic"])

        for progress in (
            {"current": 15, "total": 14},
            {"current": 3, "total": 14, "previous": 4},
            {"current": 3, "total": 1_000_001},
            {"current": True, "total": 14},
            {"current": 3, "total": 14, "message": "node-name"},
        ):
            with self.subTest(progress=progress), self.assertRaises(ValueError):
                build_queue_snapshot(progress=progress)

    def test_only_plain_loopback_http_urls_are_allowed(self) -> None:
        unsafe_urls = (
            "http://example.invalid:8188",
            "https://127.0.0.1:8188",
            "http://user@example.invalid:8188",
            "http://127.0.0.1:8188/api",
            "http://127.0.0.1:8188?x=1",
        )
        for url in unsafe_urls:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "loopback") as caught:
                build_queue_snapshot(probe=True, comfy_url=url)
            self.assertNotIn(url, str(caught.exception))

    def test_live_failure_is_structured_without_echoing_exception(self) -> None:
        private_value = private_windows_path("queue-response.json")

        def fail(_base_url: str, _timeout: int) -> dict:
            raise OSError(private_value)

        result = build_queue_snapshot(probe=True, fetcher=fail)
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertFalse(result["ok"])
        self.assertEqual("unavailable", result["decision"])
        self.assertEqual("queue_endpoint_unavailable", result["error_code"])
        self.assertNotIn(private_value, serialized)
        self.assertFalse(result["queue"]["safe_to_enqueue"])

    def test_live_probe_does_not_follow_http_redirects(self) -> None:
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                if self.path == "/queue":
                    self.send_response(302)
                    self.send_header("Location", "/redirected")
                    self.end_headers()
                    return
                body = json.dumps({"queue_running": [], "queue_pending": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = build_queue_snapshot(
                probe=True,
                comfy_url=f"http://127.0.0.1:{server.server_port}",
                timeout=2,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertFalse(result["ok"])
        self.assertEqual("queue_endpoint_unavailable", result["error_code"])
        self.assertFalse(result["safety"]["redirects_followed"])

    def test_tool_schema_registry_and_control_plan_are_wired(self) -> None:
        definitions = {item["name"]: item for item in TOOL_DEFINITIONS}
        tool = definitions["comfyui.queue_snapshot"]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertTrue(tool["annotations"]["safeDefault"])
        self.assertTrue(tool["annotations"]["requiresLocalSoftware"])
        self.assertFalse(tool["inputSchema"]["properties"]["probe"]["default"])
        self.assertEqual(
            SCHEMA_VERSION,
            tool["outputSchema"]["properties"]["schema_version"]["const"],
        )
        self.assertFalse(tool["outputSchema"]["properties"]["safety"]["additionalProperties"])

        capabilities = {item["name"]: item for item in list_capabilities(include_guarded=False)}
        self.assertIn("comfyui.queue_snapshot", capabilities)

        plan = build_control_plan(goal="搭建 ComfyUI 文生图 workflow")
        discover = next(phase for phase in plan["phases"] if phase["phase"] == "discover")
        self.assertIn("comfyui.queue_snapshot", discover["tools"])
        self.assertIn("queue_backpressure_reviewed", plan["quality_gates"])

    def test_comfy_recipe_exposes_queue_contract_and_evidence_gate(self) -> None:
        plan_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "starbridge.recipe_plan",
                    "arguments": {"recipe_id": "comfyui_txt2img_lifecycle"},
                },
            }
        )
        assert plan_response is not None
        plan = plan_response["result"]["structuredContent"]["plan"]
        self.assertEqual(SCHEMA_VERSION, plan["queue_snapshot"]["schema_version"])
        self.assertEqual(
            "comfyui.queue_snapshot",
            plan["action_plan"]["tool_sequence"][0],
        )
        self.assertIn("queue_backpressure_reviewed", plan["quality_gates"])

        evidence_response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "starbridge.recipe_evidence",
                    "arguments": {"recipe_id": "comfyui_txt2img_lifecycle"},
                },
            }
        )
        assert evidence_response is not None
        manifest = evidence_response["result"]["structuredContent"]["manifest"]
        self.assertEqual(
            SCHEMA_VERSION,
            manifest["input_summary"]["queue_snapshot_schema"],
        )
        self.assertTrue(manifest["safety_decision"]["queue_backpressure_review_required"])

    def test_mcp_calls_return_structured_safe_results(self) -> None:
        planned = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "comfyui.queue_snapshot", "arguments": {}},
            }
        )
        assert planned is not None
        self.assertFalse(planned["result"]["isError"])
        self.assertEqual(
            SCHEMA_VERSION,
            planned["result"]["structuredContent"]["schema_version"],
        )

        with patch(
            "starbridge_mcp.core.queue_snapshot._read_queue",
            return_value=sample_queue_payload(),
        ):
            live = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "comfyui.queue_snapshot",
                        "arguments": {"probe": True, "max_items": 10},
                    },
                }
            )
        assert live is not None
        serialized = json.dumps(live, ensure_ascii=False)
        self.assertFalse(live["result"]["isError"])
        self.assertEqual("backlog", live["result"]["structuredContent"]["decision"])
        self.assertNotIn("raw-running-001", serialized)

        refused = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "comfyui.queue_snapshot",
                    "arguments": {"probe": True, "comfy_url": "http://example.invalid"},
                },
            }
        )
        assert refused is not None
        self.assertTrue(refused["result"]["isError"])
        self.assertNotIn("example.invalid", json.dumps(refused, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
