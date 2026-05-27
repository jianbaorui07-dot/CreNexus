from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from starbridge_mcp.core.config import StarBridgeConfig, env_summary
from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.core.tool_registry import capability_summary


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


BRIDGE_NAME_MAP = {
    "ComfyUI": "comfyui",
    "Blender": "blender",
    "CAD": "autocad",
    "Photoshop": "photoshop",
    "Illustrator": "illustrator",
    "JianyingCapCut": "jianying_capcut",
}

BRIDGE_ALIASES = {
    "cad_autocad": "autocad",
    "cad_dxf": "autocad_dxf",
    "capcut_jianying": "jianying_capcut",
}

BRIDGE_PROFILES: dict[str, dict[str, Any]] = {
    "comfyui": {
        "display_name": "ComfyUI 图像生成桥",
        "software": "ComfyUI",
        "probe_type": "HTTP read-only probe",
        "required_env": ["STARBRIDGE_COMFYUI_URL", "COMFY_ROOT", "COMFY_LAUNCHER"],
        "ready_when": "ComfyUI API 可访问，且 /system_stats 与 /object_info 可读。",
        "safety_boundary": "只读检查本机 API，不读取模型文件，不提交生成图片。",
        "current_actions": ["status", "probe"],
    },
    "photoshop": {
        "display_name": "Photoshop 修图桥",
        "software": "Adobe Photoshop",
        "probe_type": "Windows COM / executable configuration probe",
        "required_env": ["PHOTOSHOP_EXE"],
        "ready_when": "pywin32 可用；严格探测时能连接 Photoshop.Application COM。",
        "safety_boundary": "不打开 PSD，不读取素材路径，不写出导出结果。",
        "current_actions": ["status", "probe"],
    },
    "illustrator": {
        "display_name": "AI 矢量文件桥",
        "software": "Adobe Illustrator",
        "probe_type": "Windows COM / executable configuration probe",
        "required_env": ["ILLUSTRATOR_EXE"],
        "ready_when": "pywin32 可用；严格探测时能连接 Illustrator.Application COM。",
        "safety_boundary": "不打开 .ai 私有工程，不读取源图或导出目录。",
        "current_actions": ["status", "probe"],
    },
    "blender": {
        "display_name": "Blender 三维场景桥",
        "software": "Blender",
        "probe_type": "Executable and optional MCP directory probe",
        "required_env": ["BLENDER_EXE", "BLENDER_MCP_DIR"],
        "ready_when": "找到 blender.exe；可选找到 Blender MCP 桥目录。",
        "safety_boundary": "不打开私有 .blend，不渲染资产，不下载外部模型。",
        "current_actions": ["status", "probe"],
    },
    "autocad": {
        "display_name": "CAD 工程制图桥",
        "software": "AutoCAD / CAD",
        "probe_type": "MCP project, executable, and win32com probe",
        "required_env": ["AUTOCAD_EXE", "STARBRIDGE_CAD_MODE"],
        "ready_when": "AutoCAD MCP 子项目存在，且找到 AutoCAD 可执行文件或 COM 线索。",
        "safety_boundary": "不打开客户 DWG/DXF，不写真实项目输出；离线 DXF 与真实 CAD 控制分开处理。",
        "current_actions": ["status", "probe"],
    },
    "autocad_dxf": {
        "display_name": "AutoCAD / DXF 离线生成桥",
        "software": "DXF headless bridge",
        "probe_type": "schema and dry-run status",
        "required_env": [],
        "ready_when": "无需 AutoCAD；CAD plan 可校验，DXF 写入默认 dry-run。",
        "safety_boundary": "不打开 DWG，不控制 AutoCAD；dry_run=False 时只允许写入 examples/cad/output。",
        "current_actions": ["status", "validate_cad_plan", "summarize_plan", "write_dxf"],
    },
    "jianying_capcut": {
        "display_name": "剪映/CapCut 草稿桥",
        "software": "剪映 / CapCut",
        "probe_type": "Executable and draft directory configuration probe",
        "required_env": ["JIANYING_EXE", "JIANYING_DRAFTS_DIR", "CAPCUT_EXE", "CAPCUT_DRAFTS_DIR"],
        "ready_when": "找到剪映或 CapCut 可执行文件，并确认对应草稿目录。",
        "safety_boundary": "只读检查配置，不读取草稿内容，不导出视频，不触碰账号。",
        "current_actions": ["status", "probe"],
    },
}


def _legacy_status_to_ok(status: str) -> bool:
    return status == "ok"


def _next_steps_from_legacy(details: list[str], status: str) -> list[str]:
    steps = []
    for detail in details:
        if "处理建议" in detail or "下一步" in detail:
            steps.append(detail)
    if not steps and status != "ok":
        steps.append("根据 details 配置本机软件、环境变量或先手动启动对应桌面软件。")
    return steps


def normalize_legacy_status(result: dict[str, Any]) -> dict[str, Any]:
    name = str(result.get("name") or result.get("bridge_id") or "unknown")
    bridge = BRIDGE_NAME_MAP.get(name, name.lower())
    profile = BRIDGE_PROFILES.get(bridge, {})
    status = str(result.get("status") or ("ok" if result.get("ok") else "warn"))
    details_list = [str(item) for item in result.get("details", [])]
    warnings = []
    if status != "ok":
        warnings.append(str(result.get("status_label") or status))
        warnings.append(f"{profile.get('display_name', name)} 当前未完全就绪，详见 details.notes。")
    message = str(profile.get("display_name") or result.get("label") or name)
    unified = make_result(
        ok=_legacy_status_to_ok(status),
        bridge=bridge,
        action="status",
        message=f"{message}: {status}",
        details={
            "status": status,
            "display_name": profile.get("display_name", result.get("label") or name),
            "software": profile.get("software", name),
            "probe_type": profile.get("probe_type", "status probe"),
            "required_env": profile.get("required_env", []),
            "ready_when": profile.get("ready_when", ""),
            "safety_boundary": profile.get("safety_boundary", ""),
            "current_actions": profile.get("current_actions", ["status"]),
            "legacy_status": status,
            "legacy_name": name,
            "data": result.get("data", {}),
            "notes": details_list,
        },
        warnings=warnings,
        next_steps=_next_steps_from_legacy(details_list, status),
    )
    sanitized = sanitize(unified)
    validate_result(sanitized)
    return sanitized


def collect_status(*, comfy_url: str, timeout: int, probe_executables: bool) -> list[dict[str, Any]]:
    from examples import bridge_status as legacy
    from starbridge_mcp.bridges.autocad_dxf import status as autocad_dxf_status

    legacy_results = [
        legacy.check_comfy(comfy_url, timeout),
        legacy.check_blender(probe_executables, timeout),
        legacy.check_cad(),
        legacy.check_photoshop(probe_executables),
        legacy.check_illustrator(probe_executables),
        legacy.check_jianying_capcut(),
    ]
    return [normalize_legacy_status(item) for item in legacy_results] + [autocad_dxf_status()]


def build_response(args: argparse.Namespace) -> dict[str, Any]:
    requested_bridge = BRIDGE_ALIASES.get(args.bridge, args.bridge)
    if args.action == "tools":
        return capability_summary(
            bridge=requested_bridge,
            include_guarded=not args.safe_only,
        )

    config = StarBridgeConfig(timeout=args.timeout)
    comfy_url = args.comfy_url or config.comfy_url
    results = collect_status(
        comfy_url=comfy_url,
        timeout=args.timeout,
        probe_executables=args.probe_executables,
    )
    if requested_bridge != "all":
        results = [item for item in results if item["bridge"] == requested_bridge]
    return sanitize(
        {
            "ok": all(item["ok"] for item in results),
            "framework": "StarBridge",
            "action": "status",
            "results": results,
            "env": env_summary(),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="StarBridge 本地创意软件 MCP 桥接框架最小状态入口。")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "tools"], help="当前实现 status 和 tools。")
    parser.add_argument(
        "--bridge",
        default="all",
        choices=[
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
        ],
    )
    parser.add_argument("--comfy-url", default=None)
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--probe-executables", action="store_true")
    parser.add_argument("--safe-only", action="store_true", help="tools 动作只列出 safe_default 能力。")
    parser.add_argument("--json", action="store_true", help="保留给兼容；当前始终输出 JSON。")
    parser.add_argument("--strict", action="store_true", help="任一 bridge 未通过时返回退出码 1。")
    args = parser.parse_args()

    response = build_response(args)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    if args.strict and args.action == "status" and any(not item["ok"] for item in response["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("建议使用 Python 3.10 或更新版本运行 StarBridge。")
    main()
