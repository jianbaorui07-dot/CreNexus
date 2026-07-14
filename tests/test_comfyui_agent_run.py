from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from examples.comfy_bridge.workflow_agent import agent_run, query_job_status, submit_workflow
from starbridge_mcp.mcp_server import handle_request

BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "Desktop", "Documents", "AppData")


class ComfyAgentRunTests(unittest.TestCase):
    def assert_no_private_paths(self, payload: object) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_agent_run_without_confirm_run_does_not_submit(self) -> None:
        with patch("examples.comfy_bridge.workflow_agent.submit_workflow") as submit:
            result = agent_run({"goal": "生成一张国风 Q版 明代街市人物场景图"})

        submit.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["mode"])
        self.assertFalse(result["submitted"])
        self.assertIsNone(result["prompt_id"])
        self.assertIn("confirm_run=true", " ".join(result["warnings"]))

    def test_agent_run_confirm_true_allows_submit_and_sanitizes_manifest(self) -> None:
        fake_submission = {
            "ok": True,
            "prompt_id": "abc-123",
            "job_status": {
                "state": "completed",
                "history_available": True,
                "output_manifest": {
                    "prompt_id": "abc-123",
                    "image_count": 1,
                    "images": [
                        {
                            "node_id": "9",
                            "filename": "agent_00001.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ],
                },
            },
        }
        with patch(
            "examples.comfy_bridge.workflow_agent.submit_workflow", return_value=fake_submission
        ) as submit:
            result = agent_run(
                {
                    "goal": "生成一张国风 Q版 明代街市人物场景图",
                    "confirm_run": True,
                    "checkpoint": "placeholder.safetensors",
                }
            )

        submit.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual("confirmed", result["mode"])
        self.assertTrue(result["submitted"])
        self.assertEqual("abc-123", result["prompt_id"])
        self.assertEqual(1, result["output_manifest"]["image_count"])
        self.assert_no_private_paths(result)

    def test_query_job_status_maps_execution_error_without_leaking_details(self) -> None:
        private_detail = "PRIVATE_DETAIL_MUST_NOT_LEAK"
        history = {
            "abc-123": {
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "messages": [
                        ["execution_start", {"prompt_id": "abc-123"}],
                        [
                            "execution_error",
                            {
                                "prompt_id": "abc-123",
                                "exception_message": private_detail,
                                "traceback": [private_detail],
                            },
                        ],
                    ],
                },
                "outputs": {},
            }
        }

        with patch(
            "examples.comfy_bridge.workflow_agent.get_json", return_value=history
        ) as get_json:
            result = query_job_status("http://127.0.0.1:8188", "abc-123", 5)

        get_json.assert_called_once_with("http://127.0.0.1:8188", "/history/abc-123", 5)
        self.assertEqual("failed", result["state"])
        self.assertEqual("execution_error", result["terminal_event"])
        self.assertTrue(result["history_available"])
        self.assertEqual(0, result["output_manifest"]["image_count"])
        self.assertNotIn(private_detail, json.dumps(result))
        self.assert_no_private_paths(result)

    def test_query_job_status_uses_status_str_without_terminal_event(self) -> None:
        cases = (("success", True, "completed"), ("error", False, "failed"))
        for status_str, completed, expected_state in cases:
            with self.subTest(status_str=status_str):
                history = {
                    "abc-123": {
                        "status": {
                            "status_str": status_str,
                            "completed": completed,
                            "messages": [],
                        },
                        "outputs": {},
                    }
                }
                with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history):
                    result = query_job_status("http://127.0.0.1:8188", "abc-123", 5)

                self.assertEqual(expected_state, result["state"])
                self.assertNotIn("terminal_event", result)

    def test_history_without_terminal_signal_is_not_claimed_as_completed(self) -> None:
        history = {
            "abc-123": {
                "status": {
                    "messages": [
                        [{"unexpected": "event"}, {}],
                        [["execution_error"], {}],
                    ]
                },
                "outputs": {},
            }
        }
        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history):
            result = query_job_status("http://127.0.0.1:8188", "abc-123", 5)

        self.assertEqual("status_unavailable", result["state"])
        self.assertTrue(result["history_available"])

    def test_query_job_status_maps_interruption_to_cancelled(self) -> None:
        history = {
            "abc-123": {
                "status": {
                    "status_str": "error",
                    "completed": False,
                    "messages": [
                        ["execution_interrupted", {"prompt_id": "abc-123", "node_id": "7"}]
                    ],
                },
                "outputs": {},
            }
        }

        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history):
            result = query_job_status("http://127.0.0.1:8188", "abc-123", 5)

        self.assertEqual("cancelled", result["state"])
        self.assertEqual("execution_interrupted", result["terminal_event"])

    def test_status_str_success_wins_over_contradictory_error_events(self) -> None:
        history = {
            "abc-123": {
                "status": {
                    "status_str": "success",
                    "completed": True,
                    "messages": [
                        ["execution_error", {"prompt_id": "abc-123"}],
                        ["execution_interrupted", {"prompt_id": "abc-123"}],
                        ["execution_success", {"prompt_id": "abc-123"}],
                    ],
                },
                "outputs": {},
            }
        }

        with patch("examples.comfy_bridge.workflow_agent.get_json", return_value=history):
            result = query_job_status("http://127.0.0.1:8188", "abc-123", 5)

        self.assertEqual("completed", result["state"])
        self.assertEqual("execution_success", result["terminal_event"])

    def test_submit_and_agent_run_keep_failed_execution_as_submitted(self) -> None:
        failed_status = {
            "state": "failed",
            "history_available": True,
            "terminal_event": "execution_error",
            "output_manifest": {"prompt_id": "abc-123", "image_count": 0, "images": []},
        }
        with (
            patch(
                "examples.comfy_bridge.workflow_agent.post_json",
                return_value={"prompt_id": "abc-123"},
            ),
            patch(
                "examples.comfy_bridge.workflow_agent.query_job_status",
                return_value=failed_status,
            ) as query_status,
        ):
            submission = submit_workflow(
                {"1": {"class_type": "Example", "inputs": {}}},
                base_url="http://127.0.0.1:8188",
                timeout=5,
                wait_seconds=10,
            )

        query_status.assert_called_once()
        self.assertFalse(submission["ok"])
        self.assertTrue(submission["submitted"])
        self.assertEqual("comfyui_execution_failed", submission["error"])

        with patch("examples.comfy_bridge.workflow_agent.submit_workflow", return_value=submission):
            result = agent_run(
                {
                    "goal": "生成一张公开测试图",
                    "confirm_run": True,
                    "checkpoint": "placeholder.safetensors",
                }
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertEqual("failed", result["job_status"]["state"])
        self.assertIn("execution failed", " ".join(result["warnings"]))
        self.assertIn("dry-run", " ".join(result["next_steps"]))
        self.assert_no_private_paths(result)

    def test_status_poll_failure_preserves_submission_and_prompt_id(self) -> None:
        poll_errors = (
            urllib.error.URLError("local history unavailable"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        )
        submission = {}
        for poll_error in poll_errors:
            with (
                self.subTest(error=type(poll_error).__name__),
                patch(
                    "examples.comfy_bridge.workflow_agent.post_json",
                    return_value={"prompt_id": "abc-123"},
                ),
                patch(
                    "examples.comfy_bridge.workflow_agent.query_job_status",
                    side_effect=poll_error,
                ),
            ):
                submission = submit_workflow(
                    {"1": {"class_type": "Example", "inputs": {}}},
                    base_url="http://127.0.0.1:8188",
                    timeout=5,
                    wait_seconds=10,
                )

            self.assertFalse(submission["ok"])
            self.assertTrue(submission["submitted"])
            self.assertEqual("abc-123", submission["prompt_id"])
            self.assertEqual("comfyui_status_unavailable", submission["error"])
            self.assertEqual("status_unavailable", submission["job_status"]["state"])

        with patch("examples.comfy_bridge.workflow_agent.submit_workflow", return_value=submission):
            result = agent_run(
                {
                    "goal": "生成一张公开测试图",
                    "confirm_run": True,
                    "checkpoint": "placeholder.safetensors",
                }
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertEqual("abc-123", result["prompt_id"])
        self.assertEqual("status_unavailable", result["job_status"]["state"])
        self.assertIn("same prompt_id", " ".join(result["next_steps"]))
        self.assert_no_private_paths(result)

    def test_wait_zero_does_not_claim_submission_as_generation_success(self) -> None:
        with (
            patch(
                "examples.comfy_bridge.workflow_agent.post_json",
                return_value={"prompt_id": "abc-123"},
            ),
            patch("examples.comfy_bridge.workflow_agent.time.time", side_effect=[100.0, 101.0]),
            patch("examples.comfy_bridge.workflow_agent.query_job_status") as query_status,
        ):
            submission = submit_workflow(
                {"1": {"class_type": "Example", "inputs": {}}},
                base_url="http://127.0.0.1:8188",
                timeout=5,
                wait_seconds=0,
            )

        query_status.assert_not_called()
        self.assertFalse(submission["ok"])
        self.assertTrue(submission["submitted"])
        self.assertEqual("submitted", submission["job_status"]["state"])

    def test_queued_job_is_not_success_and_keeps_recovery_prompt_id(self) -> None:
        queued_status = {
            "state": "queued_or_running",
            "history_available": False,
            "output_manifest": {"prompt_id": "abc-123", "image_count": 0, "images": []},
        }
        with (
            patch(
                "examples.comfy_bridge.workflow_agent.post_json",
                return_value={"prompt_id": "abc-123"},
            ),
            patch("examples.comfy_bridge.workflow_agent.time.time", return_value=100.0),
            patch(
                "examples.comfy_bridge.workflow_agent.query_job_status",
                return_value=queued_status,
            ),
        ):
            submission = submit_workflow(
                {"1": {"class_type": "Example", "inputs": {}}},
                base_url="http://127.0.0.1:8188",
                timeout=5,
                wait_seconds=0,
            )

        self.assertFalse(submission["ok"])
        self.assertTrue(submission["submitted"])

        with patch("examples.comfy_bridge.workflow_agent.submit_workflow", return_value=submission):
            result = agent_run(
                {
                    "goal": "生成一张公开测试图",
                    "confirm_run": True,
                    "checkpoint": "placeholder.safetensors",
                }
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertEqual("queued_or_running", result["job_status"]["state"])
        self.assertIn("same prompt_id", " ".join(result["next_steps"]))

    def test_mcp_tools_list_contains_agent_workflow_tools(self) -> None:
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert response is not None
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertIn("comfyui.workflow_build_plan", names)
        self.assertIn("comfyui.workflow_build", names)
        self.assertIn("comfyui.workflow_repair", names)
        self.assertIn("comfyui.agent_run", names)


if __name__ == "__main__":
    unittest.main()
