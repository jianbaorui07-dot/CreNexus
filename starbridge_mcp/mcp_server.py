from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from starbridge_mcp.bridges import autocad_dxf
from starbridge_mcp.core.evidence import (
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    manifest_validation_result,
    repo_relative,
    save_manifest,
)
from starbridge_mcp.core.job_status import JobStatus
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.core.tool_registry import capability_summary, list_capabilities
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


def _safe_read_annotations() -> JsonObject:
    return {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _guarded_write_annotations() -> JsonObject:
    return {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


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
                "bridge": {"type": "string", "enum": [item for item in BRIDGE_ENUM if item != "all"]},
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
    _standard_tool(
        name="starbridge.evidence_init",
        title="Initialize Evidence Manifest",
        description="Create a sanitized EvidenceManifest for a bridge action. Safe by default and limited to examples/output/evidence.",
        input_schema=_object_schema(
            {
                "bridge": {"type": "string", "default": "starbridge"},
                "action_name": {"type": "string", "default": "evidence_init"},
                "status": {
                    "type": "string",
                    "enum": ["queued", "running", "completed", "failed", "cancelled", "needs_user"],
                    "default": "queued",
                },
                "manifest_path": {"type": "string", "default": "examples/output/evidence/manifest.latest.json"},
                "job_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "persist": {"type": "boolean", "default": False},
            }
        ),
    ),
    _standard_tool(
        name="starbridge.evidence_validate",
        title="Validate Evidence Manifest",
        description="Validate a StarBridge evidence manifest stored under examples/output/evidence without launching local software.",
        input_schema=_object_schema(
            {
                "manifest_path": {"type": "string", "default": "examples/output/evidence/manifest.latest.json"},
            }
        ),
    ),
    _standard_tool(
        name="starbridge.job_status",
        title="Read Job Status",
        description="Return a unified job status summary backed by a StarBridge evidence manifest.",
        input_schema=_object_schema(
            {
                "manifest_path": {"type": "string", "default": "examples/output/evidence/manifest.latest.json"},
                "job_id": {"type": "string"},
                "message": {"type": "string", "default": "evidence manifest available"},
                "progress": {"type": "integer", "minimum": 0, "maximum": 100},
            }
        ),
    ),
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
        title="Plan ComfyUI Workflow Build",
        description="Build a dry-run plan for txt2img, img2img, inpaint, or upscale without reading files or submitting a job.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string"},
                "workflow_type": {"type": "string", "enum": ["txt2img", "img2img", "inpaint", "upscale"], "default": "txt2img"},
                "style": {"type": "string"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
            },
            required=["goal"],
        ),
    ),
    _standard_tool(
        name="comfyui.workflow_build",
        title="Build ComfyUI Workflow",
        description="Generate a valid ComfyUI API-format txt2img workflow JSON from a natural-language goal. Does not submit to ComfyUI.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string"},
                "workflow_type": {"type": "string", "enum": ["txt2img", "img2img", "inpaint", "upscale"], "default": "txt2img"},
                "style": {"type": "string"},
                "positive_prompt": {"type": "string"},
                "negative_prompt": {"type": "string"},
                "checkpoint": {"type": "string"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 1.0, "maximum": 30.0},
                "seed": {"type": "integer"},
                "sampler_name": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
            },
            required=["goal"],
        ),
    ),
    _standard_tool(
        name="comfy.workflow_draft",
        title="Draft ComfyUI Workflow",
        description="Generate API-like draft workflow JSON for txt2img, img2img, inpaint, or upscale. Draft only; no filesystem reads, network calls, or queue submission.",
        input_schema=_object_schema(
            {
                "task_type": {"type": "string", "enum": ["txt2img", "img2img", "inpaint", "upscale"], "default": "txt2img"},
                "prompt": {"type": "string"},
                "positive_prompt": {"type": "string"},
                "negative_prompt": {"type": "string"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer"},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 1.0, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "sampler_name": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "denoise": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "scale_by": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 8.0},
                "checkpoint": {"type": "string", "description": "Optional placeholder model name; real paths and checkpoint filenames are replaced with placeholders."},
            },
            required=["task_type"],
        ),
    ),
    _standard_tool(
        name="comfy.workflow_compose",
        title="Compose ComfyUI Workflow Graph",
        description="Compose API-like ComfyUI workflow JSON from safe placeholder graph modules for txt2img, img2img, inpaint, or upscale. No filesystem reads, network calls, or queue submission.",
        input_schema=_object_schema(
            {
                "task_type": {"type": "string", "enum": ["txt2img", "img2img", "inpaint", "upscale"], "default": "txt2img"},
                "prompt": {"type": "string", "description": "Positive prompt text used only inside the draft graph."},
                "positive_prompt": {"type": "string", "description": "Alias for prompt."},
                "negative_prompt": {"type": "string", "default": "low quality, blurry, distorted"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "seed": {"type": "integer", "description": "Deterministic placeholder seed."},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 1.0, "maximum": 30.0},
                "sampler": {"type": "string", "default": "euler"},
                "sampler_name": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "denoise": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "scale": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 8.0},
                "scale_by": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 8.0},
                "checkpoint": {"type": "string", "description": "Optional placeholder model label; real paths and checkpoint filenames are replaced with placeholders."},
            },
            required=["task_type"],
        ),
    ),
    _standard_tool(
        name="comfy.workflow_template_list",
        title="List ComfyUI Workflow Templates",
        description="List bundled placeholder-only ComfyUI workflow templates and lint status. No private filesystem reads, network calls, or queue submission.",
        input_schema=_object_schema({}),
    ),
    _standard_tool(
        name="comfy.workflow_template_get",
        title="Get ComfyUI Workflow Template",
        description="Return one bundled placeholder-only ComfyUI workflow template by template_id. No private filesystem reads, network calls, or queue submission.",
        input_schema=_object_schema(
            {
                "template_id": {
                    "type": "string",
                    "enum": [
                        "txt2img_basic_v1",
                        "img2img_basic_v1",
                        "inpaint_basic_v1",
                        "upscale_basic_v1",
                        "creative_poster_complex_v1",
                    ],
                }
            },
            required=["template_id"],
        ),
    ),
    _standard_tool(
        name="comfy.workflow_from_template",
        title="Compose ComfyUI Workflow From Template",
        description="Compose placeholder-only API-like ComfyUI workflow JSON from a bundled template. Does not read model/image paths, use network, or submit queue jobs.",
        input_schema=_object_schema(
            {
                "template_id": {
                    "type": "string",
                    "enum": [
                        "txt2img_basic_v1",
                        "img2img_basic_v1",
                        "inpaint_basic_v1",
                        "upscale_basic_v1",
                        "creative_poster_complex_v1",
                    ],
                },
                "arguments": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Optional placeholder composer arguments such as prompt, width, height, seed, steps, cfg, sampler, scheduler, denoise, or scale_by.",
                },
            },
            required=["template_id"],
        ),
    ),
    _standard_tool(
        name="comfyui.workflow_repair",
        title="Repair ComfyUI Workflow",
        description="Repair missing txt2img nodes, bad sampler values, invalid dimensions, prompt text, and broken core links without submitting a job.",
        input_schema=_object_schema(
            {
                "workflow": {"type": "object"},
                "goal": {"type": "string"},
                "positive_prompt": {"type": "string"},
                "negative_prompt": {"type": "string"},
                "checkpoint": {"type": "string"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
            },
            required=["workflow"],
        ),
    ),
    _standard_tool(
        name="comfyui.agent_run",
        title="Run ComfyUI Agent Workflow",
        description="Build, validate, optionally repair, and only with confirm_run=true submit a generated ComfyUI txt2img workflow.",
        input_schema=_object_schema(
            {
                "goal": {"type": "string"},
                "workflow_type": {"type": "string", "enum": ["txt2img", "img2img", "inpaint", "upscale"], "default": "txt2img"},
                "style": {"type": "string"},
                "positive_prompt": {"type": "string"},
                "negative_prompt": {"type": "string"},
                "checkpoint": {"type": "string"},
                "width": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "height": {"type": "integer", "default": 1024, "minimum": 64, "maximum": 4096},
                "steps": {"type": "integer", "default": 20, "minimum": 1, "maximum": 150},
                "cfg": {"type": "number", "default": 7.0, "minimum": 1.0, "maximum": 30.0},
                "seed": {"type": "integer"},
                "sampler_name": {"type": "string", "default": "euler"},
                "scheduler": {"type": "string", "default": "normal"},
                "filename_prefix": {"type": "string", "default": "starbridge_agent_txt2img"},
                "comfy_url": {"type": "string"},
                "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 300},
                "wait_seconds": {"type": "integer", "default": 10, "minimum": 0, "maximum": 600},
                "timeout_seconds": {"type": "integer", "default": 10, "minimum": 0, "maximum": 600},
                "confirm_run": {"type": "boolean", "default": False},
            },
            required=["goal"],
        ),
        read_only=False,
    ),
    _standard_tool(
        name="blender.environment_probe",
        title="Probe Blender",
        description="检查 Blender 可执行文件和可选环境配置。不打开 .blend，不运行脚本。",
        input_schema=_object_schema({}),
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
            {"probe_com": {"type": "boolean", "default": True, "description": "是否尝试连接已打开的 Photoshop COM 对象。"}}
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
        name="illustrator.document_info",
        title="Probe Illustrator Document",
        description="Read the active Illustrator document summary through COM without opening private AI files.",
        input_schema=_object_schema(
            {"probe_com": {"type": "boolean", "default": True, "description": "是否尝试连接已打开的 Illustrator COM 对象。"}}
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
        name="jianying_capcut.draft_probe",
        title="Probe Jianying / CapCut Drafts",
        description="检查剪映/CapCut 可执行文件和草稿目录环境变量。不读取草稿内容，不导出视频。",
        input_schema=_object_schema({}),
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


def _namespace_for_status(arguments: JsonObject, *, probe_default: bool = False) -> argparse.Namespace:
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
    bridge = BRIDGE_ALIASES.get(str(arguments.get("bridge") or "all"), str(arguments.get("bridge") or "all"))
    return capability_summary(bridge=bridge, include_guarded=not bool(arguments.get("safe_only", False)))


def _handle_evidence_init(arguments: JsonObject) -> JsonObject:
    manifest = create_manifest(
        bridge=str(arguments.get("bridge") or "starbridge"),
        action=str(arguments.get("action_name") or "evidence_init"),
        status=str(arguments.get("status") or "queued"),
        job_id=arguments.get("job_id"),
        plan_id=arguments.get("plan_id"),
    )
    manifest_path = ensure_evidence_path(arguments.get("manifest_path"))
    if bool(arguments.get("persist", False)):
        save_manifest(manifest, manifest_path)
    return sanitize(
        {
            "ok": True,
            "bridge": manifest.bridge,
            "action": "evidence_init",
            "message": "initialized evidence manifest",
            "details": {
                "manifest": manifest.to_dict(),
                "manifest_path": repo_relative(manifest_path),
                "persisted": bool(arguments.get("persist", False)),
            },
            "warnings": [],
            "next_steps": ["Use starbridge.evidence_validate to verify field shape and status vocabulary."],
        }
    )


def _handle_evidence_validate(arguments: JsonObject) -> JsonObject:
    payload = load_manifest(arguments.get("manifest_path"))
    validation = manifest_validation_result(payload)
    return sanitize(
        {
            "ok": validation.ok,
            "bridge": str(payload.get("bridge") or "starbridge"),
            "action": "evidence_validate",
            "message": validation.message,
            "details": {
                "manifest_path": repo_relative(ensure_evidence_path(arguments.get("manifest_path"))),
                "validation": validation.to_dict(),
            },
            "warnings": list(validation.warnings),
            "next_steps": [] if validation.ok else ["Reinitialize the manifest inside examples/output/evidence and validate again."],
        }
    )


def _handle_job_status(arguments: JsonObject) -> JsonObject:
    payload = load_manifest(arguments.get("manifest_path"))
    progress = arguments.get("progress")
    resolved_progress = int(progress) if progress is not None else (100 if payload.get("status") == "completed" else 0)
    job_status = JobStatus(
        job_id=str(arguments.get("job_id") or payload.get("job_id") or payload.get("manifest_id")),
        bridge=str(payload.get("bridge") or "starbridge"),
        action=str(payload.get("action") or "job_status"),
        status=str(payload.get("status") or "queued"),
        progress=resolved_progress,
        message=str(arguments.get("message") or "evidence manifest available"),
        evidence_manifest={
            "manifest_id": payload.get("manifest_id"),
            "manifest_path": repo_relative(ensure_evidence_path(arguments.get("manifest_path"))),
        },
        next_steps=["Review warnings and validation before wiring this status into a bridge execution loop."],
    )
    return sanitize(
        {
            "ok": True,
            "bridge": job_status.bridge,
            "action": "job_status",
            "message": job_status.message,
            "details": job_status.to_dict(),
            "warnings": [],
            "next_steps": job_status.next_steps,
        }
    )


def _report_to_result(*, bridge: str, action: str, report: JsonObject, display_name: str) -> JsonObject:
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


def _handle_python_probe(*, bridge: str, action: str, display_name: str, module_name: str) -> JsonObject:
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

    template_arguments = arguments.get("arguments") or {}
    if not isinstance(template_arguments, dict):
        raise ValueError("arguments must be an object when provided")
    return compose_from_template(str(arguments.get("template_id") or ""), template_arguments)


def _handle_comfy_workflow_repair(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import workflow_repair

    return workflow_repair(arguments)


def _handle_comfy_agent_run(arguments: JsonObject) -> JsonObject:
    from examples.comfy_bridge.workflow_agent import agent_run

    return agent_run(arguments)


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
                "next_steps": ["Call again with dry_run=true first, or set confirm_write=true for a sandboxed output path."],
            }
        )
    return autocad_dxf.write_dxf(
        arguments.get("plan"),
        str(arguments.get("output_path") or ""),
        dry_run=dry_run,
        confirm_write=bool(arguments.get("confirm_write", False)),
    )


REPO_ROOT = Path(__file__).resolve().parents[1]


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
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path), *(extra_args or [])],
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
                "next_steps": ["Run the matching npm.cmd script locally to inspect the environment error."],
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


def _adobe_refusal(*, bridge: str, task: str, confirm_key: str) -> JsonObject:
    return sanitize(
        {
            "ok": False,
            "bridge": bridge,
            "task": task,
            "dry_run": False,
            confirm_key: False,
            "warnings": [f"Refusing real {bridge} write/export without {confirm_key}=true."],
            "next_steps": ["Run the dry-run plan first, then call again with explicit confirmation for sandbox output."],
        }
    )


def _handle_adobe_document_info(arguments: JsonObject, bridge: str, script_relative: str) -> JsonObject:
    if not bool(arguments.get("probe_com", True)):
        return sanitize(
            {
                "ok": False,
                "bridge": bridge,
                "task": "document_info",
                "active_document": False,
                "warnings": ["COM probing was skipped by request."],
                "next_steps": [f"Run the {bridge}:info npm script on a Windows machine with the Adobe app available."],
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
        "document": {"name": "starbridge_ai_demo.ai", "width": width, "height": height, "color_space": "RGB"},
        "artboards": [{"index": 0, "width": width, "height": height}],
        "layers": ["background", "foreground"],
        "objects_created": ["background rectangle", "title text", "subtitle text", "circle", "rectangle", "line", "path"],
        "output_ai_path": f"{output_dir}/starbridge_ai_demo.ai",
        "warnings": [],
        "next_steps": ["Call again with dry_run=false and confirm_write=true to create the sandbox demo document."],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_write:
        return _adobe_refusal(bridge="illustrator", task="create_demo_artboard", confirm_key="confirm_write")
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
        "next_steps": ["Call again with dry_run=false and confirm_export=true after creating the sandbox demo document."],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_export:
        return _adobe_refusal(bridge="illustrator", task="export_demo_assets", confirm_key="confirm_export")
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
                "commands": ["npm.cmd run illustrator:demo:plan", "npm.cmd run illustrator:demo", "npm.cmd run illustrator:manifest"],
                "warnings": [],
                "next_steps": ["Call again with dry_run=false, confirm_write=true, and confirm_export=true to run the local demo."],
            }
        )
    if not bool(arguments.get("confirm_write", False)):
        return _adobe_refusal(bridge="illustrator", task="sandbox_vector_demo", confirm_key="confirm_write")
    if not bool(arguments.get("confirm_export", False)):
        return _adobe_refusal(bridge="illustrator", task="sandbox_vector_demo", confirm_key="confirm_export")
    return _run_powershell_json("examples/illustrator_bridge/scripts/run_demo.ps1")


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
        "document": {"name": "starbridge_ps_demo.psd", "width": width, "height": height, "dpi": dpi, "color_mode": "RGB"},
        "layers_created": ["background", "color_block_left", "color_block_right", "title_text", "subtitle_text"],
        "output_psd_path": f"{output_dir}/starbridge_ps_demo.psd",
        "warnings": [],
        "next_steps": ["Call again with dry_run=false and confirm_write=true to create the sandbox demo PSD."],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_write:
        return _adobe_refusal(bridge="photoshop", task="create_demo_document", confirm_key="confirm_write")
    return _run_powershell_json(
        "examples/photoshop_bridge/scripts/create_demo_document.ps1",
        ["-Width", str(width), "-Height", str(height), "-Dpi", str(dpi), "-OutputDir", output_dir, "-ConfirmWrite"],
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
        "exported_files": [f"{output_dir}/starbridge_ps_demo.png", f"{output_dir}/starbridge_ps_demo.jpg"],
        "width": 1080,
        "height": 1080,
        "layer_count": None,
        "warnings": [],
        "next_steps": ["Call again with dry_run=false and confirm_export=true after creating the sandbox demo PSD."],
    }
    if dry_run:
        return sanitize(result)
    if not confirm_export:
        return _adobe_refusal(bridge="photoshop", task="export_demo_preview", confirm_key="confirm_export")
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
                "commands": ["npm.cmd run photoshop:demo:plan", "npm.cmd run photoshop:demo", "npm.cmd run photoshop:manifest"],
                "warnings": [],
                "next_steps": ["Call again with dry_run=false, confirm_write=true, and confirm_export=true to run the local demo."],
            }
        )
    if not bool(arguments.get("confirm_write", False)):
        return _adobe_refusal(bridge="photoshop", task="sandbox_ps_demo", confirm_key="confirm_write")
    if not bool(arguments.get("confirm_export", False)):
        return _adobe_refusal(bridge="photoshop", task="sandbox_ps_demo", confirm_key="confirm_export")
    return _run_powershell_json("examples/photoshop_bridge/scripts/run_demo.ps1")


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "starbridge.status": _handle_status,
    "starbridge.probe": _handle_probe,
    "starbridge.tools": _handle_tools,
    "starbridge.evidence_init": _handle_evidence_init,
    "starbridge.evidence_validate": _handle_evidence_validate,
    "starbridge.job_status": _handle_job_status,
    "comfyui.system_probe": _handle_comfy_system_probe,
    "comfyui.workflow_validate": _handle_workflow_validate,
    "comfyui.workflow_build_plan": _handle_comfy_workflow_build_plan,
    "comfyui.workflow_build": _handle_comfy_workflow_build,
    "comfy.workflow_draft": _handle_comfy_workflow_draft,
    "comfy.workflow_compose": _handle_comfy_workflow_compose,
    "comfy.workflow_template_list": _handle_comfy_workflow_template_list,
    "comfy.workflow_template_get": _handle_comfy_workflow_template_get,
    "comfy.workflow_from_template": _handle_comfy_workflow_from_template,
    "comfyui.workflow_repair": _handle_comfy_workflow_repair,
    "comfyui.agent_run": _handle_comfy_agent_run,
    "blender.environment_probe": lambda _arguments: _handle_python_probe(
        bridge="blender",
        action="environment_probe",
        display_name="Blender 三维场景桥",
        module_name="examples.blender_bridge.probe",
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
    "illustrator.document_info": lambda arguments: _handle_adobe_document_info(
        arguments,
        "illustrator",
        "examples/illustrator_bridge/scripts/document_info.ps1",
    ),
    "illustrator.create_demo_artboard": _handle_illustrator_create,
    "illustrator.export_demo_assets": _handle_illustrator_export,
    "illustrator.run_demo": _handle_illustrator_run,
    "jianying_capcut.draft_probe": lambda _arguments: _handle_python_probe(
        bridge="jianying_capcut",
        action="draft_probe",
        display_name="剪映/CapCut 草稿桥",
        module_name="examples.capcut_jianying_bridge.probe",
    ),
    "autocad_dxf.status": lambda _arguments: autocad_dxf.status(),
    "autocad_dxf.validate_cad_plan": lambda arguments: autocad_dxf.validate_cad_plan(arguments.get("plan")),
    "autocad_dxf.create_dxf_plan": lambda arguments: autocad_dxf.create_dxf_plan(arguments.get("prompt_or_spec")),
    "autocad_dxf.summarize_plan": lambda arguments: autocad_dxf.summarize_plan(arguments.get("plan")),
    "autocad_dxf.write_dxf": _handle_write_dxf,
}


def _apply_risk_metadata() -> None:
    registry = {item["name"]: item for item in list_capabilities()}
    default_metadata = {
        "riskLevel": "safe_read_only",
        "safeDefault": True,
        "requiresConfirmation": False,
        "requiresLocalSoftware": False,
    }
    for tool in TOOL_DEFINITIONS:
        capability = registry.get(tool["name"], {})
        annotations = tool.setdefault("annotations", {})
        annotations.update(
            {
                "riskLevel": capability.get("risk_level", default_metadata["riskLevel"]),
                "safeDefault": capability.get("safe_default", default_metadata["safeDefault"]),
                "requiresConfirmation": capability.get("requires_confirmation", default_metadata["requiresConfirmation"]),
                "requiresLocalSoftware": capability.get("requires_local_software", default_metadata["requiresLocalSoftware"]),
                "currentStatus": capability.get("current_status", "stable"),
            }
        )


_apply_risk_metadata()


def _response(message_id: Any, result: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str, data: Any | None = None) -> JsonObject:
    payload: JsonObject = {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}
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
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOL_DEFINITIONS})
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
            return _response(message_id, _text_tool_result({"ok": False, "error": str(exc)}, is_error=True))
        except Exception as exc:  # pragma: no cover - defensive server boundary
            return _response(message_id, _text_tool_result({"ok": False, "error": type(exc).__name__}, is_error=True))
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
            output_stream.write(encode_message(_error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request")))
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
