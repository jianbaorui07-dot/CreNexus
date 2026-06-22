from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from starbridge_mcp.core.computer_use import (
    ActionPlan,
    CodexComputerUseAdapter,
    MockComputerUseAdapter,
    evaluate_safety,
    is_safe_output_path,
)
from starbridge_mcp.core.computer_use_demos import run_demo

REPO_ROOT = Path(__file__).resolve().parents[1]


class ComputerUsePlanTests(unittest.TestCase):
    def test_action_plan_parses_gui_plan(self) -> None:
        plan = ActionPlan.load(REPO_ROOT / "examples/plans/photoshop_poster_gui.json")
        self.assertEqual(plan.app, "photoshop")
        self.assertEqual(plan.execution_mode, "computer_use")
        self.assertGreaterEqual(len(plan.gui_steps), 1)

    def test_safety_blocks_unauthorized_computer_use(self) -> None:
        plan = ActionPlan.load(REPO_ROOT / "examples/plans/photoshop_poster_gui.json")
        decision = evaluate_safety(plan)
        self.assertFalse(decision.allowed)
        self.assertIn("--allow-computer-use", decision.required_flags)

    def test_dry_run_demo_does_not_write_plan_file(self) -> None:
        target = REPO_ROOT / "outputs/photoshop_demo/photoshop_gui_plan.json"
        if target.exists():
            target.unlink()
        result = run_demo("photoshop", mode="gui")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["written_plan"])
        self.assertFalse(target.exists())

    def test_confirm_write_false_blocks_real_write_plan(self) -> None:
        plan = ActionPlan.from_dict(
            {
                "id": "blocked-write",
                "app": "illustrator",
                "action": "write_svg",
                "goal": "Write an SVG fallback.",
                "execution_mode": "structured_tool",
                "structured_method": "svg",
                "output_paths": ["outputs/illustrator_demo/blocked.svg"],
                "risk_level": "write",
                "dry_run": False,
                "confirm_write": False,
            }
        )
        decision = evaluate_safety(plan)
        self.assertFalse(decision.allowed)
        self.assertIn("--confirm-write", decision.required_flags)

    def test_gui_instructions_are_specific(self) -> None:
        plan = ActionPlan.load(REPO_ROOT / "examples/plans/photoshop_poster_gui.json")
        text = CodexComputerUseAdapter().generate_codex_gui_instructions(plan)
        self.assertIn("Target app: photoshop", text)
        self.assertIn("Open Photoshop", text)
        self.assertIn("take a screenshot", text)

    def test_mock_adapter_returns_execution_result(self) -> None:
        plan = ActionPlan.load(REPO_ROOT / "examples/plans/capcut_timeline_gui.json")
        result = MockComputerUseAdapter().record_gui_result(plan)
        self.assertTrue(result.ok)
        self.assertEqual(result.app, "capcut")
        self.assertGreaterEqual(len(result.screenshot_paths), 1)

    def test_photoshop_gui_demo_can_generate_plan_file(self) -> None:
        result = run_demo("photoshop", mode="gui", confirm_write=True)
        self.assertTrue(result["ok"])
        self.assertTrue((REPO_ROOT / "outputs/photoshop_demo/photoshop_gui_plan.json").exists())

    def test_illustrator_gui_demo_can_generate_plan_and_svg_fallback(self) -> None:
        result = run_demo("illustrator", mode="gui", confirm_write=True)
        self.assertTrue(result["ok"])
        self.assertTrue((REPO_ROOT / "outputs/illustrator_demo/illustrator_gui_plan.json").exists())
        self.assertTrue(
            (REPO_ROOT / "outputs/illustrator_demo/starbridge_ai_gui_demo.svg").exists()
        )

    def test_capcut_gui_demo_can_generate_plan_file(self) -> None:
        result = run_demo("capcut", mode="gui", confirm_write=True)
        self.assertTrue(result["ok"])
        self.assertTrue((REPO_ROOT / "outputs/capcut_demo/capcut_gui_plan.json").exists())

    def test_ci_cli_does_not_start_desktop_apps(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "starbridge_mcp.server", "demo", "photoshop", "--mode", "gui"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertIn("Generated plan only", payload["message"])

    def test_outputs_are_restricted_to_safe_roots(self) -> None:
        self.assertTrue(is_safe_output_path("outputs/evidence/demo.png"))
        self.assertTrue(is_safe_output_path("examples/output/demo.json"))
        self.assertFalse(is_safe_output_path("../private/demo.png"))

    def test_plan_cli_returns_zero(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "starbridge_mcp.server",
                "plan",
                "examples/plans/photoshop_poster_gui.json",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["plan"]["id"], "photoshop-poster-gui")


if __name__ == "__main__":
    unittest.main()
