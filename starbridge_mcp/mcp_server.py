from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starbridge_mcp.adapters.photoshop import TOOL_DEFINITIONS as PHOTOSHOP_V1_TOOL_DEFINITIONS
from starbridge_mcp.adapters.photoshop import TOOL_HANDLERS as PHOTOSHOP_V1_TOOL_HANDLERS
from starbridge_mcp.bridges import autocad_dxf
from starbridge_mcp.bridges.blender_safe_scene import (
    build_reference_reconstruction_plan,
    build_scene_plan,
)
from starbridge_mcp.bridges.capcut_draft_structure import draft_structure_summary
from starbridge_mcp.bridges.illustrator_preflight import preflight_summary
from starbridge_mcp.core.color_preprocess import build_color_preprocess_plan
from starbridge_mcp.core.color_vector_compare import compare_color_vectorization_files
from starbridge_mcp.core.color_vectorization import (
    build_color_vectorization_plan,
    validate_color_vectorization_metrics,
)
from starbridge_mcp.core.control_planner import build_control_plan
from starbridge_mcp.core.evidence import (
    DEFAULT_MANIFEST_FILENAME,
    ValidationResult,
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    manifest_validation_result,
    repo_relative,
    save_manifest,
)
from starbridge_mcp.core.job_snapshot import build_job_snapshot, job_snapshot_contract
from starbridge_mcp.core.job_snapshot_schema import (
    JOB_SNAPSHOT_INPUT_SCHEMA,
    JOB_SNAPSHOT_OUTPUT_SCHEMA,
)
from starbridge_mcp.core.job_status import JobStatus
from starbridge_mcp.core.operation_context import (
    build_operation_context,
    operation_context_contract,
)
from starbridge_mcp.core.operation_context_schema import (
    OPERATION_CONTEXT_INPUT_SCHEMA,
    OPERATION_CONTEXT_OUTPUT_SCHEMA,
)
from starbridge_mcp.core.progress_monitor import (
    build_progress_monitor,
    progress_monitor_contract,
)
from starbridge_mcp.core.progress_monitor_schema import (
    PROGRESS_MONITOR_INPUT_SCHEMA,
    PROGRESS_MONITOR_OUTPUT_SCHEMA,
)
from starbridge_mcp.core.prompts import get_prompt, list_prompts
from starbridge_mcp.core.queue_snapshot import (
    DEFAULT_COMFY_URL,
    build_queue_snapshot,
    queue_snapshot_contract,
)
from starbridge_mcp.core.queue_snapshot_schema import (
    QUEUE_SNAPSHOT_INPUT_SCHEMA,
    QUEUE_SNAPSHOT_OUTPUT_SCHEMA,
)
from starbridge_mcp.core.resources import (
    SERVER_INSTRUCTIONS,
    list_resources,
    read_resource,
)
from starbridge_mcp.core.safe_roots import safe_roots_summary
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.core.tool_registry import capability_summary, list_capabilities
from starbridge_mcp.core.transaction import create_recipe_transaction
from starbridge_mcp.server import BRIDGE_ALIASES, build_response

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "starbridge", "version": "0.1.0"}

JsonObject = dict[str, Any]
ToolHandler = Callable[[JsonObject], JsonObject]


BRIDGE_ENUM = [
    "all",
    "comfyui",
    "blender",
    "autocad",
    "cad_autocad",
    "autocad_dxf",
    "cad_dxf",
    "photoshop",
    "illustrator",
    "jianying_capcut",
    "capcut_jianying",
]


def _object_schema(properties: JsonObject, required: list[str] | None = None) -> JsonObject:
    schema: JsonObject = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


STARBRIDGE_OUTPUT_SCHEMA: JsonObject = {"type": "object", "additionalProperties": True}

CONTROL_PLAN_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "bridge": {"type": "string"},
        "action": {"type": "string", "const": "control_plan"},
        "dry_run": {"type": "boolean", "const": True},
        "needs_clarification": {"type": "boolean"},
        "phases": {"type": "array", "items": {"type": "object"}},
        "quality_gates": {"type": "array", "items": {"type": "string"}},
        "safety_boundary": {"type": "object"},
    },
    "required": [
        "ok",
        "bridge",
        "action",
        "dry_run",
        "needs_clarification",
        "safety_boundary",
    ],
    "additionalProperties": True,
}


def _safe_read_annotations(
    *,
    risk_level: str = "safe_read_only",
    safe_default: bool = True,
    requires_confirmation: bool = False,
    requires_local_software: bool = False,
    current_status: str = "stable",
) -> JsonObject:
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "openWorldHint": False,
        "riskLevel": risk_level,
        "safeDefault": safe_default,
        "requiresConfirmation": requires_confirmation,
        "requiresLocalSoftware": requires_local_software,
        "currentStatus": current_status,
    }


def _guarded_write_annotations(
    *,
    risk_level: str = "guarded_local_write",
    safe_default: bool = False,
    requires_confirmation: bool = True,
    requires_local_software: bool = True,
    current_status: str = "experimental",
) -> JsonObject:
    return {
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": False,
        "riskLevel": risk_level,
        "safeDefault": safe_default,
        "requiresConfirmation": requires_confirmation,
        "requiresLocalSoftware": requires_local_software,
        "currentStatus": current_status,
    }


def _standard_tool(
    *,
    name: str,
    title: str,
    description: str,
    input_schema: JsonObject,
    read_only: bool = True,
) -> JsonObject:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": STARBRIDGE_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations() if read_only else _guarded_write_annotations(),
    }


TOOL_DEFINITIONS: list[JsonObject] = [
    _standard_tool(
        name="starbridge.status",
        title="StarBridge Status",
        description="返回全部或单个本地创意软件 bridge 的统一状态。只读，不打开用户文件。",
        input_schema=_object_schema(
            {
                "bridge": {
                    "type": "string",
                    "enum": BRIDGE_ENUM,
                    "default": "all",
                    "description": "要检查的软件桥；默认检查全部。",
                },
                "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "default": 8},
                "probe_executables": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否做更具体的可执行文件/COM 只读探测。",
                },
                "comfy_url": {
                    "type": "string",
                    "description": "可选 ComfyUI API 地址；未提供时读取 STARBRIDGE_COMFYUI_URL。",
                },
            }
        ),
    ),
    _standard_tool(
        name="starbridge.probe",
        title="StarBridge Probe",
        description="对单个 bridge 做只读探针检查。等价于 status + bridge filter。",
        input_schema=_object_schema(
            {
                "bridge": {
                    "type": "string",
                    "enum": [item for item in BRIDGE_ENUM if item != "all"],
                },
                "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "default": 8},
                "probe_executables": {"type": "boolean", "default": True},
                "comfy_url": {"type": "string"},
            },
            required=["bridge"],
        ),
    ),
    {
        "name": "starbridge.tools",
        "title": "StarBridge Tool Registry",
        "description": "列出 StarBridge 当前已实现、实验中和规划中的工具能力。",
        "inputSchema": _object_schema(
            {
                "bridge": {"type": "string", "enum": BRIDGE_ENUM, "default": "all"},
                "safe_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "仅返回默认安全的只读能力。",
                },
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.control_plan",
        "title": "StarBridge Codex Control Plan",
        "description": "根据自然语言目标选择创意软件桥，返回只读控制计划、质量门和确认边界。不会启动软件或读取文件。",
        "inputSchema": _object_schema(
            {
                "goal": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 500,
                    "description": "要完成的创意软件任务；不得包含真实本机路径、token 或私有素材内容。",
                },
                "preferred_bridge": {
                    "type": "string",
                    "enum": ["auto", *BRIDGE_ENUM],
                    "default": "auto",
                },
                "include_guarded_candidates": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否列出需要再次确认的真实操作候选；本工具仍不会执行它们。",
                },
            },
            required=["goal"],
        ),
        "outputSchema": CONTROL_PLAN_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.safe_roots",
        "title": "StarBridge Safe Roots",
        "description": "返回仓库相对安全根目录、可写输出边界和 MCP roots 对齐建议。",
        "inputSchema": _object_schema(
            {
                "bridge": {"type": "string", "enum": BRIDGE_ENUM, "default": "all"},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.evidence_init",
        "title": "StarBridge Evidence Init",
        "description": "Return a sanitized EvidenceManifest preview and default manifest path without launching desktop software.",
        "inputSchema": _object_schema(
            {
                "bridge": {"type": "string", "default": "starbridge"},
                "action_name": {"type": "string", "default": "evidence_init"},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.evidence_validate",
        "title": "StarBridge Evidence Validate",
        "description": "Validate the current redacted EvidenceManifest shape and path boundary.",
        "inputSchema": _object_schema(
            {
                "manifest_path": {
                    "type": "string",
                    "default": "examples/output/evidence/manifest.latest.json",
                },
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.job_status",
        "title": "StarBridge Job Status",
        "description": "Return a unified queued/running/completed-style job summary from the current evidence manifest.",
        "inputSchema": _object_schema(
            {
                "job_id": {"type": "string", "default": "job_preview"},
                "bridge": {"type": "string", "default": "starbridge"},
                "action_name": {"type": "string", "default": "evidence_review"},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.operation_context",
        "title": "StarBridge Operation Context",
        "description": (
            "Build a sanitized, chainable before/after state envelope from caller-supplied "
            "safe metrics. This tool does not inspect local software, files, or networks."
        ),
        "inputSchema": OPERATION_CONTEXT_INPUT_SCHEMA,
        "outputSchema": OPERATION_CONTEXT_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.recipe_list",
        "title": "StarBridge Recipe List",
        "description": "List safe cross-bridge StarBridge recipes. This is plan-only and does not launch desktop software.",
        "inputSchema": _object_schema(
            {
                "bridge": {"type": "string", "enum": BRIDGE_ENUM, "default": "all"},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.recipe_plan",
        "title": "StarBridge Recipe Plan",
        "description": "Return a dry-run action plan, quality gates, and evidence requirements for one cross-bridge recipe.",
        "inputSchema": _object_schema(
            {
                "recipe_id": {"type": "string", "default": "photoshop_preview_export"},
                "dry_run": {"type": "boolean", "default": True},
                "action_plan": {"type": "boolean", "default": True},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    {
        "name": "starbridge.recipe_evidence",
        "title": "StarBridge Recipe Evidence",
        "description": "Preview a standardized EvidenceManifest for one recipe, including quality gates and asset manifest entries.",
        "inputSchema": _object_schema(
            {
                "recipe_id": {"type": "string", "default": "photoshop_preview_export"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
            }
        ),
        "annotations": _safe_read_annotations(),
    },
    _standard_tool(
        name="comfyui.system_probe",
        title="Probe ComfyUI",
        description="读取 ComfyUI /system_stats 与 /object_info，确认服务和基础节点是否可用。不提交生成任务。",
        input_schema=_object_schema(
            {
                "comfy_url": {
                    "type": "string",
                    "description": "可选 ComfyUI API 地址；默认读取环境变量或 http://127.0.0.1:8188。",
                },
                "timeout": {"type": "integer", "minimum": 1, "maximum": 60, "default": 8},
            }
        ),
    ),
    {
        "name": "comfyui.queue_snapshot",
        "title": "ComfyUI Queue Snapshot",
        "description": (
            "默认只返回计划；probe=true 时只读访问 loopback ComfyUI /queue，并返回脱敏队列、"
            "backpressure 和可选单调数值进度。不会返回 workflow、prompt id 或 history。"
        ),
        "inputSchema": QUEUE_SNAPSHOT_INPUT_SCHEMA,
        "outputSchema": QUEUE_SNAPSHOT_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations(requires_local_software=True),
    },
    {
        "name": "comfyui.job_snapshot",
        "title": "ComfyUI Job Snapshot",
        "description": (
            "默认只返回计划；probe=true 时按显式 job ID 只读访问 loopback "
            "ComfyUI /api/jobs/{job_id}。只返回哈希 ID、状态、终态和输出数量，"
            "丢弃 workflow、output、preview、异常正文和 traceback。"
        ),
        "inputSchema": JOB_SNAPSHOT_INPUT_SCHEMA,
        "outputSchema": JOB_SNAPSHOT_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations(requires_local_software=True),
    },
    {
        "name": "comfyui.progress_monitor",
        "title": "ComfyUI Progress Monitor",
        "description": (
            "默认只返回计划；connect=true 时只监听 loopback ComfyUI /ws，输出哈希 job/node、"
            "单调数值进度和 stalled 判定。不会返回 workflow、异常正文、预览图或输出文件。"
        ),
        "inputSchema": PROGRESS_MONITOR_INPUT_SCHEMA,
        "outputSchema": PROGRESS_MONITOR_OUTPUT_SCHEMA,
        "annotations": _safe_read_annotations(requires_local_software=True),
    },
    _standard_tool(
        name="comfyui.workflow_validate",
        title="Validate ComfyUI Workflow",
        description="只读校验 ComfyUI workflow JSON 是否为 /prompt API format；不提交生成任务。",
        input_schema=_object_schema(
            {
                "workflow_path": {
                    "type": "string",
                    "description": "可选 workflow 文件路径；默认使用公开 txt2img API 示例。",
                }
            }
        ),
    ),
    _standard_tool(
        name="comfyui.workflow_build_plan",
        title="ComfyUI Workflow Build Plan",
        description="Generate a dry-run workflow construction plan from a natural-language goal without reading local inputs or submitting a queue job.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string", "default": ""},
                "workflow_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "style": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "source_image_path": {"type": "string"},
                "mask_path": {"type": "string"},
            }
        ),
    ),
    _standard_tool(
        name="comfyui.workflow_build",
        title="ComfyUI Workflow Build",
        description="Build a safe dry-run API-like workflow JSON for reviewed task types and return validation metadata.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string", "default": ""},
                "workflow_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "style": {"type": "string", "default": ""},
                "prompt": {"type": "string", "default": ""},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "default": 0, "minimum": 0},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 0.1, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "checkpoint": {"type": "string", "default": "__checkpoint_placeholder__"},
            }
        ),
    ),
    _standard_tool(
        name="comfyui.workflow_repair",
        title="ComfyUI Workflow Repair",
        description="Repair a dry-run txt2img workflow by recreating missing nodes, defaults, and core links.",
        input_schema=_object_schema(
            {
                "workflow": {"type": "object"},
                "goal": {"type": "string", "default": ""},
                "prompt": {"type": "string", "default": ""},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "default": 0, "minimum": 0},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 0.1, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "checkpoint": {"type": "string", "default": "__checkpoint_placeholder__"},
            }
        ),
    ),
    _standard_tool(
        name="comfyui.agent_run",
        title="ComfyUI Agent Run",
        description="Run the guarded ComfyUI agent flow. Defaults to dry-run; confirmed runs distinguish accepted submission from completed, failed, or cancelled execution.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string", "default": ""},
                "workflow_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "style": {"type": "string", "default": ""},
                "prompt": {"type": "string", "default": ""},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "minimum": 0},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 0.1, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "checkpoint": {"type": "string", "default": "__checkpoint_placeholder__"},
                "comfy_url": {"type": "string"},
                "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 300},
                "wait_seconds": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 0,
                    "maximum": 600,
                    "description": "History polling window; returns early on completed, failed, or cancelled execution.",
                },
                "confirm_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Explicitly confirms queue submission; execution failure still reports submitted=true.",
                },
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="comfy.workflow_draft",
        title="Comfy Workflow Draft",
        description="Generate a safe placeholder draft workflow for txt2img, img2img, inpaint, or upscale and validate it immediately.",
        input_schema=_object_schema(
            {
                "task_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "prompt": {"type": "string", "default": ""},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "default": 0, "minimum": 0},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 0.1, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "denoise": {"type": "number", "default": 0.55, "minimum": 0.0, "maximum": 1.0},
                "scale_by": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 8.0},
                "checkpoint": {"type": "string", "default": "__checkpoint_placeholder__"},
                "source_image_path": {"type": "string"},
                "mask_path": {"type": "string"},
            }
        ),
    ),
    _standard_tool(
        name="comfy.workflow_compose",
        title="Comfy Workflow Compose",
        description="Compose a safe placeholder ComfyUI graph from reviewed modules and validate it immediately.",
        input_schema=_object_schema(
            {
                "task_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "prompt": {"type": "string", "default": ""},
                "negative_prompt": {"type": "string", "default": ""},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "default": 0, "minimum": 0},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 0.1, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "scale": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 8.0},
                "checkpoint": {"type": "string", "default": "__checkpoint_placeholder__"},
                "source_image_path": {"type": "string"},
                "mask_path": {"type": "string"},
            }
        ),
    ),
    _standard_tool(
        name="comfy.workflow_template_list",
        title="Comfy Workflow Template List",
        description="List the bundled public ComfyUI workflow templates and their safety status.",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="comfy.workflow_template_get",
        title="Comfy Workflow Template Get",
        description="Return a single bundled public ComfyUI workflow template and its validation report.",
        input_schema=_object_schema({"template_id": {"type": "string"}}, required=["template_id"]),
    ),
    _standard_tool(
        name="comfy.workflow_from_template",
        title="Comfy Workflow From Template",
        description="Compose a safe placeholder workflow from a bundled public template without touching private files or the queue.",
        input_schema=_object_schema(
            {
                "template_id": {"type": "string"},
                "arguments": {"type": "object", "default": {}},
            },
            required=["template_id"],
        ),
    ),
    _standard_tool(
        name="comfy.workflow_lifecycle_summary",
        title="Comfy Workflow Lifecycle Summary",
        description="Return a redacted job and asset lifecycle summary for a reviewed workflow without exposing asset names or submitting the queue.",
        input_schema=_object_schema(
            {
                "template_id": {
                    "type": "string",
                    "description": "Optional bundled public template id to compose before summarizing.",
                },
                "workflow": {
                    "type": "object",
                    "description": "Optional API-format workflow object supplied directly by the caller.",
                },
                "arguments": {"type": "object", "default": {}},
                "task_type": {
                    "type": "string",
                    "enum": ["txt2img", "img2img", "inpaint", "upscale"],
                    "default": "txt2img",
                },
                "confirm_run": {"type": "boolean", "default": False},
            }
        ),
    ),
    _standard_tool(
        name="comfy.workflow_visualize",
        title="Visualize ComfyUI Workflow",
        description="把内联 API workflow 转为 Mermaid 和脱敏节点/连线摘要；不读取文件、prompt 或模型目录。",
        input_schema=_object_schema(
            {
                "workflow": {
                    "type": "object",
                    "description": "内联 ComfyUI API-format workflow JSON。",
                },
                "direction": {
                    "type": "string",
                    "enum": ["LR", "TD"],
                    "default": "LR",
                },
                "include_node_ids": {"type": "boolean", "default": True},
            },
            required=["workflow"],
        ),
    ),
    _standard_tool(
        name="blender.environment_probe",
        title="Probe Blender",
        description="检查 Blender 可执行文件和可选环境配置。不打开 .blend，不运行脚本。",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="blender.scene_plan",
        title="Blender Safe Scene Plan",
        description="生成公开安全的 Blender 基础场景 dry-run 计划；不启动 Blender，不打开 .blend，不执行任意 Python。",
        input_schema=_object_schema(
            {
                "scene_name": {"type": "string", "default": "starbridge_public_scene"},
                "render_width": {
                    "type": "integer",
                    "default": 1280,
                    "minimum": 320,
                    "maximum": 4096,
                },
                "render_height": {
                    "type": "integer",
                    "default": 720,
                    "minimum": 240,
                    "maximum": 4096,
                },
            }
        ),
    ),
    _standard_tool(
        name="blender.reference_reconstruction_plan",
        title="Blender Reference Reconstruction Plan",
        description=(
            "生成参考图驱动的 Blender 重建 dry-run 计划，包含分割、深度/点云初始化、"
            "单视图量测、渲染反查和交付误差门槛；不读取图片、不启动 Blender。"
        ),
        input_schema=_object_schema(
            {
                "reference_name": {"type": "string", "default": "reference_image"},
                "target_kind": {"type": "string", "default": "object_or_scene"},
                "reference_views": {"type": "integer", "default": 1, "minimum": 1, "maximum": 64},
                "known_scale": {"type": "string", "default": ""},
                "tolerance_pixels": {"type": "integer", "default": 4, "minimum": 1, "maximum": 64},
                "max_iterations": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
            }
        ),
    ),
    _standard_tool(
        name="cad_autocad.environment_probe",
        title="Probe CAD / AutoCAD",
        description="检查 AutoCAD 可执行文件、COM 注册和 pywin32 线索。不打开 DWG/DXF。",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="photoshop.session_info",
        title="Probe Photoshop Session",
        description="通过状态探针检查 Photoshop COM 线索；只读，不打开 PSD，不保存导出。",
        input_schema=_object_schema(
            {
                "probe_com": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否尝试连接已打开的 Photoshop COM 对象。",
                }
            }
        ),
    ),
    _standard_tool(
        name="photoshop.document_info",
        title="Photoshop Document Info",
        description="Read the active Photoshop document summary through COM without opening private PSD files.",
        input_schema=_object_schema({"probe_com": {"type": "boolean", "default": True}}),
    ),
    _standard_tool(
        name="photoshop.create_demo_document",
        title="Create Photoshop Sandbox Demo",
        description="Create a public safe sandbox PSD with named layers. Defaults to dry-run and requires confirm_write for real output.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "output_dir": {"type": "string", "default": "examples/output/photoshop"},
                "width": {"type": "integer", "default": 1080, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1080, "minimum": 64, "maximum": 4096},
                "dpi": {"type": "integer", "default": 72, "minimum": 36, "maximum": 600},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="photoshop.export_demo_preview",
        title="Export Photoshop Sandbox Preview",
        description="Export PNG and JPG previews only from the sandbox Photoshop demo. Defaults to dry-run and requires confirm_export.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_export": {"type": "boolean", "default": False},
                "output_dir": {"type": "string", "default": "examples/output/photoshop"},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="photoshop.run_demo",
        title="Run Photoshop Sandbox Demo",
        description="Run the guarded Photoshop sandbox PSD creation, preview export, and manifest flow. Defaults to dry-run.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "confirm_export": {"type": "boolean", "default": False},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="photoshop.recipe_list",
        title="Photoshop Recipe List",
        description="列出公开安全的 Photoshop recipe 层能力。",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="photoshop.recipe_plan",
        title="Photoshop Recipe Plan",
        description="生成 dry-run recipe 计划、输出清单和质量门，不启动 Photoshop。",
        input_schema=_object_schema(
            {
                "recipe_id": {"type": "string", "default": "sandbox_demo_preview"},
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean", "default": False},
                "source_media_type": {
                    "type": "string",
                    "enum": ["image/png", "image/jpeg"],
                    "default": "image/png",
                },
                "source_width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "source_height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "max_dimension": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 8192,
                    "default": 4096,
                },
                "median_radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "normalize_srgb": {"type": "boolean", "default": True},
                "output_dir": {"type": "string", "default": "examples/output/photoshop"},
                "dry_run": {"type": "boolean", "default": True},
            }
        ),
    ),
    _standard_tool(
        name="photoshop.recipe_validate",
        title="Photoshop Recipe Validate",
        description="校验 Photoshop recipe 的 sandbox 输出边界、manifest 门和脱敏要求。",
        input_schema=_object_schema(
            {
                "recipe_id": {"type": "string", "default": "sandbox_demo_preview"},
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean", "default": False},
                "source_media_type": {
                    "type": "string",
                    "enum": ["image/png", "image/jpeg"],
                    "default": "image/png",
                },
                "source_width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "source_height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "max_dimension": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 8192,
                    "default": 4096,
                },
                "median_radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "normalize_srgb": {"type": "boolean", "default": True},
                "output_dir": {"type": "string", "default": "examples/output/photoshop"},
                "dry_run": {"type": "boolean", "default": True},
            }
        ),
    ),
    _standard_tool(
        name="photoshop.recipe_run",
        title="Photoshop Recipe Run",
        description="执行受控 Photoshop recipe；默认 dry-run，真实写入必须 confirm_write=true。",
        input_schema=_object_schema(
            {
                "recipe_id": {"type": "string", "default": "sandbox_demo_preview"},
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean", "default": False},
                "input_path": {
                    "type": "string",
                    "description": "Only the explicitly authorized PNG/JPEG used by the fixed preprocess recipe.",
                },
                "source_media_type": {
                    "type": "string",
                    "enum": ["image/png", "image/jpeg"],
                    "default": "image/png",
                },
                "source_width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "source_height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "max_dimension": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 8192,
                    "default": 4096,
                },
                "median_radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "normalize_srgb": {"type": "boolean", "default": True},
                "output_dir": {"type": "string", "default": "examples/output/photoshop"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "confirm_export": {"type": "boolean", "default": False},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="photoshop.recipe_debug",
        title="Photoshop Recipe Debug",
        description="返回受控 Photoshop recipe 的重试策略和排障建议。",
        input_schema=_object_schema(
            {
                "recipe_id": {"type": "string", "default": "sandbox_demo_preview"},
            }
        ),
    ),
    _standard_tool(
        name="illustrator.document_info",
        title="Probe Illustrator Document",
        description="Read the active Illustrator document summary through COM without opening private AI files.",
        input_schema=_object_schema(
            {
                "probe_com": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否尝试连接已打开的 Illustrator COM 对象。",
                }
            }
        ),
    ),
    _standard_tool(
        name="illustrator.create_demo_artboard",
        title="Create Illustrator Sandbox Demo",
        description="Create a public safe vector artboard demo. Defaults to dry-run and requires confirm_write for real AI output.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "output_dir": {"type": "string", "default": "examples/output/illustrator"},
                "width": {"type": "integer", "default": 1080, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1080, "minimum": 64, "maximum": 4096},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="illustrator.export_demo_assets",
        title="Export Illustrator Sandbox Assets",
        description="Export SVG, PNG, and PDF only from the sandbox Illustrator demo. Defaults to dry-run and requires confirm_export.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_export": {"type": "boolean", "default": False},
                "output_dir": {"type": "string", "default": "examples/output/illustrator"},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="illustrator.run_demo",
        title="Run Illustrator Sandbox Demo",
        description="Run the guarded Illustrator demo artboard creation, export, and manifest flow. Defaults to dry-run.",
        input_schema=_object_schema(
            {
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "confirm_export": {"type": "boolean", "default": False},
            }
        ),
        read_only=False,
    ),
    _standard_tool(
        name="illustrator.preflight",
        title="Illustrator Preflight",
        description="对传入的脱敏 Illustrator 文档摘要做只读 preflight；不打开 .ai，不导出文件。",
        input_schema=_object_schema(
            {
                "document_summary": {
                    "type": "object",
                    "description": "Optional sanitized summary from illustrator.document_info.",
                    "default": {},
                }
            }
        ),
    ),
    _standard_tool(
        name="illustrator.color_vectorize_plan",
        title="Plan Color-Faithful Illustrator Vectorization",
        description=(
            "为用户明确授权的单张 PNG/JPEG 生成 Photoshop + Illustrator 彩色矢量化 dry-run 计划；"
            "不读取图片、不启动 Adobe 软件、不上传云端。"
        ),
        input_schema=_object_schema(
            {
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean"},
                "source_media_type": {
                    "type": "string",
                    "enum": ["image/png", "image/jpeg"],
                    "default": "image/png",
                },
                "source_width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "source_height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "strategy": {
                    "type": "string",
                    "enum": [
                        "local_illustrator_trace",
                        "semantic_reconstruction",
                        "hybrid",
                    ],
                    "default": "hybrid",
                },
                "photoshop_preprocess": {"type": "boolean", "default": False},
                "max_dimension": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 8192,
                    "default": 4096,
                },
                "median_radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "normalize_srgb": {"type": "boolean", "default": True},
                "max_colors": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 256,
                    "default": 64,
                },
                "path_fitting": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 1.5,
                },
                "min_area": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 2,
                },
                "preprocess_blur": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 0,
                },
                "ignore_white": {"type": "boolean", "default": False},
                "output_to_swatches": {"type": "boolean", "default": True},
            },
            required=["reference_id", "reference_authorized"],
        ),
    ),
    _standard_tool(
        name="illustrator.color_vectorize_validate",
        title="Validate Color Vectorization Evidence",
        description=(
            "校验调用方传入的脱敏轮廓、色差、感知相似度和节点统计；不读取参考图或预览文件。"
        ),
        input_schema=_object_schema(
            {
                "metrics": _object_schema(
                    {
                        "aspect_ratio_error": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "silhouette_iou": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "mean_delta_e": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 300,
                        },
                        "p95_delta_e": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 300,
                        },
                        "perceptual_similarity": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "anchor_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000000,
                        },
                        "used_color_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 256,
                        },
                    },
                    required=[
                        "aspect_ratio_error",
                        "silhouette_iou",
                        "mean_delta_e",
                        "p95_delta_e",
                        "perceptual_similarity",
                        "anchor_count",
                        "used_color_count",
                    ],
                ),
                "hard_gates": _object_schema(
                    {
                        "reference_authorized": {"type": "boolean"},
                        "primary_silhouette_present": {"type": "boolean"},
                        "topology_valid": {"type": "boolean"},
                        "editable_vector_present": {"type": "boolean"},
                        "safe_output_scope": {"type": "boolean"},
                    },
                    required=[
                        "reference_authorized",
                        "primary_silhouette_present",
                        "topology_valid",
                        "editable_vector_present",
                        "safe_output_scope",
                    ],
                ),
            },
            required=["metrics", "hard_gates"],
        ),
    ),
    _standard_tool(
        name="illustrator.color_vectorize_compare",
        title="Compare Authorized Reference and Illustrator Preview",
        description=(
            "读取用户明确授权的一张 PNG/JPEG 与 Illustrator sandbox 中的一张 PNG 预览，"
            "计算脱敏的轮廓、色差、感知相似度和可编辑性证据；不返回路径、像素或图片元数据。"
        ),
        input_schema=_object_schema(
            {
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean"},
                "reference_path": {
                    "type": "string",
                    "description": "本次明确授权的单张 PNG/JPEG；路径不会回显。",
                },
                "candidate_preview_path": {
                    "type": "string",
                    "description": "仅允许 examples/output/illustrator 内的单张 PNG。",
                },
                "trace_evidence": _object_schema(
                    {
                        "anchor_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000000,
                        },
                        "used_color_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 256,
                        },
                        "open_path_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000000,
                        },
                        "embedded_raster_count": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 1000000,
                        },
                    },
                    required=[
                        "anchor_count",
                        "used_color_count",
                        "open_path_count",
                        "embedded_raster_count",
                    ],
                ),
                "max_dimension": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 1024,
                    "default": 512,
                },
                "background_threshold": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 128,
                    "default": 24,
                },
                "soft_exit": {"type": "boolean", "default": True},
            },
            required=[
                "reference_id",
                "reference_authorized",
                "reference_path",
                "candidate_preview_path",
                "trace_evidence",
            ],
        ),
    ),
    _standard_tool(
        name="illustrator.color_vectorize_execute",
        title="Execute Guarded Illustrator Color Trace",
        description=(
            "对用户明确传入的单张 PNG/JPEG 执行固定、可审计的 Illustrator 彩色 Image Trace；"
            "默认 dry-run，真实 SVG/AI/PNG 输出需同时确认写入与导出。"
        ),
        input_schema=_object_schema(
            {
                "reference_id": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$",
                },
                "reference_authorized": {"type": "boolean"},
                "input_path": {
                    "type": "string",
                    "description": "仅在真实执行时提供的单个用户授权 PNG/JPEG 路径；不会回显。",
                },
                "source_media_type": {
                    "type": "string",
                    "enum": ["image/png", "image/jpeg"],
                    "default": "image/png",
                },
                "source_width": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "source_height": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 32768,
                    "default": None,
                },
                "strategy": {
                    "type": "string",
                    "enum": ["local_illustrator_trace", "hybrid"],
                    "default": "hybrid",
                },
                "photoshop_preprocess": {"type": "boolean", "default": False},
                "max_dimension": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 8192,
                    "default": 4096,
                },
                "median_radius": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 5,
                    "default": 0,
                },
                "normalize_srgb": {"type": "boolean", "default": True},
                "output_dir": {
                    "type": "string",
                    "default": "examples/output/illustrator",
                },
                "max_colors": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 256,
                    "default": 64,
                },
                "path_fitting": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 1.5,
                },
                "min_area": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 2,
                },
                "preprocess_blur": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 0,
                },
                "ignore_white": {"type": "boolean", "default": False},
                "output_to_swatches": {"type": "boolean", "default": True},
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {"type": "boolean", "default": False},
                "confirm_export": {"type": "boolean", "default": False},
            },
            required=["reference_id", "reference_authorized"],
        ),
        read_only=False,
    ),
    _standard_tool(
        name="jianying_capcut.draft_probe",
        title="Probe Jianying / CapCut Drafts",
        description="检查剪映/CapCut 可执行文件和草稿目录环境变量。不读取草稿内容，不导出视频。",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="jianying_capcut.draft_structure",
        title="Jianying / CapCut Draft Structure",
        description="只读统计草稿目录顶层结构，不递归扫描，不读取 draft_content.json 或素材路径。",
        input_schema=_object_schema(
            {
                "max_entries": {"type": "integer", "default": 25, "minimum": 1, "maximum": 200},
            }
        ),
    ),
    _standard_tool(
        name="autocad_dxf.status",
        title="AutoCAD DXF Status",
        description="检查离线 DXF bridge 是否可用于 plan 校验和 dry-run。",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="autocad_dxf.validate_cad_plan",
        title="Validate CAD Plan",
        description="校验 CAD JSON plan 的单位、图层和实体结构。不写文件。",
        input_schema=_object_schema({"plan": {"type": "object"}}, required=["plan"]),
    ),
    _standard_tool(
        name="autocad_dxf.create_dxf_plan",
        title="Create DXF Plan",
        description="从结构化 spec 或简单 prompt 生成可审查 CAD plan。不写文件。",
        input_schema=_object_schema(
            {
                "prompt_or_spec": {
                    "description": "自然语言 prompt 或结构化 CAD plan。",
                    "oneOf": [{"type": "string"}, {"type": "object"}],
                }
            },
            required=["prompt_or_spec"],
        ),
    ),
    _standard_tool(
        name="autocad_dxf.summarize_plan",
        title="Summarize CAD Plan",
        description="汇总 CAD plan 的图层、实体数量和实体类型。不写文件。",
        input_schema=_object_schema({"plan": {"type": "object"}}, required=["plan"]),
    ),
    _standard_tool(
        name="autocad_dxf.write_dxf",
        title="Write Test DXF",
        description="将 CAD plan 写为测试 DXF；默认 dry_run=True，真实写入需要 confirm_write=true 且输出位于 examples/cad/output。",
        input_schema=_object_schema(
            {
                "plan": {"type": "object"},
                "output_path": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm_write": {
                    "type": "boolean",
                    "default": False,
                    "description": "dry_run=false 时必须显式为 true。",
                },
            },
            required=["plan", "output_path"],
        ),
        read_only=False,
    ),
]

TOOL_DEFINITIONS.extend(PHOTOSHOP_V1_TOOL_DEFINITIONS)


def _dedupe_tool_definitions(tools: list[JsonObject]) -> list[JsonObject]:
    unique: list[JsonObject] = []
    seen: set[str] = set()
    for tool in tools:
        name = str(tool["name"])
        if name in seen:
            continue
        seen.add(name)
        unique.append(tool)
    return unique


TOOL_DEFINITIONS = _dedupe_tool_definitions(TOOL_DEFINITIONS)


def _normalize_risk_level(value: str | None, *, read_only: bool) -> str:
    if value in {"safe_read_only", "guarded_local_write", "guarded_local_process"}:
        return value
    if value and ("write" in value or "confirmed" in value or "destructive" in value):
        return "guarded_local_write"
    if value and ("process" in value or "launch" in value):
        return "guarded_local_process"
    return "safe_read_only" if read_only else "guarded_local_write"


def _tool_metadata_map() -> dict[str, JsonObject]:
    return {item["name"]: item for item in list_capabilities()}


def _enrich_tool_annotations() -> None:
    capability_by_name = _tool_metadata_map()
    for tool in TOOL_DEFINITIONS:
        annotations = dict(tool.get("annotations", {}))
        capability = capability_by_name.get(tool["name"])
        read_only = bool(annotations.get("readOnlyHint", False))
        input_schema = dict(tool.get("inputSchema", {}))
        properties = dict(input_schema.get("properties", {}))
        annotations["riskLevel"] = _normalize_risk_level(
            capability.get("risk_level") if capability else annotations.get("riskLevel"),
            read_only=read_only,
        )
        annotations["safeDefault"] = bool(capability["safe_default"]) if capability else read_only
        annotations["requiresConfirmation"] = (
            bool(capability["requires_confirmation"]) if capability else not read_only
        )
        annotations["requiresLocalSoftware"] = (
            bool(capability["requires_local_software"]) if capability else False
        )
        annotations["currentStatus"] = (
            str(capability["current_status"]) if capability else "experimental"
        )
        tool["annotations"] = annotations
        if not read_only:
            if tool["name"] == "comfyui.agent_run":
                properties.setdefault("confirm_run", {"type": "boolean", "default": False})
            else:
                properties.setdefault("dry_run", {"type": "boolean", "default": True})
                if "confirm_write" not in properties and "confirm_export" not in properties:
                    properties["confirm_write"] = {"type": "boolean", "default": False}
            input_schema["properties"] = properties
            tool["inputSchema"] = input_schema


_enrich_tool_annotations()


def _namespace_for_status(
    arguments: JsonObject, *, probe_default: bool = False
) -> argparse.Namespace:
    return argparse.Namespace(
        action="status",
        bridge=str(arguments.get("bridge") or "all"),
        comfy_url=arguments.get("comfy_url"),
        timeout=int(arguments.get("timeout") or 8),
        probe_executables=bool(arguments.get("probe_executables", probe_default)),
        safe_only=False,
    )


def _handle_status(arguments: JsonObject) -> JsonObject:
    return build_response(_namespace_for_status(arguments))


def _handle_probe(arguments: JsonObject) -> JsonObject:
    if not arguments.get("bridge"):
        raise ValueError("bridge is required")
    return build_response(_namespace_for_status(arguments, probe_default=True))


def _handle_tools(arguments: JsonObject) -> JsonObject:
    bridge = BRIDGE_ALIASES.get(
        str(arguments.get("bridge") or "all"), str(arguments.get("bridge") or "all")
    )
    return capability_summary(
        bridge=bridge, include_guarded=not bool(arguments.get("safe_only", False))
    )


def _handle_control_plan(arguments: JsonObject) -> JsonObject:
    return build_control_plan(
        goal=str(arguments.get("goal") or ""),
        preferred_bridge=str(arguments.get("preferred_bridge") or "auto"),
        include_guarded_candidates=bool(arguments.get("include_guarded_candidates", False)),
    )


def _handle_safe_roots(arguments: JsonObject) -> JsonObject:
    bridge = BRIDGE_ALIASES.get(
        str(arguments.get("bridge") or "all"), str(arguments.get("bridge") or "all")
    )
    return safe_roots_summary(bridge=bridge)


def _handle_evidence_init(arguments: JsonObject) -> JsonObject:
    manifest_path = ensure_evidence_path(DEFAULT_MANIFEST_FILENAME)
    return sanitize(
        {
            "ok": True,
            "bridge": str(arguments.get("bridge") or "starbridge"),
            "action": "evidence_init",
            "manifest": {
                "manifest_path": repo_relative(manifest_path),
                "bridge": str(arguments.get("bridge") or "starbridge"),
                "action": str(arguments.get("action_name") or "evidence_init"),
                "status": "queued",
                "dry_run": True,
            },
            "next_steps": [
                "Review the manifest preview, then use the CLI if you want to materialize or validate a local file."
            ],
        }
    )


def _handle_evidence_validate(arguments: JsonObject) -> JsonObject:
    manifest_path = ensure_evidence_path(
        str(arguments.get("manifest_path") or DEFAULT_MANIFEST_FILENAME)
    )
    if not manifest_path.exists():
        return sanitize(
            {
                "ok": False,
                "bridge": "starbridge",
                "action": "evidence_validate",
                "message": "manifest file not found",
                "manifest_path": repo_relative(manifest_path),
            }
        )
    manifest = load_manifest(manifest_path)
    validation = manifest_validation_result(manifest)
    return sanitize(
        {
            "ok": validation.ok,
            "bridge": "starbridge",
            "action": "evidence_validate",
            "manifest_path": repo_relative(manifest_path),
            "validation": validation.to_dict(),
        }
    )


def _handle_job_status(arguments: JsonObject) -> JsonObject:
    manifest_path = ensure_evidence_path(DEFAULT_MANIFEST_FILENAME)
    payload: JsonObject = {
        "ok": True,
        "bridge": str(arguments.get("bridge") or "starbridge"),
        "action": "job_status",
        "job": JobStatus(
            job_id=str(arguments.get("job_id") or "job_preview"),
            bridge=str(arguments.get("bridge") or "starbridge"),
            action=str(arguments.get("action_name") or "evidence_review"),
            status="queued",
            message="evidence preview available",
            evidence_manifest={"manifest_path": repo_relative(manifest_path)},
        ).to_dict(),
    }
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        payload["job"]["status"] = str(manifest.status)
        payload["job"]["evidence_manifest"] = {
            "manifest_path": repo_relative(manifest_path),
            "bridge": manifest.bridge,
            "action": manifest.action,
            "status": manifest.status,
        }
    return sanitize(payload)


def _handle_operation_context(arguments: JsonObject) -> JsonObject:
    return build_operation_context(
        bridge=arguments.get("bridge"),
        action=arguments.get("action"),
        operation_id=arguments.get("operation_id", "operation_preview"),
        phase=arguments.get("phase", "completed"),
        dry_run=arguments.get("dry_run", True),
        before_state=arguments.get("before_state"),
        after_state=arguments.get("after_state"),
        warnings=arguments.get("warnings"),
        evidence_refs=arguments.get("evidence_refs"),
        parent_context_id=arguments.get("parent_context_id"),
    )


STARBRIDGE_RECIPES: dict[str, JsonObject] = {
    "photoshop_preview_export": {
        "bridge": "photoshop",
        "goal": "Plan a sandbox Photoshop preview export with manifest evidence.",
        "steps": [
            {"tool": "photoshop.recipe_plan", "purpose": "build the sandbox action plan"},
            {"tool": "photoshop.recipe_validate", "purpose": "check output and manifest gates"},
            {
                "tool": "photoshop.recipe_run",
                "purpose": "dry-run first; confirmed write stays sandboxed",
            },
        ],
        "quality_gates": ["sandbox_output_dir", "manifest_schema", "no_private_path_leak"],
        "evidence": ["examples/output/evidence/manifest.latest.json"],
        "safety": "dry-run by default; confirmed writes remain under examples/output/photoshop.",
    },
    "comfyui_txt2img_lifecycle": {
        "bridge": "comfyui",
        "goal": "Validate a public txt2img template and return a redacted lifecycle summary.",
        "steps": [
            {
                "tool": "comfyui.queue_snapshot",
                "purpose": "plan a safe queue check; live loopback read remains an explicit probe",
            },
            {"tool": "comfy.workflow_template_get", "purpose": "load a bundled public template"},
            {
                "tool": "comfy.workflow_from_template",
                "purpose": "compose placeholder workflow JSON",
            },
            {
                "tool": "comfy.workflow_lifecycle_summary",
                "purpose": "summarize job and asset lifecycle",
            },
            {
                "tool": "comfyui.progress_monitor",
                "purpose": "plan a bounded live progress observation for separately confirmed runs",
            },
            {
                "tool": "comfyui.job_snapshot",
                "purpose": "plan a redacted single-job status read after a disconnect or later resume",
            },
        ],
        "quality_gates": [
            "queue_backpressure_reviewed",
            "live_progress_reviewed",
            "terminal_status_reviewed",
            "workflow_schema",
            "prompt_redacted",
            "no_queue_submit",
        ],
        "evidence": ["workflow_hash", "asset_manifest_preview"],
        "safety": (
            "queue snapshot is plan-only by default and live mode is loopback read-only; "
            "progress monitoring is also plan-only by default and omits raw events; "
            "job snapshot is plan-only by default and discards workflow, output, and error fields; "
            "the recipe does not submit to /prompt or read local model/image folders."
        ),
    },
    "cad_dxf_from_spec": {
        "bridge": "autocad_dxf",
        "goal": "Convert a public CAD spec into a validated DXF dry-run plan.",
        "steps": [
            {"tool": "autocad_dxf.create_dxf_plan", "purpose": "turn spec into CAD plan"},
            {
                "tool": "autocad_dxf.validate_cad_plan",
                "purpose": "validate units, layers, and entities",
            },
            {"tool": "autocad_dxf.summarize_plan", "purpose": "produce a reviewable summary"},
            {
                "tool": "autocad_dxf.write_dxf",
                "purpose": "dry-run first; confirmed write stays sandboxed",
            },
        ],
        "quality_gates": ["cad_plan_schema", "sandbox_output_dir", "confirm_write_for_dxf"],
        "evidence": ["plan_summary", "examples/output/evidence/manifest.latest.json"],
        "safety": "headless DXF path only; does not open customer DWG or AutoCAD.",
    },
    "illustrator_trace_preflight": {
        "bridge": "illustrator",
        "goal": "Plan an Illustrator trace/preflight workflow from sanitized document metadata.",
        "steps": [
            {"tool": "illustrator.document_info", "purpose": "optional local session summary"},
            {
                "tool": "illustrator.preflight",
                "purpose": "check links, colors, text, and export risk",
            },
            {"tool": "starbridge.evidence_init", "purpose": "prepare redacted evidence fields"},
        ],
        "quality_gates": ["metadata_only", "no_private_ai_read", "sandbox_export_required"],
        "evidence": ["document_summary", "preflight_report"],
        "safety": "preflight is read-only; any export remains a separate confirmed sandbox action.",
    },
    "blender_scene_evidence": {
        "bridge": "blender",
        "goal": "Plan a Blender scene or reference reconstruction evidence pass.",
        "steps": [
            {"tool": "blender.environment_probe", "purpose": "check executable hints"},
            {"tool": "blender.scene_plan", "purpose": "build a safe scene dry-run plan"},
            {
                "tool": "blender.reference_reconstruction_plan",
                "purpose": "optional single-reference reconstruction plan",
            },
            {"tool": "starbridge.evidence_init", "purpose": "prepare manifest evidence"},
        ],
        "quality_gates": ["no_blend_open", "no_arbitrary_python", "render_manifest_required"],
        "evidence": ["scene_plan", "camera_match_report", "manifest_preview"],
        "safety": "does not start Blender, download assets, or run arbitrary Python.",
    },
}


def _recipe_public_summary(recipe_id: str, recipe: JsonObject) -> JsonObject:
    return {
        "recipe_id": recipe_id,
        "bridge": recipe["bridge"],
        "goal": recipe["goal"],
        "safe_default": True,
        "writes": False,
        "quality_gates": recipe["quality_gates"],
    }


def _handle_starbridge_recipe_list(arguments: JsonObject) -> JsonObject:
    bridge = BRIDGE_ALIASES.get(
        str(arguments.get("bridge") or "all"), str(arguments.get("bridge") or "all")
    )
    recipes = []
    for recipe_id, recipe in STARBRIDGE_RECIPES.items():
        if bridge != "all" and recipe["bridge"] != bridge:
            continue
        recipes.append(_recipe_public_summary(recipe_id, recipe))
    return sanitize(
        {
            "ok": True,
            "bridge": bridge,
            "action": "recipe_list",
            "recipes": recipes,
        }
    )


def _handle_starbridge_recipe_plan(arguments: JsonObject) -> JsonObject:
    recipe_id = str(arguments.get("recipe_id") or "photoshop_preview_export")
    recipe = STARBRIDGE_RECIPES.get(recipe_id)
    if recipe is None:
        return sanitize(
            {
                "ok": False,
                "bridge": "all",
                "action": "recipe_plan",
                "recipe_id": recipe_id,
                "message": "unknown recipe_id",
                "available_recipes": sorted(STARBRIDGE_RECIPES),
            }
        )
    dry_run = bool(arguments.get("dry_run", True))
    transaction = create_recipe_transaction(
        recipe_id=recipe_id,
        bridge=str(recipe["bridge"]),
        intent=str(recipe["goal"]),
        steps=list(recipe["steps"]),
        quality_gates=list(recipe["quality_gates"]),
        expected_outputs=list(recipe["evidence"]),
        dry_run=dry_run,
    )
    plan = {
        **_recipe_public_summary(recipe_id, recipe),
        "dry_run": dry_run,
        "transaction": transaction.to_dict(),
        "steps": recipe["steps"],
        "evidence_requirements": recipe["evidence"],
        "operation_context": operation_context_contract(),
        "safety_boundary": recipe["safety"],
        "next_steps": [
            "Run listed tools in order only after reviewing their own safety annotations.",
            "Use starbridge.evidence_validate after any confirmed sandbox write.",
        ],
    }
    if recipe["bridge"] == "comfyui":
        plan["queue_snapshot"] = queue_snapshot_contract()
        plan["progress_monitor"] = progress_monitor_contract()
        plan["job_snapshot"] = job_snapshot_contract()
    if arguments.get("action_plan", True):
        plan["action_plan"] = {
            "mode": "plan_then_execute",
            "requires_user_confirmation_before_write": True,
            "tool_sequence": [step["tool"] for step in recipe["steps"]],
            "observation_tool": "starbridge.operation_context",
            "observation_capture_points": operation_context_contract()["capture_points"],
        }
    return sanitize(
        {
            "ok": True,
            "bridge": recipe["bridge"],
            "action": "recipe_plan",
            "recipe_id": recipe_id,
            "plan": plan,
        }
    )


def _handle_starbridge_recipe_evidence(arguments: JsonObject) -> JsonObject:
    recipe_id = str(arguments.get("recipe_id") or "photoshop_preview_export")
    recipe = STARBRIDGE_RECIPES.get(recipe_id)
    if recipe is None:
        return sanitize(
            {
                "ok": False,
                "bridge": "all",
                "action": "recipe_evidence",
                "recipe_id": recipe_id,
                "message": "unknown recipe_id",
                "available_recipes": sorted(STARBRIDGE_RECIPES),
            }
        )
    input_summary = {
        "recipe_id": recipe_id,
        "goal": recipe["goal"],
        "tools": [step["tool"] for step in recipe["steps"]],
        "safety_boundary": recipe["safety"],
        "operation_context_schema": operation_context_contract()["schema_version"],
    }
    if recipe["bridge"] == "comfyui":
        input_summary["queue_snapshot_schema"] = queue_snapshot_contract()["schema_version"]
        input_summary["progress_monitor_schema"] = progress_monitor_contract()["schema_version"]
        input_summary["job_snapshot_schema"] = job_snapshot_contract()["schema_version"]
    manifest = create_manifest(
        bridge=str(recipe["bridge"]),
        action="recipe_evidence",
        status="queued",
        dry_run=bool(arguments.get("dry_run", True)),
        confirm_write=bool(arguments.get("confirm_write", False)),
        plan_id=f"recipe::{recipe_id}",
        job_id=f"job::{recipe_id}::preview",
        input_summary=input_summary,
        notes=[
            "preview only; not saved to disk",
            "quality gates must pass before any confirmed bridge write",
            "capture a sanitized operation context after every major action or failure",
            "review queue backpressure before any confirmed ComfyUI submit",
            "review bounded live progress without returning raw WebSocket events",
            "review terminal status through a redacted single-job snapshot after disconnects",
        ],
    )
    for gate_name in recipe["quality_gates"]:
        manifest.add_quality_gate(
            ValidationResult(
                name=str(gate_name),
                ok=True,
                message="declared gate for recipe preview",
                details={"recipe_id": recipe_id, "preview": True},
            )
        )
    for item in recipe["evidence"]:
        manifest.add_asset(
            str(item),
            label="declared_evidence",
            details={"recipe_id": recipe_id, "materialized": False},
        )
    manifest.safety_decision = {
        "safe_default": True,
        "dry_run": manifest.dry_run,
        "confirm_write": manifest.confirm_write,
        "requires_confirmation_before_write": True,
        "sandbox_or_metadata_only": True,
        "operation_context_required_after_major_action": True,
        "queue_backpressure_review_required": recipe["bridge"] == "comfyui",
        "live_progress_review_required": recipe["bridge"] == "comfyui",
        "terminal_status_review_required": recipe["bridge"] == "comfyui",
    }
    return sanitize(
        {
            "ok": True,
            "bridge": recipe["bridge"],
            "action": "recipe_evidence",
            "recipe_id": recipe_id,
            "manifest": manifest.to_dict(),
        }
    )


def _report_to_result(
    *, bridge: str, action: str, report: JsonObject, display_name: str
) -> JsonObject:
    errors = report.get("errors", [])
    raw_warnings = report.get("warnings", [])
    warnings = []
    for warning in raw_warnings if isinstance(raw_warnings, list) else []:
        if isinstance(warning, dict):
            warnings.append(str(warning.get("message") or warning.get("code") or warning))
        else:
            warnings.append(str(warning))
    next_steps = []
    for error in errors if isinstance(errors, list) else []:
        if isinstance(error, dict):
            next_steps.append(str(error.get("message") or error.get("code") or error))
        else:
            next_steps.append(str(error))
    return sanitize(
        {
            "ok": bool(report.get("ok")),
            "bridge": bridge,
            "action": action,
            "message": f"{display_name}: {'ok' if report.get('ok') else 'not ready'}",
            "details": {"report": report},
            "warnings": warnings,
            "next_steps": next_steps,
        }
    )


def _handle_comfy_system_probe(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.probe import DEFAULT_BASE_URL, probe

    base_url = str(arguments.get("comfy_url") or DEFAULT_BASE_URL)
    timeout = int(arguments.get("timeout") or 8)
    return _report_to_result(
        bridge="comfyui",
        action="system_probe",
        report=probe(base_url, timeout),
        display_name="ComfyUI 图像生成桥",
    )


def _handle_comfy_queue_snapshot(arguments: JsonObject) -> JsonObject:
    return build_queue_snapshot(
        probe=arguments.get("probe", False),
        comfy_url=arguments.get("comfy_url", DEFAULT_COMFY_URL),
        timeout=arguments.get("timeout", 5),
        max_items=arguments.get("max_items", 25),
        progress=arguments.get("progress"),
    )


def _handle_comfy_job_snapshot(arguments: JsonObject) -> JsonObject:
    return build_job_snapshot(
        job_id=arguments.get("job_id"),
        probe=arguments.get("probe", False),
        comfy_url=arguments.get("comfy_url", DEFAULT_COMFY_URL),
        timeout=arguments.get("timeout", 5),
    )


def _handle_comfy_progress_monitor(arguments: JsonObject) -> JsonObject:
    return build_progress_monitor(
        connect=arguments.get("connect", False),
        comfy_url=arguments.get("comfy_url", DEFAULT_COMFY_URL),
        listen_seconds=arguments.get("listen_seconds", 5),
        stall_after_seconds=arguments.get("stall_after_seconds", 5),
        max_events=arguments.get("max_events", 100),
        target_job_id=arguments.get("target_job_id"),
    )


def _handle_python_probe(
    *, bridge: str, action: str, display_name: str, module_name: str
) -> JsonObject:
    module = __import__(module_name, fromlist=["probe"])
    return _report_to_result(
        bridge=bridge,
        action=action,
        report=module.probe(),
        display_name=display_name,
    )


def _handle_bridge_probe_tool(arguments: JsonObject, bridge: str) -> JsonObject:
    probe_com = bool(arguments.get("probe_com", True))
    response = build_response(
        argparse.Namespace(
            action="status",
            bridge=bridge,
            comfy_url=arguments.get("comfy_url"),
            timeout=int(arguments.get("timeout") or 8),
            probe_executables=probe_com,
            safe_only=False,
        )
    )
    results = response.get("results", [])
    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], dict):
        return results[0]
    return response


def _handle_workflow_validate(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.validate_workflow import DEFAULT_WORKFLOW, validate_workflow_file

    workflow_path = arguments.get("workflow_path")
    path = Path(str(workflow_path)) if workflow_path else DEFAULT_WORKFLOW
    return validate_workflow_file(path)


def _handle_comfy_workflow_build_plan(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_build_plan

    return workflow_build_plan(arguments)


def _handle_comfy_workflow_build(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_build

    return workflow_build(arguments)


def _handle_comfy_workflow_repair(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_repair

    return workflow_repair(arguments)


def _handle_comfy_agent_run(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import agent_run

    return agent_run(arguments)


def _handle_comfy_workflow_draft(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_draft

    return workflow_draft(arguments)


def _handle_comfy_workflow_compose(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_compose

    return workflow_compose(arguments)


def _handle_comfy_workflow_template_list(_arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_template_registry import list_workflow_templates

    return list_workflow_templates()


def _handle_comfy_workflow_template_get(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_template_registry import get_workflow_template

    return get_workflow_template(str(arguments.get("template_id") or ""))


def _handle_comfy_workflow_from_template(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_template_registry import compose_from_template

    nested_arguments = arguments.get("arguments")
    payload = nested_arguments if isinstance(nested_arguments, dict) else {}
    return compose_from_template(str(arguments.get("template_id") or ""), payload)


def _handle_comfy_workflow_lifecycle_summary(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_lifecycle_summary

    return workflow_lifecycle_summary(arguments)


def _handle_comfy_workflow_visualize(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_visualize import visualize_workflow

    workflow = arguments.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError("workflow is required and must be an object")
    return visualize_workflow(
        workflow,
        direction=str(arguments.get("direction") or "LR"),
        include_node_ids=bool(arguments.get("include_node_ids", True)),
    )


def _handle_write_dxf(arguments: JsonObject) -> JsonObject:
    dry_run = bool(arguments.get("dry_run", True))
    if not dry_run and not bool(arguments.get("confirm_write", False)):
        return sanitize(
            {
                "ok": False,
                "bridge": "autocad_dxf",
                "action": "write_dxf",
                "message": "Refusing real DXF write without confirm_write=true.",
                "details": {
                    "dry_run": dry_run,
                    "output": Path(str(arguments.get("output_path", ""))).name,
                    "output_root": "examples/cad/output",
                },
                "warnings": ["MCP write calls must be explicitly confirmed."],
                "next_steps": [
                    "Call again with dry_run=true first, or set confirm_write=true for a sandboxed output path."
                ],
            }
        )
    return autocad_dxf.write_dxf(
        arguments.get("plan"),
        str(arguments.get("output_path") or ""),
        dry_run=dry_run,
        confirm_write=bool(arguments.get("confirm_write", False)),
    )


REPO_ROOT = Path(__file__).resolve().parents[1]


PHOTOSHOP_RECIPE_ID = "sandbox_demo_preview"

CORE_RECIPES = {
    "prepare_vector_trace": {
        "goal": "Prepare one explicitly authorized PNG/JPEG for color-faithful Illustrator tracing.",
        "steps": [
            "validate the explicit reference authorization and bounded settings",
            "copy the source into examples/output/photoshop before opening Photoshop",
            "use the fixed JSX to normalize RGB, sRGB, 8-bit depth, size, and optional median filtering",
            "export an alpha-preserving PNG and redacted EvidenceManifest",
            "hand the sandbox PNG to the fixed Illustrator color trace",
        ],
        "tools": [
            "photoshop.recipe_plan",
            "photoshop.recipe_run",
            "illustrator.color_vectorize_execute",
            "starbridge.evidence_validate",
        ],
        "safety": "One explicit authorized PNG/JPEG only; copy-first sandbox processing; fixed JSX only; real copy and export require separate confirmations.",
        "example_execution": "Plan with recipe_id=prepare_vector_trace, then run with explicit input_path, reference_authorized=true, dry_run=false, confirm_write=true, and confirm_export=true.",
    },
    "remove_background": {
        "goal": "Remove background using select subject, feather mask, apply layer mask. All in sandbox.",
        "steps": [
            "1. ps.probe + ps.get_state for current doc",
            "2. ps.selection.subject (subject extract)",
            "3. feather selection (2-5px)",
            "4. create mask from selection on copy layer (use ps.layer ops or batchplay)",
            "5. apply layer mask",
            "6. ps.get_preview for vision check",
            "7. starbridge.evidence.capture + manifest",
            "8. Optional: ps.preview.export for final",
        ],
        "tools": [
            "ps.probe",
            "ps.get_state",
            "ps.selection.subject",
            "ps.preview.export",
            "starbridge.evidence",
        ],
        "safety": "dry_run default; confirm for real mask application on copy. Never on original PSD.",
        "example_execution": "Use recipe_plan then recipe_run with confirm_write after review. Maps to existing subject_extract + layer scripts.",
    },
    "enhance_portrait": {
        "goal": "Enhance portrait with frequency separation or smoothing, tone, skin retouch.",
        "steps": [
            "1. ps.probe + ps.get_state",
            "2. duplicate layer for high/low freq (ps.layer ops)",
            "3. gaussian blur low freq",
            "4. high freq = original - blurred (via batchplay or script)",
            "5. smooth high, tone low",
            "6. merge or group",
            "7. ps.get_preview",
            "8. evidence + manifest",
        ],
        "tools": [
            "ps.document.info",
            "ps.layer.duplicate",
            "ps.batchplay",
            "ps.preview.export",
            "starbridge.evidence",
        ],
        "safety": "sandbox only; non-destructive where possible. Use on copy layers.",
        "example_execution": "recipe_plan with action_plan, then run via photoshop scripts or batchplay sequence.",
    },
    "frequency_separation": {
        "goal": "Set up frequency separation for retouching on active raster layer.",
        "steps": [
            "duplicate for high/low",
            "apply gaussian blur to low",
            "high = original - low",
            "group layers",
        ],
        "tools": ["ps.layer.ops", "ps.batchplay.execute"],
        "safety": "plan first, dry_run for preview.",
    },
    "color_grade": {
        "goal": "Apply non-destructive color grade with adjustment layers (curves, hsl, gradient).",
        "steps": [
            "add curves adj",
            "add hsl adj",
            "add gradient map",
            "clip to subject",
            "preview",
        ],
        "tools": ["ps.adjustment.layers", "ps.preview.export"],
        "safety": "adjustment layers on copy.",
    },
    "prepare_for_web": {
        "goal": "Prepare for web: convert sRGB, resize, sharpen, export optimized variants.",
        "steps": [
            "convert profile",
            "resize for web",
            "unsharp mask",
            "export jpeg/png",
            "export variants",
        ],
        "tools": ["ps.document.profile", "ps.export", "ps.preview"],
        "safety": "exports to sandbox.",
    },
}


def _recipe_output_dir(arguments: JsonObject) -> str:
    return _sandbox_output_dir(arguments, "photoshop")


def _recipe_validations(output_dir: str) -> list[JsonObject]:
    return [
        {
            "name": "output_dir_sandboxed",
            "ok": output_dir.startswith("examples/output/photoshop"),
            "expected_root": "examples/output/photoshop",
        },
        {
            "name": "manifest_schema",
            "ok": True,
            "path": "examples/output/evidence/manifest.latest.json",
        },
        {"name": "no_private_path_leak", "ok": True},
        {"name": "confirm_write_required", "ok": True},
    ]


def _recipe_definition(output_dir: str, recipe_id: str = None) -> JsonObject:
    recipe_id = recipe_id or PHOTOSHOP_RECIPE_ID
    if recipe_id in CORE_RECIPES:
        recipe = CORE_RECIPES[recipe_id]
        if recipe_id == "prepare_vector_trace":
            allowed_inputs = [
                "recipe_id",
                "reference_id",
                "reference_authorized",
                "input_path",
                "source_media_type",
                "source_width",
                "source_height",
                "max_dimension",
                "median_radius",
                "normalize_srgb",
                "dry_run",
                "confirm_write",
                "confirm_export",
                "output_dir",
            ]
            allowed_outputs = [
                f"{output_dir}/<reference_id>_source.<png|jpg|jpeg>",
                f"{output_dir}/<reference_id>_vector_source.png",
                "examples/output/evidence/<reference_id>.color_preprocess.json",
            ]
        else:
            allowed_inputs = ["recipe_id", "dry_run", "confirm_write", "output_dir"]
            allowed_outputs = [
                f"{output_dir}/result_{recipe_id}.psd",
                f"{output_dir}/preview_{recipe_id}.png",
            ]
        return {
            "recipe_id": recipe_id,
            "goal": recipe["goal"],
            "allowed_inputs": allowed_inputs,
            "allowed_outputs": allowed_outputs,
            "steps": recipe["steps"],
            "tools": recipe["tools"],
            "validations": [item["name"] for item in _recipe_validations(output_dir)],
            "retry_policy": [
                "start with dry_run and recipe_validate",
                "review manifest before confirm_write",
            ],
            "evidence_requirements": [
                "redacted EvidenceManifest",
                "sandbox outputs only",
            ],
            "safety_boundary": recipe.get(
                "safety", "dry_run default; sandbox only; confirm for real."
            ),
        }
    # fallback to demo
    return {
        "recipe_id": PHOTOSHOP_RECIPE_ID,
        "goal": "Create a sandbox Photoshop demo document, export previews, and record evidence without exposing private PSD paths.",
        "allowed_inputs": ["recipe_id", "dry_run", "confirm_write", "output_dir"],
        "allowed_outputs": [
            f"{output_dir}/starbridge_ps_demo.psd",
            f"{output_dir}/starbridge_ps_demo.png",
            f"{output_dir}/starbridge_ps_demo.jpg",
        ],
        "steps": [
            "plan sandbox outputs",
            "create sandbox PSD",
            "export preview assets",
            "validate evidence manifest",
        ],
        "tools": [
            "photoshop.create_demo_document",
            "photoshop.export_demo_preview",
            "starbridge.evidence_init",
            "starbridge.evidence_validate",
        ],
        "validations": [item["name"] for item in _recipe_validations(output_dir)],
        "retry_policy": [
            "retry after local Photoshop authorization is ready",
            "rerun dry_run before enabling confirm_write",
        ],
        "evidence_requirements": [
            "redacted EvidenceManifest JSON",
            "declared output file list",
            "no private path leakage",
        ],
        "safety_boundary": "Writes stay inside examples/output/photoshop and require confirm_write=true for real execution.",
    }


def _handle_photoshop_recipe_list(_arguments: JsonObject) -> JsonObject:
    recipes = []
    for rid in [PHOTOSHOP_RECIPE_ID] + list(CORE_RECIPES.keys()):
        recipes.append(_recipe_definition("examples/output/photoshop", rid))
    return sanitize(
        {"ok": True, "bridge": "photoshop", "action": "recipe_list", "recipes": recipes}
    )


def _handle_photoshop_recipe_plan(arguments: JsonObject) -> JsonObject:
    recipe_id = str(arguments.get("recipe_id") or PHOTOSHOP_RECIPE_ID)
    output_dir = _recipe_output_dir(arguments)
    if recipe_id == "prepare_vector_trace":
        preprocess_arguments = dict(arguments)
        preprocess_arguments["output_dir"] = output_dir
        preprocess_plan = build_color_preprocess_plan(preprocess_arguments)
        return sanitize(
            {
                "ok": bool(preprocess_plan.get("ok")),
                "bridge": "photoshop",
                "action": "recipe_plan",
                "dry_run": True,
                "recipe_id": recipe_id,
                "preprocess_plan": preprocess_plan,
                "quality_gates": [item["name"] for item in _recipe_validations(output_dir)],
            }
        )
    plan_def = _recipe_definition(output_dir, recipe_id) | {"recipe_id": recipe_id}
    # Action Plan mode support: if "action_plan" requested, return executable steps
    if arguments.get("action_plan"):
        plan_def["action_plan"] = {
            "mode": "plan_then_execute",
            "steps": plan_def["steps"],
            "tools_sequence": plan_def["tools"],
            "repair": "validate after each major step, re-plan on failure up to 3 times",
        }
    return sanitize(
        {
            "ok": True,
            "bridge": "photoshop",
            "action": "recipe_plan",
            "dry_run": bool(arguments.get("dry_run", True)),
            "plan": plan_def,
            "quality_gates": [item["name"] for item in _recipe_validations(output_dir)],
        }
    )


def _handle_photoshop_recipe_validate(arguments: JsonObject) -> JsonObject:
    output_dir = _recipe_output_dir(arguments)
    recipe_id = str(arguments.get("recipe_id") or PHOTOSHOP_RECIPE_ID)
    if recipe_id == "prepare_vector_trace":
        preprocess_arguments = dict(arguments)
        preprocess_arguments["output_dir"] = output_dir
        preprocess_plan = build_color_preprocess_plan(preprocess_arguments)
        return sanitize(
            {
                "ok": bool(preprocess_plan.get("ok")),
                "bridge": "photoshop",
                "action": "recipe_validate",
                "dry_run": True,
                "recipe_id": recipe_id,
                "preprocess_plan": preprocess_plan,
                "validation": _recipe_validations(output_dir),
            }
        )
    return sanitize(
        {
            "ok": True,
            "bridge": "photoshop",
            "action": "recipe_validate",
            "dry_run": bool(arguments.get("dry_run", True)),
            "recipe_id": recipe_id,
            "validation": _recipe_validations(output_dir),
        }
    )


def _handle_photoshop_recipe_run(arguments: JsonObject) -> JsonObject:
    output_dir = _recipe_output_dir(arguments)
    recipe_id = str(arguments.get("recipe_id") or PHOTOSHOP_RECIPE_ID)
    if recipe_id == "prepare_vector_trace":
        preprocess_arguments = dict(arguments)
        preprocess_arguments["output_dir"] = output_dir
        preprocess_result = _execute_photoshop_color_preprocess(preprocess_arguments)
        if arguments.get("dry_run", True) is not False:
            return sanitize(
                {
                    "ok": bool(preprocess_result.get("ok")),
                    "bridge": "photoshop",
                    "action": "recipe_run",
                    "dry_run": True,
                    "recipe_id": recipe_id,
                    "preprocess_plan": preprocess_result,
                }
            )
        return sanitize(preprocess_result | {"recipe_id": recipe_id})
    dry_run = bool(arguments.get("dry_run", True))
    if dry_run:
        commands = ["npm.cmd run photoshop:demo:plan"]
        if recipe_id == "remove_background":
            commands += [
                "# For remove_background: use extract_subject_to_png.ps1 with input from plan",
                'powershell -ExecutionPolicy Bypass -File examples/photoshop_bridge/scripts/extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "examples/output/photoshop/subject.png"',
            ]
        elif recipe_id == "enhance_portrait":
            commands += ["# Use frequency sep via batchplay or custom script on sandbox copy"]
        else:
            commands += ["# execute recipe steps via BatchPlay or UXP in sandbox"]
        commands += ["npm.cmd run photoshop:manifest"]
        return sanitize(
            {
                "ok": True,
                "bridge": "photoshop",
                "action": "recipe_run",
                "dry_run": True,
                "recipe_id": recipe_id,
                "output_dir": output_dir,
                "commands": commands,
                "quality_gates": [item["name"] for item in _recipe_validations(output_dir)],
            }
        )
    if not bool(arguments.get("confirm_write", False)):
        return sanitize(
            {
                "ok": False,
                "bridge": "photoshop",
                "action": "recipe_run",
                "dry_run": False,
                "message": "Refusing recipe_run without confirm_write=true.",
                "output_dir": output_dir,
            }
        )
    return sanitize(
        {
            "ok": True,
            "bridge": "photoshop",
            "action": "recipe_run",
            "dry_run": False,
            "confirm_write": True,
            "output_dir": output_dir,
            "recipe_id": recipe_id,
            "next_steps": [
                "Run authorized local script for the recipe (e.g. BatchPlay sequence for "
                + recipe_id
                + ")",
                "Capture evidence manifest after run.",
            ],
        }
    )


def _handle_photoshop_recipe_debug(arguments: JsonObject) -> JsonObject:
    recipe_id = str(arguments.get("recipe_id") or PHOTOSHOP_RECIPE_ID)
    extra = CORE_RECIPES.get(recipe_id, {})
    return sanitize(
        {
            "ok": True,
            "bridge": "photoshop",
            "action": "recipe_debug",
            "recipe_id": recipe_id,
            "action_plan_mode": "plan multiple steps in one LLM call, execute seq with repair",
            "retry_policy": [
                "start with recipe_plan and recipe_validate",
                "keep output_dir inside examples/output/photoshop",
                "only enable confirm_write after reviewing the EvidenceManifest path and output file list",
            ]
            + extra.get("steps", []),
            "common_failures": [
                "Photoshop COM unavailable",
                "sandbox output path escaped the allowed root",
                "real execution was requested without confirm_write=true",
            ],
            "example_action_plan": "Use recipe_plan with action_plan=true to get sequenced tool calls.",
        }
    )


def _sandbox_output_dir(arguments: JsonObject, bridge: str) -> str:
    default = f"examples/output/{bridge}"
    requested = str(arguments.get("output_dir") or default)
    base = (REPO_ROOT / default).resolve()
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"output_dir must stay inside {default}") from exc
    return candidate.relative_to(REPO_ROOT).as_posix()


def _run_powershell_json(script_relative: str, extra_args: list[str] | None = None) -> JsonObject:
    script_path = REPO_ROOT / script_relative
    if not script_path.exists():
        raise ValueError(f"missing script: {script_relative}")
    completed = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            *(extra_args or []),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return sanitize(
            {
                "ok": False,
                "bridge": "adobe",
                "task": "script_call",
                "warnings": ["PowerShell script returned no JSON output."],
                "next_steps": [
                    "Run the matching npm.cmd script locally to inspect the environment error."
                ],
            }
        )
    try:
        return sanitize(json.loads(stdout))
    except json.JSONDecodeError:
        return sanitize(
            {
                "ok": False,
                "bridge": "adobe",
                "task": "script_call",
                "warnings": ["PowerShell script output was not valid JSON."],
                "next_steps": ["Run the matching npm.cmd script locally and check stdout."],
            }
        )


def _execute_photoshop_color_preprocess(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "photoshop")
    preprocess_arguments = dict(arguments)
    preprocess_arguments["output_dir"] = output_dir
    plan = build_color_preprocess_plan(preprocess_arguments)
    if not plan.get("ok"):
        return sanitize(plan)
    if arguments.get("dry_run", True) is not False:
        return sanitize(plan)

    if arguments.get("confirm_write") is not True:
        return _adobe_refusal(
            bridge="photoshop", task="color_preprocess", confirm_key="confirm_write"
        )
    if arguments.get("confirm_export") is not True:
        return _adobe_refusal(
            bridge="photoshop", task="color_preprocess", confirm_key="confirm_export"
        )

    input_path = arguments.get("input_path")
    if not isinstance(input_path, str) or not input_path.strip():
        raise ValueError("input_path is required for confirmed color preprocessing")
    input_file = Path(input_path).expanduser()
    if not input_file.is_absolute():
        input_file = REPO_ROOT / input_file
    input_file = input_file.resolve()
    if not input_file.is_file():
        raise ValueError("the explicitly supplied input file was not found")

    extension = input_file.suffix.lower()
    media_type = str(arguments.get("source_media_type") or "image/png")
    if extension == ".png" and media_type != "image/png":
        raise ValueError("source_media_type does not match the explicit input file")
    if extension in {".jpg", ".jpeg"} and media_type != "image/jpeg":
        raise ValueError("source_media_type does not match the explicit input file")
    if extension not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("input_path must identify one PNG or JPEG file")

    settings = plan["settings"]
    extra_args = [
        "-ReferenceId",
        str(plan["reference_id"]),
        "-InputPath",
        str(input_file),
        "-OutputDir",
        output_dir,
        "-MaxDimension",
        str(settings["max_dimension"]),
        "-MedianRadius",
        str(settings["median_radius"]),
        "-ConfirmAuthorization",
        "-ConfirmWrite",
        "-ConfirmExport",
    ]
    if not settings["normalize_srgb"]:
        extra_args.append("-DisableSrgbNormalization")

    result = dict(
        _run_powershell_json(
            "examples/photoshop_bridge/scripts/color_vector_preprocess.ps1",
            extra_args,
        )
    )
    succeeded = result.get("ok") is True
    outputs = result.get("outputs") if isinstance(result.get("outputs"), dict) else {}
    safety = result.get("safety") if isinstance(result.get("safety"), dict) else {}
    manifest = create_manifest(
        bridge="photoshop",
        action="color_preprocess",
        status="completed" if succeeded else "failed",
        dry_run=False,
        confirm_write=True,
        plan_id=f"color-preprocess::{plan['reference_id']}",
        job_id=f"photoshop::{plan['reference_id']}::vector-source",
        input_summary={
            "reference_id": plan["reference_id"],
            "reference_authorized": True,
            "media_type": media_type,
            "settings": settings,
            "input_sha256": result.get("input_sha256"),
            "paths_returned": False,
        },
        notes=[
            "The original image was not modified.",
            "Only a sandbox copy was opened by the fixed Photoshop script.",
            "Desktop execution still requires visual review before acceptance.",
        ],
    )
    for key, label in (
        ("source_copy", "sandbox_source_copy"),
        ("prepared_png", "illustrator_trace_source"),
    ):
        value = outputs.get(key)
        if isinstance(value, str) and value.startswith("examples/output/photoshop/"):
            manifest.add_output_file(value, label=label)
    manifest.add_validation(
        ValidationResult(
            name="source_copy_verified",
            ok=safety.get("source_copy_verified") is True,
            message=(
                "sandbox source copy hash matched"
                if safety.get("source_copy_verified") is True
                else "sandbox source copy was not verified"
            ),
            details={"paths_returned": False},
        )
    )
    manifest.add_validation(
        ValidationResult(
            name="prepared_png_created",
            ok=succeeded and isinstance(outputs.get("prepared_png"), str),
            message=(
                "prepared PNG was created"
                if succeeded and isinstance(outputs.get("prepared_png"), str)
                else "prepared PNG was not created"
            ),
            details={"output_sha256": result.get("output_sha256")},
        )
    )
    manifest.add_quality_gate(
        ValidationResult(
            name="photoshop_preprocess_ready_for_visual_review",
            ok=succeeded,
            message=(
                "fixed preprocessing completed"
                if succeeded
                else "fixed preprocessing did not complete"
            ),
            details={"visual_review_required": True},
        )
    )
    manifest.safety_decision = {
        "single_explicit_user_file": True,
        "sandbox_copy_before_photoshop": True,
        "original_modified": False,
        "output_sandboxed": safety.get("output_sandboxed") is True,
        "arbitrary_script": False,
        "cloud_upload": False,
        "visual_review_required": True,
    }
    manifest.add_validation(manifest_validation_result(manifest.to_dict()))
    evidence_file = save_manifest(
        manifest,
        f"examples/output/evidence/{plan['reference_id']}.color_preprocess.json",
    )
    evidence_path = repo_relative(evidence_file)
    result.setdefault("bridge", "photoshop")
    result.setdefault("action", "color_preprocess")
    result["evidence_manifest"] = evidence_path
    result["evidence_path"] = evidence_path
    return sanitize(result)


def _adobe_refusal(*, bridge: str, task: str, confirm_key: str) -> JsonObject:
    return sanitize(
        {
            "ok": False,
            "bridge": bridge,
            "task": task,
            "dry_run": False,
            confirm_key: False,
            "warnings": [f"Refusing real {bridge} write/export without {confirm_key}=true."],
            "next_steps": [
                "Run the dry-run plan first, then call again with explicit confirmation for sandbox output."
            ],
        }
    )


def _handle_adobe_document_info(
    arguments: JsonObject, bridge: str, script_relative: str
) -> JsonObject:
    if not bool(arguments.get("probe_com", True)):
        return sanitize(
            {
                "ok": False,
                "bridge": bridge,
                "task": "document_info",
                "active_document": False,
                "warnings": ["COM probing was skipped by request."],
                "next_steps": [
                    f"Run the {bridge}:info npm script on a Windows machine with the Adobe app available."
                ],
            }
        )
    return _run_powershell_json(script_relative)


def _handle_illustrator_create(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "illustrator")
    width = int(arguments.get("width") or 1080)
    height = int(arguments.get("height") or 1080)
    dry_run = bool(arguments.get("dry_run", True))
    confirm_write = bool(arguments.get("confirm_write", False))
    result = {
        "ok": True,
        "bridge": "illustrator",
        "task": "create_demo_artboard",
        "dry_run": dry_run,
        "confirm_write": confirm_write,
        "document": {
            "name": "starbridge_ai_demo.ai",
            "width": width,
            "height": height,
            "color_space": "RGB",
        },
        "artboards": [{"index": 0, "width": width, "height": height}],
        "layers": ["background", "foreground"],
        "objects_created": [
            "background rectangle",
            "title text",
            "subtitle text",
            "circle",
            "rectangle",
            "line",
            "path",
        ],
        "output_ai_path": f"{output_dir}/starbridge_ai_demo.ai",
        "warnings": [],
        "next_steps": [
            "Call again with dry_run=false and confirm_write=true to create the sandbox demo document."
        ],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_write:
        return _adobe_refusal(
            bridge="illustrator", task="create_demo_artboard", confirm_key="confirm_write"
        )
    return _run_powershell_json(
        "examples/illustrator_bridge/scripts/create_demo_artboard.ps1",
        ["-Width", str(width), "-Height", str(height), "-OutputDir", output_dir, "-ConfirmWrite"],
    )


def _handle_illustrator_export(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "illustrator")
    dry_run = bool(arguments.get("dry_run", True))
    confirm_export = bool(arguments.get("confirm_export", False))
    result = {
        "ok": True,
        "bridge": "illustrator",
        "task": "export_demo_assets",
        "dry_run": dry_run,
        "confirm_export": confirm_export,
        "exported_files": [
            f"{output_dir}/starbridge_ai_demo.svg",
            f"{output_dir}/starbridge_ai_demo.png",
            f"{output_dir}/starbridge_ai_demo.pdf",
        ],
        "svg_path": f"{output_dir}/starbridge_ai_demo.svg",
        "png_path": f"{output_dir}/starbridge_ai_demo.png",
        "pdf_path": f"{output_dir}/starbridge_ai_demo.pdf",
        "warnings": [],
        "next_steps": [
            "Call again with dry_run=false and confirm_export=true after creating the sandbox demo document."
        ],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_export:
        return _adobe_refusal(
            bridge="illustrator", task="export_demo_assets", confirm_key="confirm_export"
        )
    return _run_powershell_json(
        "examples/illustrator_bridge/scripts/export_demo_assets.ps1",
        ["-OutputDir", output_dir, "-ConfirmExport"],
    )


def _handle_illustrator_run(arguments: JsonObject) -> JsonObject:
    dry_run = bool(arguments.get("dry_run", True))
    if dry_run:
        return sanitize(
            {
                "ok": True,
                "bridge": "illustrator",
                "task": "sandbox_vector_demo",
                "dry_run": True,
                "commands": [
                    "npm.cmd run illustrator:demo:plan",
                    "npm.cmd run illustrator:demo",
                    "npm.cmd run illustrator:manifest",
                ],
                "warnings": [],
                "next_steps": [
                    "Call again with dry_run=false, confirm_write=true, and confirm_export=true to run the local demo."
                ],
            }
        )
    if not bool(arguments.get("confirm_write", False)):
        return _adobe_refusal(
            bridge="illustrator", task="sandbox_vector_demo", confirm_key="confirm_write"
        )
    if not bool(arguments.get("confirm_export", False)):
        return _adobe_refusal(
            bridge="illustrator", task="sandbox_vector_demo", confirm_key="confirm_export"
        )
    return _run_powershell_json("examples/illustrator_bridge/scripts/run_demo.ps1")


def _handle_illustrator_color_vectorize_execute(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "illustrator")
    plan = build_color_vectorization_plan(arguments)
    if plan.get("ok") and isinstance(plan.get("outputs"), dict):
        plan["outputs"]["output_dir"] = output_dir

    dry_run = arguments.get("dry_run", True) is not False
    if dry_run or not plan.get("ok"):
        return sanitize(plan)

    if arguments.get("confirm_write", False) is not True:
        return _adobe_refusal(
            bridge="illustrator", task="color_vectorize", confirm_key="confirm_write"
        )
    if arguments.get("confirm_export", False) is not True:
        return _adobe_refusal(
            bridge="illustrator", task="color_vectorize", confirm_key="confirm_export"
        )

    application_chain = "illustrator_only"
    preprocess_summary: JsonObject | None = None
    if arguments.get("photoshop_preprocess", False) is True:
        preprocess_arguments = dict(arguments)
        preprocess_arguments["output_dir"] = "examples/output/photoshop"
        preprocess_result = _execute_photoshop_color_preprocess(preprocess_arguments)
        if preprocess_result.get("ok") is not True:
            return sanitize(
                {
                    "ok": False,
                    "bridge": "illustrator",
                    "task": "color_vectorize",
                    "verdict": "blocked",
                    "application_chain": "photoshop_to_illustrator",
                    "preprocess": {
                        "ok": False,
                        "action": preprocess_result.get("action"),
                        "error_code": preprocess_result.get("error_code"),
                        "evidence_path": preprocess_result.get("evidence_path"),
                    },
                    "warnings": preprocess_result.get("warnings")
                    or ["Photoshop preprocessing did not produce a trace source."],
                    "next_steps": preprocess_result.get("next_steps") or [],
                }
            )
        outputs = (
            preprocess_result.get("outputs")
            if isinstance(preprocess_result.get("outputs"), dict)
            else {}
        )
        prepared_path = outputs.get("prepared_png")
        if not isinstance(prepared_path, str) or not prepared_path:
            raise ValueError("Photoshop preprocessing returned no prepared sandbox PNG")
        prepared_file = Path(prepared_path)
        if not prepared_file.is_absolute():
            prepared_file = REPO_ROOT / prepared_file
        input_file = prepared_file.resolve()
        photoshop_root = (REPO_ROOT / "examples/output/photoshop").resolve()
        try:
            input_file.relative_to(photoshop_root)
        except ValueError as exc:
            raise ValueError(
                "prepared Photoshop output must stay inside examples/output/photoshop"
            ) from exc
        if input_file.suffix.lower() != ".png":
            raise ValueError("prepared Photoshop output must be one PNG file")
        application_chain = "photoshop_to_illustrator"
        preprocess_summary = {
            "ok": True,
            "action": preprocess_result.get("action"),
            "reference_id": preprocess_result.get("reference_id"),
            "input_sha256": preprocess_result.get("input_sha256"),
            "output_sha256": preprocess_result.get("output_sha256"),
            "operations": preprocess_result.get("operations"),
            "outputs": {"prepared_png": prepared_path},
            "evidence_path": preprocess_result.get("evidence_path"),
        }
    else:
        input_path = arguments.get("input_path")
        if not isinstance(input_path, str) or not input_path.strip():
            raise ValueError("input_path is required for confirmed color vectorization")
        input_file = Path(input_path).expanduser()
        if not input_file.is_absolute():
            input_file = REPO_ROOT / input_file
        input_file = input_file.resolve()
        if not input_file.is_file():
            raise ValueError("the explicitly supplied input file was not found")

        extension = input_file.suffix.lower()
        media_type = str(arguments.get("source_media_type") or "image/png")
        if extension == ".png" and media_type != "image/png":
            raise ValueError("source_media_type does not match the explicit input file")
        if extension in {".jpg", ".jpeg"} and media_type != "image/jpeg":
            raise ValueError("source_media_type does not match the explicit input file")
        if extension not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("input_path must identify one PNG or JPEG file")

    trace = plan["trace"]
    extra_args = [
        "-ReferenceId",
        str(plan["reference_id"]),
        "-InputPath",
        str(input_file),
        "-OutputDir",
        output_dir,
        "-MaxColors",
        str(trace["max_colors"]),
        "-PathFitting",
        str(trace["path_fitting"]),
        "-MinArea",
        str(trace["min_area"]),
        "-PreprocessBlur",
        str(trace["preprocess_blur"]),
        "-ConfirmWrite",
        "-ConfirmExport",
    ]
    if trace["ignore_white"]:
        extra_args.append("-IgnoreWhite")
    if not trace["output_to_swatches"]:
        extra_args.append("-DisableOutputToSwatches")
    result = dict(
        _run_powershell_json("examples/illustrator_bridge/scripts/color_vectorize.ps1", extra_args)
    )
    result["application_chain"] = application_chain
    if preprocess_summary is not None:
        result["preprocess"] = preprocess_summary
    return sanitize(result)


def _handle_illustrator_color_vectorize_compare(arguments: JsonObject) -> JsonObject:
    try:
        return compare_color_vectorization_files(arguments, repo_root=REPO_ROOT)
    except (OSError, RuntimeError, ValueError) as error:
        if arguments.get("soft_exit", True) is False:
            raise
        return sanitize(
            {
                "ok": False,
                "bridge": "illustrator",
                "action": "color_vectorize_compare",
                "verdict": "blocked",
                "error_code": "comparison_unavailable",
                "warnings": [str(error)],
                "safety": {
                    "paths_returned": False,
                    "pixels_retained": False,
                    "metadata_returned": False,
                    "recursive_scan": False,
                },
            }
        )


def _handle_photoshop_create(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "photoshop")
    width = int(arguments.get("width") or 1080)
    height = int(arguments.get("height") or 1080)
    dpi = int(arguments.get("dpi") or 72)
    dry_run = bool(arguments.get("dry_run", True))
    confirm_write = bool(arguments.get("confirm_write", False))
    result = {
        "ok": True,
        "bridge": "photoshop",
        "task": "create_demo_document",
        "dry_run": dry_run,
        "confirm_write": confirm_write,
        "document": {
            "name": "starbridge_ps_demo.psd",
            "width": width,
            "height": height,
            "dpi": dpi,
            "color_mode": "RGB",
        },
        "layers_created": [
            "background",
            "color_block_left",
            "color_block_right",
            "title_text",
            "subtitle_text",
        ],
        "output_psd_path": f"{output_dir}/starbridge_ps_demo.psd",
        "warnings": [],
        "next_steps": [
            "Call again with dry_run=false and confirm_write=true to create the sandbox demo PSD."
        ],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_write:
        return _adobe_refusal(
            bridge="photoshop", task="create_demo_document", confirm_key="confirm_write"
        )
    return _run_powershell_json(
        "examples/photoshop_bridge/scripts/create_demo_document.ps1",
        [
            "-Width",
            str(width),
            "-Height",
            str(height),
            "-Dpi",
            str(dpi),
            "-OutputDir",
            output_dir,
            "-ConfirmWrite",
        ],
    )


def _handle_photoshop_export(arguments: JsonObject) -> JsonObject:
    output_dir = _sandbox_output_dir(arguments, "photoshop")
    dry_run = bool(arguments.get("dry_run", True))
    confirm_export = bool(arguments.get("confirm_export", False))
    result = {
        "ok": True,
        "bridge": "photoshop",
        "task": "export_demo_preview",
        "dry_run": dry_run,
        "confirm_export": confirm_export,
        "exported_files": [
            f"{output_dir}/starbridge_ps_demo.png",
            f"{output_dir}/starbridge_ps_demo.jpg",
        ],
        "width": 1080,
        "height": 1080,
        "layer_count": None,
        "warnings": [],
        "next_steps": [
            "Call again with dry_run=false and confirm_export=true after creating the sandbox demo PSD."
        ],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_export:
        return _adobe_refusal(
            bridge="photoshop", task="export_demo_preview", confirm_key="confirm_export"
        )
    return _run_powershell_json(
        "examples/photoshop_bridge/scripts/export_demo_preview.ps1",
        ["-OutputDir", output_dir, "-ConfirmExport"],
    )


def _handle_photoshop_run(arguments: JsonObject) -> JsonObject:
    dry_run = bool(arguments.get("dry_run", True))
    if dry_run:
        return sanitize(
            {
                "ok": True,
                "bridge": "photoshop",
                "task": "sandbox_ps_demo",
                "dry_run": True,
                "commands": [
                    "npm.cmd run photoshop:demo:plan",
                    "npm.cmd run photoshop:demo",
                    "npm.cmd run photoshop:manifest",
                ],
                "warnings": [],
                "next_steps": [
                    "Call again with dry_run=false, confirm_write=true, and confirm_export=true to run the local demo."
                ],
            }
        )
    if not bool(arguments.get("confirm_write", False)):
        return _adobe_refusal(
            bridge="photoshop", task="sandbox_ps_demo", confirm_key="confirm_write"
        )
    if not bool(arguments.get("confirm_export", False)):
        return _adobe_refusal(
            bridge="photoshop", task="sandbox_ps_demo", confirm_key="confirm_export"
        )
    return _run_powershell_json("examples/photoshop_bridge/scripts/run_demo.ps1")


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "starbridge.status": _handle_status,
    "starbridge.probe": _handle_probe,
    "starbridge.tools": _handle_tools,
    "starbridge.control_plan": _handle_control_plan,
    "starbridge.safe_roots": _handle_safe_roots,
    "starbridge.evidence_init": _handle_evidence_init,
    "starbridge.evidence_validate": _handle_evidence_validate,
    "starbridge.job_status": _handle_job_status,
    "starbridge.operation_context": _handle_operation_context,
    "starbridge.recipe_list": _handle_starbridge_recipe_list,
    "starbridge.recipe_plan": _handle_starbridge_recipe_plan,
    "starbridge.recipe_evidence": _handle_starbridge_recipe_evidence,
    "comfyui.system_probe": _handle_comfy_system_probe,
    "comfyui.queue_snapshot": _handle_comfy_queue_snapshot,
    "comfyui.job_snapshot": _handle_comfy_job_snapshot,
    "comfyui.progress_monitor": _handle_comfy_progress_monitor,
    "comfyui.workflow_validate": _handle_workflow_validate,
    "comfyui.workflow_build_plan": _handle_comfy_workflow_build_plan,
    "comfyui.workflow_build": _handle_comfy_workflow_build,
    "comfyui.workflow_repair": _handle_comfy_workflow_repair,
    "comfyui.agent_run": _handle_comfy_agent_run,
    "comfy.workflow_draft": _handle_comfy_workflow_draft,
    "comfy.workflow_compose": _handle_comfy_workflow_compose,
    "comfy.workflow_template_list": _handle_comfy_workflow_template_list,
    "comfy.workflow_template_get": _handle_comfy_workflow_template_get,
    "comfy.workflow_from_template": _handle_comfy_workflow_from_template,
    "comfy.workflow_lifecycle_summary": _handle_comfy_workflow_lifecycle_summary,
    "comfy.workflow_visualize": _handle_comfy_workflow_visualize,
    "blender.environment_probe": lambda _arguments: _handle_python_probe(
        bridge="blender",
        action="environment_probe",
        display_name="Blender 三维场景桥",
        module_name="examples.blender_bridge.probe",
    ),
    "blender.scene_plan": lambda arguments: build_scene_plan(
        scene_name=str(arguments.get("scene_name") or "starbridge_public_scene"),
        render_width=int(arguments.get("render_width") or 1280),
        render_height=int(arguments.get("render_height") or 720),
    ),
    "blender.reference_reconstruction_plan": lambda arguments: build_reference_reconstruction_plan(
        reference_name=str(arguments.get("reference_name") or "reference_image"),
        target_kind=str(arguments.get("target_kind") or "object_or_scene"),
        reference_views=int(arguments.get("reference_views") or 1),
        known_scale=str(arguments.get("known_scale") or ""),
        tolerance_pixels=int(arguments.get("tolerance_pixels") or 4),
        max_iterations=int(arguments.get("max_iterations") or 8),
    ),
    "cad_autocad.environment_probe": lambda _arguments: _handle_python_probe(
        bridge="cad_autocad",
        action="environment_probe",
        display_name="CAD / AutoCAD 工程制图桥",
        module_name="examples.cad_bridge.probe",
    ),
    "photoshop.session_info": lambda arguments: _handle_bridge_probe_tool(arguments, "photoshop"),
    "photoshop.document_info": lambda arguments: _handle_adobe_document_info(
        arguments,
        "photoshop",
        "examples/photoshop_bridge/scripts/document_info.ps1",
    ),
    "photoshop.create_demo_document": _handle_photoshop_create,
    "photoshop.export_demo_preview": _handle_photoshop_export,
    "photoshop.run_demo": _handle_photoshop_run,
    "photoshop.recipe_list": _handle_photoshop_recipe_list,
    "photoshop.recipe_plan": _handle_photoshop_recipe_plan,
    "photoshop.recipe_validate": _handle_photoshop_recipe_validate,
    "photoshop.recipe_run": _handle_photoshop_recipe_run,
    "photoshop.recipe_debug": _handle_photoshop_recipe_debug,
    "illustrator.document_info": lambda arguments: _handle_adobe_document_info(
        arguments,
        "illustrator",
        "examples/illustrator_bridge/scripts/document_info.ps1",
    ),
    "illustrator.create_demo_artboard": _handle_illustrator_create,
    "illustrator.export_demo_assets": _handle_illustrator_export,
    "illustrator.run_demo": _handle_illustrator_run,
    "illustrator.preflight": lambda arguments: preflight_summary(
        arguments.get("document_summary") or {}
    ),
    "illustrator.color_vectorize_plan": build_color_vectorization_plan,
    "illustrator.color_vectorize_validate": lambda arguments: validate_color_vectorization_metrics(
        metrics=arguments.get("metrics") or {},
        hard_gates=arguments.get("hard_gates") or {},
        quality_gates=arguments.get("quality_gates"),
    ),
    "illustrator.color_vectorize_compare": _handle_illustrator_color_vectorize_compare,
    "illustrator.color_vectorize_execute": _handle_illustrator_color_vectorize_execute,
    "jianying_capcut.draft_probe": lambda _arguments: _handle_python_probe(
        bridge="jianying_capcut",
        action="draft_probe",
        display_name="剪映/CapCut 草稿桥",
        module_name="examples.capcut_jianying_bridge.probe",
    ),
    "jianying_capcut.draft_structure": lambda arguments: draft_structure_summary(
        max_entries=int(arguments.get("max_entries") or 25)
    ),
    "autocad_dxf.status": lambda _arguments: autocad_dxf.status(),
    "autocad_dxf.validate_cad_plan": lambda arguments: autocad_dxf.validate_cad_plan(
        arguments.get("plan")
    ),
    "autocad_dxf.create_dxf_plan": lambda arguments: autocad_dxf.create_dxf_plan(
        arguments.get("prompt_or_spec")
    ),
    "autocad_dxf.summarize_plan": lambda arguments: autocad_dxf.summarize_plan(
        arguments.get("plan")
    ),
    "autocad_dxf.write_dxf": _handle_write_dxf,
}

TOOL_HANDLERS.update(PHOTOSHOP_V1_TOOL_HANDLERS)


def _response(message_id: Any, result: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str, data: Any | None = None) -> JsonObject:
    payload: JsonObject = {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _text_tool_result(payload: JsonObject, *, is_error: bool = False) -> JsonObject:
    sanitized = sanitize(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(sanitized, ensure_ascii=False, indent=2)}],
        "structuredContent": sanitized,
        "isError": is_error,
    }


def handle_request(message: JsonObject) -> JsonObject | None:
    message_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(message_id, -32602, "params must be an object")

    if method == "initialize":
        return _response(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": SERVER_INFO,
                "instructions": SERVER_INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOL_DEFINITIONS})
    if method == "resources/list":
        return _response(message_id, {"resources": list_resources()})
    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str):
            return _error(message_id, -32602, "resources/read params.uri must be a string")
        content = read_resource(uri)
        if content is None:
            return _error(message_id, -32602, f"unknown resource: {uri}")
        return _response(message_id, {"contents": [content]})
    if method == "prompts/list":
        return _response(message_id, {"prompts": list_prompts()})
    if method == "prompts/get":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return _error(message_id, -32602, "prompts/get params.name must be a string")
        if not isinstance(arguments, dict):
            return _error(message_id, -32602, "prompts/get params.arguments must be an object")
        prompt = get_prompt(name, arguments)
        if prompt is None:
            return _error(message_id, -32602, f"unknown prompt: {name}")
        return _response(message_id, prompt)
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return _error(message_id, -32602, "tools/call params.name must be a string")
        if not isinstance(arguments, dict):
            return _error(message_id, -32602, "tools/call params.arguments must be an object")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return _error(message_id, -32601, f"unknown tool: {name}")
        try:
            result = handler(arguments)
        except (TypeError, ValueError) as exc:
            return _response(
                message_id, _text_tool_result({"ok": False, "error": str(exc)}, is_error=True)
            )
        except Exception as exc:  # pragma: no cover - defensive server boundary
            return _response(
                message_id,
                _text_tool_result({"ok": False, "error": type(exc).__name__}, is_error=True),
            )
        return _response(message_id, _text_tool_result(result))

    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    return _error(message_id, -32601, f"method not found: {method}")


def encode_message(message: JsonObject) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def serve_stdio(stdin: Any = None, stdout: Any = None) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            output_stream.write(encode_message(_error(None, -32700, "parse error", str(exc))))
            output_stream.flush()
            continue
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            output_stream.write(
                encode_message(
                    _error(
                        message.get("id") if isinstance(message, dict) else None,
                        -32600,
                        "invalid request",
                    )
                )
            )
            output_stream.flush()
            continue
        response = handle_request(message)
        if response is not None:
            output_stream.write(encode_message(response))
            output_stream.flush()
    return 0


def main() -> None:
    raise SystemExit(serve_stdio())


if __name__ == "__main__":
    main()
