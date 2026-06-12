from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from starbridge_mcp.core.config import StarBridgeConfig, env_summary
from starbridge_mcp.core.computer_use import (
    ActionPlan,
    CodexComputerUseAdapter,
    LocalScreenshotEvidenceStore,
    evaluate_safety,
    render_plan_summary,
)
from starbridge_mcp.core.computer_use_demos import run_demo
from starbridge_mcp.core.evidence import (
    DEFAULT_MANIFEST_FILENAME,
    ExecutionResult,
    create_manifest,
    ensure_evidence_path,
    load_manifest,
    manifest_validation_result,
    repo_relative,
    save_manifest,
)
from starbridge_mcp.core.job_status import JobStatus
from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.safe_roots import safe_roots_summary
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
    if args.action == "roots":
        return safe_roots_summary(bridge=requested_bridge)

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


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(sanitize(payload), ensure_ascii=False, indent=2))


def _default_manifest_path() -> Path:
    return ensure_evidence_path()


def _manifest_summary(payload: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    return sanitize(
        {
            "manifest_path": repo_relative(manifest_path),
            "manifest_id": payload.get("manifest_id"),
            "bridge": payload.get("bridge"),
            "action": payload.get("action"),
            "status": payload.get("status"),
            "dry_run": payload.get("dry_run"),
        }
    )


def _handle_evidence_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Create or validate StarBridge evidence manifests.")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--add-file", dest="add_file", action="store_true")
    parser.add_argument("--add-screenshot", dest="add_screenshot", action="store_true")
    parser.add_argument("--manifest-path", default=str(_default_manifest_path().relative_to(REPO_ROOT)))
    parser.add_argument("--bridge", default="starbridge")
    parser.add_argument("--action-name", default="evidence_init")
    parser.add_argument("--status", default="queued")
    parser.add_argument("--job-id")
    parser.add_argument("--plan-id")
    parser.add_argument("--label")
    parser.add_argument("--path")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--no-dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    modes = [args.init, args.validate, args.add_file, args.add_screenshot]
    if sum(bool(mode) for mode in modes) != 1:
        raise SystemExit("choose exactly one of --init, --validate, --add-file, or --add-screenshot")

    manifest_path = ensure_evidence_path(args.manifest_path)
    if args.init:
        manifest = create_manifest(
            bridge=args.bridge,
            action=args.action_name,
            status=args.status,
            dry_run=not args.no_dry_run,
            confirm_write=args.confirm_write,
            job_id=args.job_id,
            plan_id=args.plan_id,
        )
        saved = save_manifest(manifest, manifest_path)
        result = ExecutionResult(
            ok=True,
            status=manifest.status,
            message="initialized evidence manifest",
            manifest_path=repo_relative(saved),
            next_steps=["Run `python -m starbridge_mcp.server evidence --validate --json` to validate the manifest."],
        )
        payload = {"ok": True, "action": "evidence_init", "result": result.to_dict(), "manifest": manifest.to_dict()}
        _print_json(payload)
        return

    payload = load_manifest(manifest_path)
    if args.add_file or args.add_screenshot:
        evidence_path = ensure_evidence_path(args.path or args.manifest_path)
        collection = "output_files" if args.add_file else "screenshots"
        payload.setdefault(collection, []).append(
            {
                "kind": "file" if args.add_file else "screenshot",
                "path": repo_relative(evidence_path),
                "label": args.label,
                "details": {},
            }
        )
        payload.setdefault("redacted_paths", []).append(repo_relative(evidence_path))
        payload["updated_at"] = payload.get("updated_at")
        target = ensure_evidence_path(args.manifest_path)
        target.write_text(json.dumps(sanitize(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _print_json({"ok": True, "action": "evidence_add", "manifest": _manifest_summary(payload, target)})
        return

    validation = manifest_validation_result(payload)
    payload.setdefault("validation", []).append(validation.to_dict())
    save_path = ensure_evidence_path(args.manifest_path)
    save_path.write_text(json.dumps(sanitize(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _print_json(
        {
            "ok": validation.ok,
            "action": "evidence_validate",
            "manifest": _manifest_summary(payload, save_path),
            "validation": validation.to_dict(),
        }
    )


def _handle_job_status_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Return a unified StarBridge job status summary.")
    parser.add_argument("--manifest-path", default=str(_default_manifest_path().relative_to(REPO_ROOT)))
    parser.add_argument("--job-id")
    parser.add_argument("--message", default="evidence manifest available")
    parser.add_argument("--progress", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = load_manifest(args.manifest_path)
    progress = args.progress
    if progress is None:
        progress = 100 if payload.get("status") == "completed" else 0
    job = JobStatus(
        job_id=args.job_id or str(payload.get("job_id") or payload.get("manifest_id")),
        bridge=str(payload.get("bridge") or "starbridge"),
        action=str(payload.get("action") or "job_status"),
        status=str(payload.get("status") or "queued"),
        progress=progress,
        message=args.message,
        evidence_manifest=_manifest_summary(payload, ensure_evidence_path(args.manifest_path)),
        next_steps=["Review validation results before connecting the manifest to a real bridge execution loop."],
    )
    _print_json({"ok": True, "action": "job_status", "job_status": job.to_dict()})


def _load_action_plan(path: str) -> ActionPlan:
    return ActionPlan.load(Path(path))


def _handle_plan_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Normalize a StarBridge action plan and evaluate safety.")
    parser.add_argument("plan_path")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--allow-computer-use", action="store_true")
    args = parser.parse_args(argv)
    plan = _load_action_plan(args.plan_path)
    _print_json(render_plan_summary(plan, confirm_write=args.confirm_write, allow_computer_use=args.allow_computer_use))


def _handle_gui_instructions_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Generate Codex Windows Computer Use instructions for an action plan.")
    parser.add_argument("plan_path")
    args = parser.parse_args(argv)
    plan = _load_action_plan(args.plan_path)
    adapter = CodexComputerUseAdapter()
    _print_json({"ok": True, "plan_id": plan.id, "app": plan.app, "gui_instructions": adapter.generate_codex_gui_instructions(plan)})


def _handle_gui_record_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Record a real GUI execution result.")
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--plan-path")
    parser.add_argument("--ok", required=True)
    parser.add_argument("--screenshot", action="append", default=[])
    parser.add_argument("--created-file", action="append", default=[])
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    plan = _load_action_plan(args.plan_path) if args.plan_path else ActionPlan(id=args.plan_id, app="generic", action="gui_record", goal="Record GUI result")
    ok = str(args.ok).lower() in {"1", "true", "yes", "y"}
    result = CodexComputerUseAdapter().record_gui_result(
        plan,
        ok=ok,
        screenshot_paths=args.screenshot,
        created_files=args.created_file,
        notes=args.notes,
    )
    saved = LocalScreenshotEvidenceStore().save_result(args.plan_id, result)
    _print_json({"ok": True, "result": result.to_dict(), "saved_log": saved.relative_to(REPO_ROOT).as_posix()})


def _write_structured_fallback(plan: ActionPlan, *, confirm_write: bool) -> list[str]:
    if not confirm_write or plan.structured_method not in {"svg", "filesystem"}:
        return []
    created: list[str] = []
    for output_path in plan.output_paths:
        if not output_path.endswith(".svg"):
            continue
        target = REPO_ROOT / output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"450\" viewBox=\"0 0 800 450\">\n"
            "  <rect width=\"800\" height=\"450\" fill=\"#f8fafc\"/>\n"
            "  <text x=\"60\" y=\"120\" font-family=\"Arial\" font-size=\"42\" fill=\"#111827\">StarBridge structured fallback</text>\n"
            "  <circle cx=\"180\" cy=\"270\" r=\"70\" fill=\"#2563eb\"/>\n"
            "  <rect x=\"330\" y=\"210\" width=\"160\" height=\"120\" fill=\"#10b981\"/>\n"
            "</svg>\n",
            encoding="utf-8",
        )
        created.append(output_path)
    return created


def _handle_run_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Run a structured StarBridge action plan.")
    parser.add_argument("plan_path")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args(argv)
    plan = _load_action_plan(args.plan_path)
    decision = evaluate_safety(plan, confirm_write=args.confirm_write, allow_computer_use=plan.allow_computer_use)
    created = []
    if decision.allowed and plan.execution_mode == "structured_tool":
        created = _write_structured_fallback(plan, confirm_write=args.confirm_write and not plan.dry_run)
    _print_json(
        {
            "ok": decision.allowed,
            "plan_id": plan.id,
            "app": plan.app,
            "action": plan.action,
            "dry_run": plan.dry_run or not args.confirm_write,
            "safety_decision": decision.to_dict(),
            "created_files": created,
            "message": "structured plan evaluated; no desktop software was launched",
        }
    )


def _handle_demo_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Generate StarBridge GUI demo plans.")
    parser.add_argument("app", choices=["photoshop", "illustrator", "capcut"])
    parser.add_argument("--mode", default="gui", choices=["gui"])
    parser.add_argument("--allow-computer-use", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args(argv)
    _print_json(run_demo(args.app, mode=args.mode, allow_computer_use=args.allow_computer_use, confirm_write=args.confirm_write))


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"plan", "run", "gui-instructions", "gui-record", "demo", "evidence", "job-status"}:
        command = sys.argv[1]
        argv = sys.argv[2:]
        if command == "plan":
            _handle_plan_cli(argv)
        elif command == "run":
            _handle_run_cli(argv)
        elif command == "gui-instructions":
            _handle_gui_instructions_cli(argv)
        elif command == "gui-record":
            _handle_gui_record_cli(argv)
        elif command == "demo":
            _handle_demo_cli(argv)
        elif command == "evidence":
            _handle_evidence_cli(argv)
        elif command == "job-status":
            _handle_job_status_cli(argv)
        return

    parser = argparse.ArgumentParser(description="StarBridge 本地创意软件 MCP 桥接框架最小状态入口。")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "tools", "roots"], help="当前实现 status、tools 和 roots。")
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
