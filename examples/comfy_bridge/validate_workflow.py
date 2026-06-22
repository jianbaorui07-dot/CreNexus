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
    if payload and all(
        isinstance(node, dict) and "class_type" in node for node in payload.values()
    ):
        return "api"
    if payload and all(isinstance(node, dict) for node in payload.values()):
        if any("class_type" in node or "inputs" in node for node in payload.values()):
            return "api"
    return "unknown"


MODEL_INPUT_KEYS = {
    "ckpt_name",
    "checkpoint",
    "model_name",
    "lora_name",
    "vae_name",
    "control_net_name",
    "unet_name",
}
KNOWN_DRAFT_METADATA_CLASSES = {"StarBridgeDraftMetadata"}


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )


def _empty_report(
    *,
    workflow_name: str,
    workflow_format: str,
    errors: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "workflow": workflow_name,
        "format": workflow_format,
        "valid": False,
        "errors": errors,
        "warnings": warnings or [],
        "node_count": 0,
        "link_count": 0,
        "class_types": {},
        "detected_models": [],
        "missing_or_suspicious_fields": [],
        "prompt_text_nodes": [],
        "output_nodes": [],
    }


def _append_model_value(
    detected_models: list[dict[str, str]], *, node_id: str, input_name: str, value: Any
) -> None:
    if isinstance(value, str) and value.strip():
        detected_models.append({"node_id": node_id, "input": input_name, "value": value.strip()})


def _missing_or_suspicious_node_fields(node_id: str, node: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if "inputs" not in node:
        findings.append(f"节点 {node_id} 缺少 inputs。")
    elif node.get("inputs") is None:
        findings.append(f"节点 {node_id}.inputs 为空。")
    elif not isinstance(node.get("inputs"), dict):
        findings.append(f"节点 {node_id}.inputs 必须是 JSON object。")
    for reserved in ("_meta", "widgets_values"):
        if reserved in node and not isinstance(node.get(reserved), (dict, list)):
            findings.append(f"节点 {node_id}.{reserved} 类型可疑。")
    return findings


def validate_api_workflow(payload: dict[str, Any], *, workflow_name: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    class_types: Counter[str] = Counter()
    link_count = 0
    detected_models: list[dict[str, str]] = []
    missing_or_suspicious_fields: list[str] = []

    for node_id, node in payload.items():
        node_label = str(node_id)
        if not str(node_id).strip():
            errors.append("节点 id 不能为空。")
            continue
        if not str(node_id).isdigit():
            warnings.append(f"节点 {node_label} id 不是常见数字字符串。")
        if not isinstance(node, dict):
            errors.append(f"节点 {node_label} 必须是 JSON object。")
            continue
        missing_or_suspicious_fields.extend(_missing_or_suspicious_node_fields(node_label, node))
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type:
            errors.append(f"节点 {node_label} 缺少 class_type。")
            missing_or_suspicious_fields.append(f"节点 {node_label}.class_type 缺失或为空。")
        else:
            class_types[class_type] += 1

        inputs = node.get("inputs", {})
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            errors.append(f"节点 {node_label} 的 inputs 必须是 JSON object。")
            continue
        for input_name, input_value in inputs.items():
            if input_name in MODEL_INPUT_KEYS:
                _append_model_value(
                    detected_models,
                    node_id=node_label,
                    input_name=str(input_name),
                    value=input_value,
                )
            if _is_link(input_value):
                link_count += 1
                if input_value[0] not in payload:
                    errors.append(
                        f"节点 {node_label}.{input_name} 引用了不存在的节点 {input_value[0]}。"
                    )
            elif isinstance(input_value, list) and input_value:
                missing_or_suspicious_fields.append(
                    f"节点 {node_label}.{input_name} 是列表但不是标准 ComfyUI link。"
                )

    prompt_text_nodes = []
    output_nodes = []
    for node_id, node in payload.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        if node.get("class_type") == "CLIPTextEncode":
            text_value = inputs.get("text")
            if isinstance(text_value, str) and text_value.strip():
                prompt_text_nodes.append(str(node_id))
        if node.get("class_type") == "SaveImage" and isinstance(inputs.get("images"), list):
            output_nodes.append(str(node_id))

    if not prompt_text_nodes:
        warnings.append(
            "workflow 未包含带 text prompt 的 CLIPTextEncode 节点；仅适合非 prompt 类草案或后续人工补齐。"
        )
    if not output_nodes:
        errors.append("workflow 必须包含至少一个带 images 输入的 SaveImage 输出节点。")
    if class_types and not any(
        class_type not in KNOWN_DRAFT_METADATA_CLASSES for class_type in class_types
    ):
        errors.append("workflow 必须包含至少一个非 metadata 的 ComfyUI 节点。")

    details = {
        "workflow": workflow_name,
        "format": "api",
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(payload),
        "link_count": link_count,
        "class_types": dict(sorted(class_types.items())),
        "detected_models": detected_models,
        "missing_or_suspicious_fields": missing_or_suspicious_fields,
        "prompt_text_nodes": prompt_text_nodes,
        "output_nodes": output_nodes,
    }
    return _result(
        ok=not errors,
        message="ComfyUI API workflow 校验通过。"
        if not errors
        else "ComfyUI API workflow 校验失败。",
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
                **_empty_report(
                    workflow_name=workflow_name,
                    workflow_format="visual",
                    errors=["需要从 ComfyUI 导出 API format workflow 后再提交。"],
                    warnings=["visual workflow 适合人工打开检查，不适合直接提交到 /prompt。"],
                ),
                "node_count": node_count,
                "link_count": link_count,
            },
            warnings=["visual workflow 适合人工打开检查，不适合直接提交到 /prompt。"],
            next_steps=["在 ComfyUI 中使用 Save (API Format) 或导出 API workflow。"],
        )
    return _result(
        ok=False,
        message="无法识别 ComfyUI workflow 格式。",
        details=_empty_report(
            workflow_name=workflow_name,
            workflow_format=workflow_format,
            errors=["workflow 根节点必须是 API object，或可识别的 visual workflow。"],
        ),
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
            details=_empty_report(
                workflow_name=path.name,
                workflow_format="missing",
                errors=["找不到 workflow 文件。"],
            ),
            next_steps=[
                "传入 examples/comfy_bridge/workflows 下的公开 workflow，或用户明确提供的 API workflow。"
            ],
        )
    except json.JSONDecodeError as exc:
        return _result(
            ok=False,
            message="workflow JSON 解析失败。",
            details=_empty_report(
                workflow_name=path.name, workflow_format="invalid_json", errors=[str(exc)]
            ),
            next_steps=["先修复 JSON 语法。"],
        )
    return validate_workflow_payload(payload, workflow_name=path.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a ComfyUI workflow without submitting a generation job."
    )
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--json", action="store_true", help="保留给兼容；当前始终输出 JSON。")
    args = parser.parse_args(argv)

    result = validate_workflow_file(args.workflow)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
