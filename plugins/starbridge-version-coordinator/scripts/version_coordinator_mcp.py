from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "starbridge-version-coordinator", "version": "0.1.0"}
PLAN_SCHEMA_VERSION = "starbridge.version-plan.v1"

GENERATION_ORDER = ("v5", "v6", "v7", "v8", "v9")
GENERATION_CATALOG: dict[str, dict[str, Any]] = {
    "v5": {
        "name": "semantic",
        "label": "几何语义分层",
        "capabilities": ["几何意图分类", "稳定 intent 选择器", "紧凑编辑索引"],
    },
    "v6": {
        "name": "refinement",
        "label": "可审计局部精修",
        "capabilities": ["客户意图预校准", "schema-v2 编辑索引", "patch/edit 引用链"],
    },
    "v7": {
        "name": "paint",
        "label": "颜色与块面优化",
        "capabilities": ["非重叠叶子块面合并", "近似色压缩", "基础色保护"],
    },
    "v8": {
        "name": "direction",
        "label": "人工配色与设计命名",
        "capabilities": ["显式颜色组", "设计对象命名", "Illustrator 映射引用"],
    },
    "v9": {
        "name": "illustrator",
        "label": "确认式 Illustrator 事务",
        "capabilities": ["state revision 门", "回读/提交/回滚", "双确认写入协议"],
    },
}

SOFTWARE_CATALOG: dict[str, dict[str, Any]] = {
    "photoshop": {
        "label": "Adobe Photoshop",
        "aliases": ("ps", "adobe-photoshop"),
        "manifest_min_version": "25.0.0",
        "gate_source": "uxp/photoshop-bridge/manifest.json",
        "preferred_route": "uxp-node-proxy",
        "fallback_route": "com-readonly-or-headless",
        "probe_tool": "photoshop.session_info",
        "env_vars": ("PHOTOSHOP_EXE",),
        "full_mcp_tools": ("photoshop.session_info", "photoshop.recipe_plan"),
        "default_route": "version-probe-first",
    },
    "illustrator": {
        "label": "Adobe Illustrator",
        "aliases": ("ai", "adobe-illustrator"),
        "manifest_min_version": "30.0.0",
        "gate_source": "uxp/illustrator-bridge/manifest.json",
        "preferred_route": "uxp-node-proxy-v2",
        "fallback_route": "headless-svg-or-com-readonly",
        "probe_tool": "illustrator.document_info",
        "env_vars": ("ILLUSTRATOR_EXE",),
        "full_mcp_tools": ("illustrator.document_info", "illustrator.preflight"),
        "default_route": "version-probe-first",
    },
    "autocad": {
        "label": "AutoCAD / CAD",
        "aliases": ("cad", "cad-autocad", "cad_autocad"),
        "manifest_min_version": None,
        "gate_source": None,
        "preferred_route": "headless-dxf-with-optional-com",
        "fallback_route": "headless-dxf",
        "probe_tool": "cad_autocad.environment_probe",
        "env_vars": ("AUTOCAD_EXE",),
        "full_mcp_tools": (
            "cad_autocad.environment_probe",
            "autocad_dxf.validate_cad_plan",
            "autocad_dxf.write_dxf",
        ),
        "default_route": "headless-dxf",
    },
    "blender": {
        "label": "Blender",
        "aliases": ("bpy",),
        "manifest_min_version": None,
        "gate_source": None,
        "preferred_route": "plan-only-with-cli-probe",
        "fallback_route": "plan-only",
        "probe_tool": "blender.environment_probe",
        "env_vars": ("BLENDER_EXE", "BLENDER_MCP_DIR"),
        "full_mcp_tools": ("blender.environment_probe", "blender.scene_plan"),
        "default_route": "plan-only-with-cli-probe",
    },
    "comfyui": {
        "label": "ComfyUI",
        "aliases": ("comfy",),
        "manifest_min_version": None,
        "gate_source": None,
        "preferred_route": "loopback-api",
        "fallback_route": "workflow-validate-only",
        "probe_tool": "comfyui.system_probe",
        "env_vars": ("STARBRIDGE_COMFYUI_URL", "COMFY_ROOT"),
        "full_mcp_tools": ("comfyui.system_probe", "comfyui.workflow_validate"),
        "default_route": "loopback-api-probe-first",
    },
    "capcut_jianying": {
        "label": "CapCut / 剪映",
        "aliases": ("capcut", "jianying", "jianying-capcut"),
        "manifest_min_version": None,
        "gate_source": None,
        "preferred_route": "draft-probe-and-summary",
        "fallback_route": "manual-open-and-export",
        "probe_tool": "jianying_capcut.draft_probe",
        "env_vars": (
            "JIANYING_EXE",
            "JIANYING_DRAFTS_DIR",
            "CAPCUT_EXE",
            "CAPCUT_DRAFTS_DIR",
        ),
        "full_mcp_tools": (
            "jianying_capcut.draft_probe",
            "jianying_capcut.draft_structure",
        ),
        "default_route": "draft-probe-first",
    },
}

VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][0-9A-Za-z.-]+)?$")


class CoordinatorError(ValueError):
    pass


def configure_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for software_id, entry in SOFTWARE_CATALOG.items():
        aliases[software_id] = software_id
        for alias in entry["aliases"]:
            aliases[str(alias)] = software_id
    return aliases


ALIASES = _alias_map()


def normalize_software_id(value: Any) -> str:
    candidate = str(value or "").strip().lower().replace("_", "-")
    normalized = ALIASES.get(candidate)
    if normalized is None:
        supported = ", ".join(SOFTWARE_CATALOG)
        raise CoordinatorError(f"unsupported software '{candidate}'; supported: {supported}")
    return normalized


def normalize_generation(value: Any, *, field: str = "generation") -> str:
    candidate = str(value or "v9").strip().lower()
    if candidate.isdigit():
        candidate = f"v{candidate}"
    if candidate not in GENERATION_CATALOG:
        raise CoordinatorError(f"{field} must be one of: {', '.join(GENERATION_ORDER)}")
    return candidate


def normalize_version(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate or candidate.lower() in {"unknown", "auto", "none", "null"}:
        return None
    if len(candidate) > 40 or not VERSION_PATTERN.fullmatch(candidate):
        raise CoordinatorError(
            "software versions must be short numeric versions such as 25, 25.4, or 30.0.1"
        )
    return candidate


def version_tuple(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    numeric = value.split("-", 1)[0].split("+", 1)[0]
    parts = [int(part) for part in numeric.split(".")]
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def _cumulative_capabilities(generation: str) -> list[dict[str, Any]]:
    limit = GENERATION_ORDER.index(generation)
    return [
        {
            "generation": item,
            "name": GENERATION_CATALOG[item]["name"],
            "label": GENERATION_CATALOG[item]["label"],
            "capabilities": list(GENERATION_CATALOG[item]["capabilities"]),
        }
        for item in GENERATION_ORDER[: limit + 1]
    ]


def build_migration(source_generation: Any, target_generation: Any = "v9") -> dict[str, Any]:
    source = normalize_generation(source_generation, field="source_generation")
    target = normalize_generation(target_generation, field="target_generation")
    source_index = GENERATION_ORDER.index(source)
    target_index = GENERATION_ORDER.index(target)
    if source_index > target_index:
        raise CoordinatorError("downgrades are not generated; choose the same or a newer target")

    steps = []
    for generation in GENERATION_ORDER[source_index + 1 : target_index + 1]:
        entry = GENERATION_CATALOG[generation]
        steps.append(
            {
                "to": generation,
                "profile": entry["name"],
                "add": list(entry["capabilities"]),
                "preserve_previous_outputs": True,
                "requires_customer_asset_reupload": False,
            }
        )
    return {
        "ok": True,
        "schema_version": PLAN_SCHEMA_VERSION,
        "action": "migrate",
        "source_generation": source,
        "target_generation": target,
        "already_current": source == target,
        "steps": steps,
        "rules": [
            "迁移只增加能力，不改写旧产物。",
            "旧 edit_ref/patch_ref/direction_ref 保留；需要升级时生成新引用。",
            "迁移计划不读取图片、PSD、AI、DWG、blend 或剪映草稿。",
        ],
    }


def _resolve_route(software_id: str, version: str | None) -> tuple[str, str, list[str]]:
    entry = SOFTWARE_CATALOG[software_id]
    gate = normalize_version(entry["manifest_min_version"])
    notes: list[str] = []

    # A host application's version is not a license check or a compatibility
    # whitelist.  Older and vendor-suffixed builds must still reach the same
    # read-only capability probe; the probe decides whether UXP, a proxy, or a
    # headless route is actually available.  Keep ``manifest_min_version`` as advisory
    # metadata because it documents the manifest's preferred minimum.
    if gate is not None:
        if version is None:
            notes.append(
                f"版本未知；先做只读能力探针。manifest minVersion {gate} 仅供参考，不是阻断条件。"
            )
        else:
            notes.append(
                f"已记录版本 {version}；manifest minVersion {gate} 仅供参考，兼容性由本机能力探针决定。"
            )
        return entry["preferred_route"], "probe_required", notes

    if version is None:
        notes.append("该桥没有硬编码软件版本门；仍需先运行只读环境探针。")
        return entry["default_route"], "needs_environment_probe", notes
    notes.append("记录版本仅用于配置协同；真实兼容性由本机只读探针和能力测试确认。")
    return entry["preferred_route"], "probe_required", notes


def _normalize_versions(value: Any) -> dict[str, str | None]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CoordinatorError("software_versions must be an object keyed by software id")
    normalized: dict[str, str | None] = {}
    for raw_id, raw_version in value.items():
        software_id = normalize_software_id(raw_id)
        if software_id in normalized:
            raise CoordinatorError(
                f"duplicate software entry after alias normalization: {software_id}"
            )
        normalized[software_id] = normalize_version(raw_version)
    return normalized


def _normalize_requested(value: Any, versions: dict[str, str | None]) -> list[str]:
    if value is None:
        return list(versions) if versions else list(SOFTWARE_CATALOG)
    if not isinstance(value, list) or not value:
        raise CoordinatorError("requested_software must be a non-empty array")
    result: list[str] = []
    for item in value:
        software_id = normalize_software_id(item)
        if software_id not in result:
            result.append(software_id)
    return result


def build_plan(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    generation = normalize_generation(args.get("starbridge_generation", "v9"))
    safety_mode = str(args.get("safety_mode", "safe")).strip().lower()
    if safety_mode not in {"safe", "balanced", "production"}:
        raise CoordinatorError("safety_mode must be safe, balanced, or production")
    versions = _normalize_versions(args.get("software_versions"))
    requested = _normalize_requested(args.get("requested_software"), versions)

    software_plans = []
    for software_id in requested:
        entry = SOFTWARE_CATALOG[software_id]
        version = versions.get(software_id)
        route, eligibility, notes = _resolve_route(software_id, version)
        software_plans.append(
            {
                "id": software_id,
                "label": entry["label"],
                "version": version or "unknown",
                "route": route,
                "eligibility": eligibility,
                "probe_tool": entry["probe_tool"],
                "configuration": {
                    "env_vars": list(entry["env_vars"]),
                    "full_mcp_tools": list(entry["full_mcp_tools"]),
                },
                "notes": notes,
                "compatibility_policy": "capability-probe-not-version-whitelist",
            }
        )

    generation_migration = build_migration(generation, "v9")
    version_summary = ", ".join(f"{item['id']}={item['version']}" for item in software_plans)
    write_policy = {
        "safe": "coordinator_read_only_and_full_mcp_dry_run",
        "balanced": "full_mcp_confirmed_sandbox_writes_only",
        "production": "reviewed_full_mcp_tools_with_explicit_confirmation",
    }[safety_mode]
    return {
        "ok": True,
        "schema_version": PLAN_SCHEMA_VERSION,
        "action": "plan",
        "target": "codex",
        "safety_mode": safety_mode,
        "write_policy": write_policy,
        "starbridge_generation": generation,
        "generation_profiles": _cumulative_capabilities(generation),
        "migration_to_v9": generation_migration,
        "software": software_plans,
        "customer_workflow": {
            "policy": "exact-pixel-first-then-drawn-vector",
            "image_trace_allowed": False,
            "stages": [
                {
                    "order": 1,
                    "id": "pixel-level-print",
                    "label": "像素级打印 / 精确重建",
                    "implementation": "exact_pixel_vector.py",
                    "gate": "verified raster-free SVG baseline",
                },
                {
                    "order": 2,
                    "id": "drawn-vector",
                    "label": "绘制型矢量",
                    "implementation": "artisan or customer-selected smart/lightweight",
                    "requires": "verified stage-1 baseline",
                },
            ],
            "stop_rule": (
                "If exact reconstruction exceeds a safety limit, stop and ask the customer "
                "to reduce dimensions or change the delivery goal; never fall back to Image Trace."
            ),
        },
        "codex": {
            "coordinator_mcp_server": "starbridge-version-coordinator",
            "coordinator_tools": [
                "starbridge_config.catalog",
                "starbridge_config.plan",
                "starbridge_config.migrate",
            ],
            "full_starbridge_mcp": {
                "command": "python",
                "args": ["-m", "starbridge_mcp.mcp_server"],
                "env": {
                    "STARBRIDGE_PHOTOSHOP_SAFE_ONLY": "1",
                    "STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN": "1",
                    "STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE": "0",
                },
            },
            "starter_prompt": (
                f"请用 StarBridge Version Coordinator 按 {generation} 和 {version_summary} "
                f"生成 {safety_mode} 配置；先探针，未确认不写入。"
            ),
            "compatibility_policy": "capability-probe-not-version-whitelist",
        },
        "next_steps": [
            "客户任务先完成像素级打印/精确重建，再进入绘制型矢量。",
            "先执行每个软件计划中的 probe_tool。",
            "探针通过后，再把对应 full_mcp_tools 交给完整 StarBridge MCP。",
            "涉及桌面写入时重新请求用户确认，并限制在 sandbox/output。",
        ],
        "safety": {
            "reads_private_assets": False,
            "scans_install_directories": False,
            "starts_desktop_software": False,
            "writes_configuration": False,
            "contains_absolute_paths": False,
            "uses_image_trace": False,
        },
    }


def build_catalog() -> dict[str, Any]:
    software = []
    for software_id, entry in SOFTWARE_CATALOG.items():
        software.append(
            {
                "id": software_id,
                "label": entry["label"],
                "aliases": list(entry["aliases"]),
                "manifest_min_version": entry["manifest_min_version"],
                "gate_source": entry["gate_source"],
                "probe_tool": entry["probe_tool"],
                "default_route": entry["default_route"],
            }
        )
    return {
        "ok": True,
        "schema_version": PLAN_SCHEMA_VERSION,
        "action": "catalog",
        "software": software,
        "starbridge_generations": _cumulative_capabilities("v9"),
        "safety_modes": ["safe", "balanced", "production"],
        "customer_default_policy": "exact-pixel-first-then-drawn-vector-no-image-trace",
        "compatibility_policy": "capability-probe-not-version-whitelist",
    }


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
OUTPUT_SCHEMA = {"type": "object", "additionalProperties": True}
TOOLS = [
    {
        "name": "starbridge_config.catalog",
        "title": "StarBridge Version Catalog",
        "description": "列出可协同的软件、能力探针和 StarBridge v5-v9 能力档位；只读。",
        "inputSchema": _object_schema({}),
        "outputSchema": OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "starbridge_config.plan",
        "title": "Plan StarBridge Configuration",
        "description": "根据软件版本、StarBridge 代际和安全模式生成 Codex 配置协同计划；不探测路径、不写配置。",
        "inputSchema": _object_schema(
            {
                "software_versions": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "null"]},
                    "description": '例如 {"photoshop":"25.5","illustrator":"30.0"}。',
                },
                "requested_software": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "starbridge_generation": {
                    "type": "string",
                    "enum": list(GENERATION_ORDER),
                    "default": "v9",
                },
                "safety_mode": {
                    "type": "string",
                    "enum": ["safe", "balanced", "production"],
                    "default": "safe",
                },
            }
        ),
        "outputSchema": OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "starbridge_config.migrate",
        "title": "Migrate StarBridge Generation",
        "description": "生成 v5-v9 之间的增量迁移计划，保留旧引用与产物；只读。",
        "inputSchema": _object_schema(
            {
                "source_generation": {"type": "string", "enum": list(GENERATION_ORDER)},
                "target_generation": {
                    "type": "string",
                    "enum": list(GENERATION_ORDER),
                    "default": "v9",
                },
            },
            required=["source_generation"],
        ),
        "outputSchema": OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
]


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "structuredContent": payload,
        "isError": is_error,
    }


def call_tool(name: str, arguments: Any) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "starbridge_config.catalog":
            return _tool_result(build_catalog())
        if name == "starbridge_config.plan":
            return _tool_result(build_plan(args))
        if name == "starbridge_config.migrate":
            return _tool_result(
                build_migration(args.get("source_generation"), args.get("target_generation", "v9"))
            )
        raise CoordinatorError(f"unknown tool: {name}")
    except CoordinatorError as exc:
        return _tool_result(
            {
                "ok": False,
                "schema_version": PLAN_SCHEMA_VERSION,
                "action": "error",
                "error": str(exc),
            },
            is_error=True,
        )


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    request_id = request.get("id")
    if method == "initialize":
        requested = request.get("params", {}).get("protocolVersion")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "先用 starbridge_config.plan 按软件版本选择安全桥接路由。"
                    "版本未知时先探针；本协调器永不读取客户素材、扫描安装目录、启动桌面软件或写配置。"
                    "真实动作转交完整 StarBridge MCP，默认 dry-run，写入必须显式确认。"
                ),
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params") or {}
        result = call_tool(str(params.get("name") or ""), params.get("arguments") or {})
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def serve_stdio(lines: Iterable[str] = sys.stdin) -> int:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = handle_request(request)
        except (json.JSONDecodeError, ValueError) as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def _parse_software_args(values: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for value in values:
        software_id, separator, version = value.partition("=")
        if not separator:
            version = "unknown"
        result[normalize_software_id(software_id)] = normalize_version(version)
    return result


def cli(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="StarBridge Codex 版本配置协同器")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("catalog", help="列出支持的软件和项目代际")
    plan_parser = subparsers.add_parser("plan", help="生成只读配置计划")
    plan_parser.add_argument("--software", action="append", default=[], metavar="ID=VERSION")
    plan_parser.add_argument("--generation", choices=GENERATION_ORDER, default="v9")
    plan_parser.add_argument(
        "--safety-mode", choices=("safe", "balanced", "production"), default="safe"
    )
    migrate_parser = subparsers.add_parser("migrate", help="生成 v5-v9 增量迁移计划")
    migrate_parser.add_argument("--from", dest="source", choices=GENERATION_ORDER, required=True)
    migrate_parser.add_argument("--to", dest="target", choices=GENERATION_ORDER, default="v9")
    subparsers.add_parser("self-test", help="运行无桌面依赖的自检")
    args = parser.parse_args(argv)

    if args.command == "catalog":
        payload = build_catalog()
    elif args.command == "plan":
        versions = _parse_software_args(args.software)
        payload = build_plan(
            {
                "software_versions": versions,
                "starbridge_generation": args.generation,
                "safety_mode": args.safety_mode,
            }
        )
    elif args.command == "migrate":
        payload = build_migration(args.source, args.target)
    elif args.command == "self-test":
        sample = build_plan(
            {
                "software_versions": {"photoshop": "25.0", "illustrator": "30.0"},
                "starbridge_generation": "v8",
            }
        )
        payload = {
            "ok": sample["ok"] and len(TOOLS) == 3,
            "server": SERVER_INFO,
            "tools": [tool["name"] for tool in TOOLS],
            "sample_routes": {item["id"]: item["route"] for item in sample["software"]},
        }
    else:
        return serve_stdio()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
