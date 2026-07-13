from __future__ import annotations

from typing import Any

from starbridge_mcp.core.security import sanitize
from starbridge_mcp.core.tool_registry import BRIDGE_ALIASES

BRIDGE_ROUTES: dict[str, dict[str, Any]] = {
    "photoshop": {
        "keywords": ("photoshop", "修图", "抠图", "图层", "蒙版", "camera raw"),
        "label": "Photoshop 图像编辑桥",
        "probe": "photoshop.session_info",
        "plan": "photoshop.recipe_plan",
        "recipe_id": "photoshop_preview_export",
        "guarded": "photoshop.recipe_run",
    },
    "illustrator": {
        "keywords": ("illustrator", "矢量", "画板", "svg", "image trace"),
        "label": "Illustrator 矢量设计桥",
        "probe": "illustrator.document_info",
        "plan": "illustrator.preflight",
        "recipe_id": "illustrator_trace_preflight",
        "guarded": None,
    },
    "comfyui": {
        "keywords": ("comfyui", "文生图", "图生图", "扩散", "workflow", "工作流"),
        "label": "ComfyUI 图像生成桥",
        "probe": "comfyui.system_probe",
        "queue_snapshot": "comfyui.queue_snapshot",
        "plan": "comfyui.workflow_build_plan",
        "visual_review": "comfy.workflow_visualize",
        "recipe_id": "comfyui_txt2img_lifecycle",
        "guarded": "comfyui.agent_run",
    },
    "autocad_dxf": {
        "keywords": ("autocad", "cad", "dxf", "dwg", "工程图", "制图"),
        "label": "CAD / AutoCAD 工程制图桥",
        "probe": "autocad_dxf.status",
        "plan": "autocad_dxf.create_dxf_plan",
        "recipe_id": "cad_dxf_from_spec",
        "guarded": "autocad_dxf.write_dxf",
    },
    "blender": {
        "keywords": ("blender", "三维", "3d", "建模", "渲染", "场景"),
        "label": "Blender 三维场景桥",
        "probe": "blender.environment_probe",
        "plan": "blender.scene_plan",
        "recipe_id": "blender_scene_evidence",
        "guarded": None,
    },
    "jianying_capcut": {
        "keywords": ("capcut", "剪映", "视频", "字幕", "时间线", "剪辑"),
        "label": "剪映 / CapCut 视频草稿桥",
        "probe": "jianying_capcut.draft_probe",
        "plan": "jianying_capcut.draft_structure",
        "recipe_id": None,
        "guarded": None,
    },
}


def _select_bridge(goal: str, preferred_bridge: str) -> tuple[str, list[str]]:
    safe_preference = {
        "autocad": "autocad_dxf",
        "cad_autocad": "autocad_dxf",
        "cad_dxf": "autocad_dxf",
    }.get(preferred_bridge, preferred_bridge)
    normalized_preference = BRIDGE_ALIASES.get(safe_preference, safe_preference)
    if normalized_preference not in {"", "auto", "all"}:
        if normalized_preference not in BRIDGE_ROUTES:
            raise ValueError(f"unsupported preferred_bridge: {preferred_bridge}")
        return normalized_preference, ["explicit_preference"]

    lowered = goal.casefold()
    scores = {
        bridge: [keyword for keyword in route["keywords"] if keyword.casefold() in lowered]
        for bridge, route in BRIDGE_ROUTES.items()
    }
    ranked = sorted(scores, key=lambda bridge: (-len(scores[bridge]), bridge))
    if not ranked or not scores[ranked[0]]:
        return "all", []
    selected = ranked[0]
    return selected, scores[selected]


def build_control_plan(
    *, goal: str, preferred_bridge: str = "auto", include_guarded_candidates: bool = False
) -> dict[str, Any]:
    clean_goal = goal.strip()
    if not clean_goal:
        raise ValueError("goal is required")
    if len(clean_goal) > 500:
        raise ValueError("goal must be 500 characters or fewer")

    bridge, matched_keywords = _select_bridge(clean_goal, preferred_bridge)
    safety_boundary = {
        "launches_software": False,
        "reads_private_files": False,
        "writes_files": False,
        "confirmation_required_before_real_action": True,
    }
    if bridge == "all":
        return sanitize(
            {
                "ok": True,
                "bridge": "all",
                "action": "control_plan",
                "dry_run": True,
                "goal_summary": clean_goal,
                "needs_clarification": True,
                "message": "目标尚不足以安全选择软件桥；请指定 preferred_bridge。",
                "bridge_options": [
                    {"bridge": name, "label": route["label"]}
                    for name, route in BRIDGE_ROUTES.items()
                ],
                "safety_boundary": safety_boundary,
            }
        )

    route = BRIDGE_ROUTES[bridge]
    recipe_id = route.get("recipe_id")
    review_phase: dict[str, Any] = {
        "phase": "review",
        "tools": ["starbridge.evidence_init"],
        "purpose": "预览脱敏证据字段；当前软件桥没有跨软件 recipe 时不伪造执行证据。",
    }
    if recipe_id:
        review_phase = {
            "phase": "review",
            "tools": ["starbridge.recipe_evidence"],
            "tool_arguments": {
                "starbridge.recipe_evidence": {
                    "recipe_id": recipe_id,
                    "dry_run": True,
                    "confirm_write": False,
                }
            },
            "purpose": "按当前软件 recipe 预览质量门、脱敏摘要和证据要求。",
        }

    discover_phase: dict[str, Any] = {
        "phase": "discover",
        "tools": ["starbridge.safe_roots", route["probe"]],
        "purpose": "确认安全根目录与当前软件桥就绪状态。",
    }
    queue_snapshot = route.get("queue_snapshot")
    if queue_snapshot:
        discover_phase["tools"].append(queue_snapshot)
        discover_phase["tool_arguments"] = {queue_snapshot: {"probe": False}}

    phases: list[dict[str, Any]] = [
        discover_phase,
        {
            "phase": "plan",
            "tools": [route["plan"]],
            "purpose": "只生成或校验结构化计划，不执行真实写入。",
        },
    ]
    visual_review = route.get("visual_review")
    if visual_review:
        phases.append(
            {
                "phase": "visual_review",
                "tools": [visual_review],
                "purpose": "把 compose/build 返回的内联 workflow 转为脱敏 Mermaid，先审图再执行。",
            }
        )
    phases.append(
        {
            "phase": "observe",
            "tools": ["starbridge.operation_context"],
            "required_arguments": ["before_state", "after_state"],
            "purpose": (
                "由调用方传入白名单状态指标，生成 before/after delta、warning 和逻辑 evidence 引用；"
                "不自动读取桌面软件。"
            ),
        }
    )
    phases.append(review_phase)
    guarded = route.get("guarded")
    if include_guarded_candidates and guarded:
        phases.append(
            {
                "phase": "confirmed_action_candidate",
                "tools": [guarded],
                "purpose": "仅列为候选；调用前仍必须满足该工具的确认参数和 sandbox 边界。",
                "requires_confirmation": True,
            }
        )

    quality_gates = [
        "safe_roots_reviewed",
        "no_private_path_leak",
        "dry_run_first",
        "explicit_confirmation_before_write",
        "operation_context_captured",
        "evidence_manifest_valid",
    ]
    if queue_snapshot:
        quality_gates.insert(1, "queue_backpressure_reviewed")

    return sanitize(
        {
            "ok": True,
            "bridge": bridge,
            "action": "control_plan",
            "dry_run": True,
            "goal_summary": clean_goal,
            "selected_route": route["label"],
            "selection_evidence": matched_keywords,
            "needs_clarification": False,
            "phases": phases,
            "quality_gates": quality_gates,
            "safety_boundary": safety_boundary,
        }
    )
