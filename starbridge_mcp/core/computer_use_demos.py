from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starbridge_mcp.core.computer_use import (
    REPO_ROOT,
    ActionPlan,
    CodexComputerUseAdapter,
    GuiStep,
    evaluate_safety,
)
from starbridge_mcp.core.security import sanitize


def _write_json(path: Path, payload: dict[str, Any], *, confirm_write: bool) -> str | None:
    if not confirm_write:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.relative_to(REPO_ROOT).as_posix()


def _write_text(path: Path, text: str, *, confirm_write: bool) -> str | None:
    if not confirm_write:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path.relative_to(REPO_ROOT).as_posix()


def build_photoshop_gui_demo(
    *, allow_computer_use: bool = False, confirm_write: bool = False
) -> ActionPlan:
    return ActionPlan(
        id="photoshop-demo",
        app="photoshop",
        action="create_layered_poster_gui",
        goal="Create a simple layered poster in Photoshop and verify PNG or PSD export from the GUI.",
        execution_mode="computer_use",
        structured_method="none",
        gui_steps=[
            GuiStep(
                "ps-01",
                "Open Photoshop and create a new 1080 by 1350 RGB document.",
                "photoshop",
                "A blank Photoshop document is visible.",
                evidence_required=True,
            ),
            GuiStep(
                "ps-02",
                "Create a solid or gradient background layer named background.",
                "photoshop",
                "The Layers panel contains a background layer.",
            ),
            GuiStep(
                "ps-03",
                "Add a main title text layer near the top named main_title.",
                "photoshop",
                "The title is visible and selected.",
            ),
            GuiStep(
                "ps-04",
                "Add a smaller subtitle text layer named subtitle.",
                "photoshop",
                "The subtitle sits below the title.",
            ),
            GuiStep(
                "ps-05",
                "Add geometric decorative layers such as circles, lines, or rectangles.",
                "photoshop",
                "At least two decorative layers are visible.",
            ),
            GuiStep(
                "ps-06",
                "Add a small explanatory text layer near the bottom.",
                "photoshop",
                "The poster has readable explanatory text.",
            ),
            GuiStep(
                "ps-07",
                "Export a PNG preview or save a PSD under outputs/photoshop_demo/.",
                "photoshop",
                "The export/save dialog targets outputs/photoshop_demo/.",
                fallback_if_failed="Cancel the dialog and record failure.",
                requires_confirmation=True,
                evidence_required=True,
            ),
        ],
        expected_result="A sandbox Photoshop poster plan with layered structure and export verification evidence.",
        output_paths=[
            "outputs/photoshop_demo/starbridge_ps_gui_demo.png",
            "outputs/photoshop_demo/starbridge_ps_gui_demo.psd",
        ],
        needs_screenshot_evidence=True,
        risk_level="write",
        dry_run=not confirm_write,
        confirm_write=confirm_write,
        allow_computer_use=allow_computer_use,
        requires_user_presence=True,
    )


def build_illustrator_gui_demo(
    *, allow_computer_use: bool = False, confirm_write: bool = False
) -> ActionPlan:
    return ActionPlan(
        id="illustrator-demo",
        app="illustrator",
        action="create_vector_layout_gui",
        goal="Create a simple vector layout in Illustrator and verify SVG, PDF, and PNG export from the GUI.",
        execution_mode="hybrid",
        structured_method="svg",
        gui_steps=[
            GuiStep(
                "ai-01",
                "Open Illustrator and create a 1080 by 1080 RGB artboard.",
                "illustrator",
                "A blank square artboard is visible.",
                evidence_required=True,
            ),
            GuiStep(
                "ai-02",
                "Add a title text object at the top.",
                "illustrator",
                "The title is visible on the artboard.",
            ),
            GuiStep(
                "ai-03",
                "Draw two or more lines as layout guides or design accents.",
                "illustrator",
                "Line objects are visible.",
            ),
            GuiStep(
                "ai-04",
                "Add geometric vector symbols such as circles, triangles, or hexagons.",
                "illustrator",
                "Vector symbols are visible.",
            ),
            GuiStep(
                "ai-05",
                "Add annotation text near one symbol.",
                "illustrator",
                "Annotation text is readable.",
            ),
            GuiStep(
                "ai-06",
                "Export SVG, PDF, and PNG into outputs/illustrator_demo/.",
                "illustrator",
                "Export targets outputs/illustrator_demo/.",
                fallback_if_failed="Use the generated SVG fallback file.",
                requires_confirmation=True,
                evidence_required=True,
            ),
        ],
        expected_result="A sandbox Illustrator vector layout plus optional SVG fallback output.",
        output_paths=[
            "outputs/illustrator_demo/starbridge_ai_gui_demo.svg",
            "outputs/illustrator_demo/starbridge_ai_gui_demo.pdf",
            "outputs/illustrator_demo/starbridge_ai_gui_demo.png",
        ],
        needs_screenshot_evidence=True,
        risk_level="write",
        dry_run=not confirm_write,
        confirm_write=confirm_write,
        allow_computer_use=allow_computer_use,
        requires_user_presence=True,
    )


def build_capcut_gui_demo(
    *, allow_computer_use: bool = False, confirm_write: bool = False
) -> ActionPlan:
    return ActionPlan(
        id="capcut-demo",
        app="capcut",
        action="create_timeline_gui_plan",
        goal="Create a safe GUI plan for a short CapCut or Jianying timeline demo using placeholder media.",
        execution_mode="computer_use",
        structured_method="none",
        gui_steps=[
            GuiStep(
                "cc-01",
                "Open Jianying or CapCut.",
                "capcut",
                "The home screen is visible.",
                fallback_if_failed="Record that the app is not installed and keep the plan only.",
                evidence_required=True,
            ),
            GuiStep(
                "cc-02", "Create a new project.", "capcut", "A blank timeline project is visible."
            ),
            GuiStep(
                "cc-03",
                "Import placeholder images or videos from the approved demo asset directory.",
                "capcut",
                "Demo media appears in the media bin.",
                requires_confirmation=True,
            ),
            GuiStep(
                "cc-04",
                "Place one placeholder item on the timeline.",
                "capcut",
                "The media item is visible on the timeline.",
            ),
            GuiStep(
                "cc-05",
                "Add a title text clip.",
                "capcut",
                "The title appears in the preview and on the timeline.",
            ),
            GuiStep(
                "cc-06",
                "Set a simple duration or transition.",
                "capcut",
                "The timeline duration or transition is visible.",
            ),
            GuiStep(
                "cc-07",
                "Inspect the timeline before export and take a screenshot.",
                "capcut",
                "Timeline structure is visible.",
                evidence_required=True,
            ),
        ],
        expected_result="A CapCut/Jianying GUI plan and evidence record; real export is not required.",
        output_paths=["outputs/capcut_demo/timeline_evidence.png"],
        needs_screenshot_evidence=True,
        risk_level="write",
        dry_run=not confirm_write,
        confirm_write=confirm_write,
        allow_computer_use=allow_computer_use,
        requires_user_presence=True,
    )


def illustrator_svg_fallback() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <rect width="1080" height="1080" fill="#f7f7f2"/>
  <text x="90" y="150" font-family="Arial, sans-serif" font-size="68" fill="#111827">StarBridge Vector Demo</text>
  <line x1="90" y1="220" x2="990" y2="220" stroke="#2563eb" stroke-width="10"/>
  <circle cx="260" cy="520" r="120" fill="#10b981" opacity="0.85"/>
  <polygon points="560,390 710,650 410,650" fill="#f59e0b" opacity="0.88"/>
  <rect x="760" y="420" width="170" height="170" fill="#ef4444" opacity="0.82"/>
  <text x="90" y="860" font-family="Arial, sans-serif" font-size="34" fill="#374151">Fallback SVG for CI and machines without Illustrator.</text>
</svg>
"""


def run_demo(
    app: str,
    *,
    mode: str = "gui",
    allow_computer_use: bool = False,
    confirm_write: bool = False,
) -> dict[str, Any]:
    if mode != "gui":
        raise ValueError("only --mode gui is implemented for computer use demos")
    if app == "photoshop":
        plan = build_photoshop_gui_demo(
            allow_computer_use=allow_computer_use, confirm_write=confirm_write
        )
        plan_path = REPO_ROOT / "outputs/photoshop_demo/photoshop_gui_plan.json"
        fallback_path = None
    elif app == "illustrator":
        plan = build_illustrator_gui_demo(
            allow_computer_use=allow_computer_use, confirm_write=confirm_write
        )
        plan_path = REPO_ROOT / "outputs/illustrator_demo/illustrator_gui_plan.json"
        fallback_path = REPO_ROOT / "outputs/illustrator_demo/starbridge_ai_gui_demo.svg"
    elif app == "capcut":
        plan = build_capcut_gui_demo(
            allow_computer_use=allow_computer_use, confirm_write=confirm_write
        )
        plan_path = REPO_ROOT / "outputs/capcut_demo/capcut_gui_plan.json"
        fallback_path = None
    else:
        raise ValueError(f"unsupported demo app: {app}")

    written_plan = _write_json(plan_path, plan.to_dict(), confirm_write=confirm_write)
    written_fallback = None
    if app == "illustrator":
        written_fallback = _write_text(
            fallback_path, illustrator_svg_fallback(), confirm_write=confirm_write
        )

    instructions = CodexComputerUseAdapter().generate_codex_gui_instructions(plan)
    decision = evaluate_safety(plan)
    return sanitize(
        {
            "ok": True,
            "app": app,
            "mode": mode,
            "plan": plan.to_dict(),
            "safety_decision": decision.to_dict(),
            "written_plan": written_plan,
            "written_fallback": written_fallback,
            "gui_instructions": instructions,
            "message": (
                "Now ask Codex to operate the foreground app using the GUI instructions."
                if allow_computer_use
                else "Generated plan only. Re-run with --allow-computer-use to request live GUI operation instructions."
            ),
        }
    )
