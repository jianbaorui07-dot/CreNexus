from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from starbridge_mcp.bridges import autocad_dxf
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.core.tool_registry import capability_summary
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
        name="illustrator.document_info",
        title="Probe Illustrator Document",
        description="通过状态探针检查 Illustrator COM 线索；只读，不打开私有 .ai 文件。",
        input_schema=_object_schema(
            {"probe_com": {"type": "boolean", "default": True, "description": "是否尝试连接已打开的 Illustrator COM 对象。"}}
        ),
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
    )


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "starbridge.status": _handle_status,
    "starbridge.probe": _handle_probe,
    "starbridge.tools": _handle_tools,
    "comfyui.system_probe": _handle_comfy_system_probe,
    "comfyui.workflow_validate": _handle_workflow_validate,
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
    "illustrator.document_info": lambda arguments: _handle_bridge_probe_tool(arguments, "illustrator"),
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
