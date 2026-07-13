from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from examples.comfy_bridge.validate_workflow import validate_workflow_payload
from starbridge_mcp.core.security import sanitize

CATEGORY_ORDER = ("loaders", "conditioning", "sampling", "latent", "decode", "output", "other")
CATEGORY_LABELS = {
    "loaders": "加载",
    "conditioning": "条件",
    "sampling": "采样",
    "latent": "潜空间",
    "decode": "解码",
    "output": "输出",
    "other": "其他",
}


def _safe_label(value: Any, *, fallback: str = "Unknown") -> str:
    cleaned = re.sub(r"[^\w\- ]+", " ", str(value), flags=re.UNICODE)
    return " ".join(cleaned.split())[:80] or fallback


def _category(class_type: str) -> str:
    lowered = class_type.casefold()
    if any(word in lowered for word in ("loader", "loadimage", "checkpoint")):
        return "loaders"
    if any(word in lowered for word in ("cliptext", "conditioning", "prompt")):
        return "conditioning"
    if any(word in lowered for word in ("sampler", "scheduler", "guider", "noise")):
        return "sampling"
    if any(word in lowered for word in ("latent", "emptyimage")):
        return "latent"
    if any(word in lowered for word in ("decode", "vae")):
        return "decode"
    if any(word in lowered for word in ("save", "preview", "output")):
        return "output"
    return "other"


def _iter_links(value: Any, node_ids: set[str]) -> Iterable[tuple[str, int]]:
    if isinstance(value, list):
        if (
            len(value) == 2
            and str(value[0]) in node_ids
            and isinstance(value[1], int)
            and not isinstance(value[1], bool)
        ):
            yield str(value[0]), value[1]
            return
        for item in value:
            yield from _iter_links(item, node_ids)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_links(item, node_ids)


def visualize_workflow(
    workflow: dict[str, Any], *, direction: str = "LR", include_node_ids: bool = True
) -> dict[str, Any]:
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be an object")
    if direction not in {"LR", "TD"}:
        raise ValueError("direction must be LR or TD")

    validation = validate_workflow_payload(workflow, workflow_name="inline-workflow")
    node_items = [
        (str(node_id), node)
        for node_id, node in workflow.items()
        if isinstance(node, dict) and isinstance(node.get("class_type"), str)
    ]
    node_items.sort(key=lambda item: item[0])
    node_ids = {node_id for node_id, _node in node_items}
    mermaid_ids = {node_id: f"N{index}" for index, (node_id, _node) in enumerate(node_items)}

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    nodes: list[dict[str, str]] = []
    for node_id, node in node_items:
        class_type = _safe_label(node["class_type"])
        category = _category(class_type)
        label = f"{node_id} · {class_type}" if include_node_ids else class_type
        summary = {
            "node_id": node_id,
            "diagram_id": mermaid_ids[node_id],
            "class_type": class_type,
            "category": category,
            "label": label,
        }
        nodes.append(summary)
        groups[category].append(summary)

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, int]] = set()
    for target_id, node in node_items:
        for source_id, output_index in _iter_links(node.get("inputs", {}), node_ids):
            key = (source_id, target_id, output_index)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "output_index": output_index,
                }
            )
    edges.sort(key=lambda item: (item["source"], item["target"], item["output_index"]))

    lines = [f"flowchart {direction}"]
    for category in CATEGORY_ORDER:
        category_nodes = groups.get(category, [])
        if not category_nodes:
            continue
        lines.append(f'  subgraph {category}["{CATEGORY_LABELS[category]}"]')
        for node in category_nodes:
            lines.append(f'    {node["diagram_id"]}["{node["label"]}"]')
        lines.append("  end")
    for edge in edges:
        lines.append(
            f'  {mermaid_ids[edge["source"]]} -->|"out {edge["output_index"]}"| '
            f"{mermaid_ids[edge['target']]}"
        )

    details = validation.get("details", {})
    return sanitize(
        {
            "ok": bool(validation.get("ok")),
            "bridge": "comfyui",
            "action": "workflow_visualize",
            "dry_run": True,
            "diagram_format": "mermaid",
            "direction": direction,
            "mermaid": "\n".join(lines),
            "summary": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "categories": {
                    category: len(groups.get(category, [])) for category in CATEGORY_ORDER
                },
                "workflow_valid": bool(details.get("valid", False)),
                "validation_errors": details.get("errors", []),
            },
            "nodes": nodes,
            "edges": edges,
            "privacy": {
                "includes_input_values": False,
                "includes_prompts": False,
                "includes_model_names": False,
                "reads_files": False,
                "uses_network": False,
            },
            "next_steps": [
                "Review the graph and validation errors before any separate queue submission.",
                "Use comfy.workflow_compose or comfyui.workflow_repair for structural changes.",
            ],
        }
    )
