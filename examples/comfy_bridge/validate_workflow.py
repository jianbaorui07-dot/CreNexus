from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.security import sanitize_result


BRIDGE_ID = "comfyui"
BRIDGE_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKFLOW = BRIDGE_ROOT / "workflows" / "txt2img_basic_api.json"


def _result(
    *,
    ok: bool,
    message: str,
    details: dict[str, Any],
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    result = make_result(
        ok=ok,
        bridge=BRIDGE_ID,
        action="workflow_validate",
        message=message,
        details=details,
        warnings=warnings or [],
        next_steps=next_steps or [],
    )
    sanitized = sanitize_result(result)
    validate_result(sanitized)
    return sanitized


def detect_workflow_format(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "invalid"
    if isinstance(payload.get("nodes"), list) and isinstance(payload.get("links"), list):
        return "visual"
    if payload and all(isinstance(node, dict) and "class_type" in node for node in payload.values()):
        return "api"
    return "unknown"


def validate_api_workflow(payload: dict[str, Any], *, workflow_name: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    class_types: Counter[str] = Counter()
    link_count = 0

    for node_id, node in payload.items():
        node_label = str(node_id)
        if not isinstance(node, dict):
            errors.append(f"节点 {node_label} 必须是 JSON object。")
            continue
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type:
            errors.append(f"节点 {node_label} 缺少 class_type。")
        else:
            class_types[class_type] += 1

        inputs = node.get("inputs", {})
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            errors.append(f"节点 {node_label} 的 inputs 必须是 JSON object。")
            continue
        for input_name, input_value in inputs.items():
            if (
                isinstance(input_value, list)
                and len(input_value) == 2
                and isinstance(input_value[0], str)
                and isinstance(input_value[1], int)
            ):
                link_count += 1
                if input_value[0] not in payload:
                    errors.append(f"节点 {node_label}.{input_name} 引用了不存在的节点 {input_value[0]}。")

    required_classes = {"KSampler", "CheckpointLoaderSimple", "SaveImage"}
    missing_required = sorted(required_classes - set(class_types))
    if missing_required:
        warnings.append("未发现基础文生图常用节点：" + ", ".join(missing_required))

    details = {
        "workflow": workflow_name,
        "format": "api",
        "node_count": len(payload),
        "link_count": link_count,
        "class_types": dict(sorted(class_types.items())),
        "errors": errors,
    }
    return _result(
        ok=not errors,
        message="ComfyUI API workflow 校验通过。" if not errors else "ComfyUI API workflow 校验失败。",
        details=details,
        warnings=warnings,
        next_steps=[] if not errors else ["修复 errors 后再提交到 ComfyUI /prompt。"],
    )


def validate_workflow_payload(payload: Any, *, workflow_name: str) -> dict[str, Any]:
    workflow_format = detect_workflow_format(payload)
    if workflow_format == "api":
        return validate_api_workflow(payload, workflow_name=workflow_name)
    if workflow_format == "visual":
        node_count = len(payload.get("nodes", [])) if isinstance(payload, dict) else 0
        link_count = len(payload.get("links", [])) if isinstance(payload, dict) else 0
        return _result(
            ok=False,
            message="检测到 ComfyUI 可视化 workflow，不是 /prompt API format。",
            details={
                "workflow": workflow_name,
                "format": "visual",
                "node_count": node_count,
                "link_count": link_count,
                "errors": ["需要从 ComfyUI 导出 API format workflow 后再提交。"],
            },
            warnings=["visual workflow 适合人工打开检查，不适合直接提交到 /prompt。"],
            next_steps=["在 ComfyUI 中使用 Save (API Format) 或导出 API workflow。"],
        )
    return _result(
        ok=False,
        message="无法识别 ComfyUI workflow 格式。",
        details={
            "workflow": workflow_name,
            "format": workflow_format,
            "node_count": 0,
            "link_count": 0,
            "errors": ["workflow 根节点必须是 API object，或可识别的 visual workflow。"],
        },
        warnings=[],
        next_steps=["确认 JSON 文件来自 ComfyUI workflow 导出。"],
    )


def validate_workflow_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _result(
            ok=False,
            message="workflow 文件不存在。",
            details={"workflow": path.name, "format": "missing", "errors": ["找不到 workflow 文件。"]},
            next_steps=["传入 examples/comfy_bridge/workflows 下的公开 workflow，或用户明确提供的 API workflow。"],
        )
    except json.JSONDecodeError as exc:
        return _result(
            ok=False,
            message="workflow JSON 解析失败。",
            details={"workflow": path.name, "format": "invalid_json", "errors": [str(exc)]},
            next_steps=["先修复 JSON 语法。"],
        )
    return validate_workflow_payload(payload, workflow_name=path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a ComfyUI workflow without submitting a generation job.")
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--json", action="store_true", help="保留给兼容；当前始终输出 JSON。")
    args = parser.parse_args(argv)

    result = validate_workflow_file(args.workflow)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
