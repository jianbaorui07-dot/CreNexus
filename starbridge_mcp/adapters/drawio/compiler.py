from __future__ import annotations

import csv
import io
import re
from collections import defaultdict, deque
from typing import Any

from .model import DiagramCell, DiagramDocument, DiagramPage, from_drawio_xml, stable_id

NODE_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#F8FAFC;strokeColor=#334155;"
    "fontColor=#0F172A;fontSize=14;spacing=10;"
)
ACCENT_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#E0F2FE;strokeColor=#0369A1;"
    "fontColor=#0C4A6E;fontSize=14;spacing=10;"
)
SUMMARY_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor=#ECFDF5;strokeColor=#047857;"
    "fontColor=#064E3B;fontSize=13;spacing=10;"
)
CONTAINER_STYLE = (
    "swimlane;rounded=1;whiteSpace=wrap;html=1;horizontal=1;startSize=34;"
    "fillColor=#F1F5F9;swimlaneFillColor=#FFFFFF;strokeColor=#475569;"
    "fontColor=#0F172A;fontSize=14;spacing=10;"
)
EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
    "strokeColor=#475569;endArrow=block;endFill=1;"
)


def _node_key(raw: dict[str, Any], index: int) -> str:
    return str(raw.get("key") or raw.get("id") or f"node-{index + 1}")


def _rank_nodes(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    keys = [_node_key(node, index) for index, node in enumerate(nodes)]
    incoming: dict[str, int] = dict.fromkeys(keys, 0)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in incoming and target in incoming:
            incoming[target] += 1
            outgoing[source].append(target)
    queue = deque(key for key in keys if incoming[key] == 0)
    ranks = dict.fromkeys(keys, 0)
    visited = 0
    while queue:
        source = queue.popleft()
        visited += 1
        for target in outgoing[source]:
            ranks[target] = max(ranks[target], ranks[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if visited != len(keys):
        return {key: index for index, key in enumerate(keys)}
    return ranks


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    ranks = _rank_nodes(nodes, edges)
    buckets: dict[int, list[str]] = defaultdict(list)
    for index, node in enumerate(nodes):
        buckets[int(node.get("rank", ranks[_node_key(node, index)]))].append(_node_key(node, index))
    positions: dict[str, tuple[int, int]] = {}
    for rank, keys in sorted(buckets.items()):
        for row, key in enumerate(keys):
            positions[key] = (80 + rank * 250, 90 + row * 130)
    return positions


def compile_spec(spec: dict[str, Any]) -> DiagramDocument:
    title = str(spec.get("title") or "DiagramForge document")[:160]
    namespace = str(spec.get("namespace") or title)
    document_id = stable_id(namespace, "document", title)
    pages: list[DiagramPage] = []
    for page_index, raw_page in enumerate(spec.get("pages") or []):
        page_name = str(raw_page.get("name") or f"Page {page_index + 1}")[:80]
        page_id = stable_id(namespace, "page", str(raw_page.get("key") or page_name))
        raw_layers = raw_page.get("layers") or [{"key": "main", "name": "Main"}]
        layer_ids = {
            str(layer.get("key") or "main"): stable_id(
                namespace, "layer", f"{page_name}:{layer.get('key') or 'main'}"
            )
            for layer in raw_layers
        }
        layers = {
            layer_ids[str(layer.get("key") or "main")]: str(layer.get("name") or "Main")
            for layer in raw_layers
        }
        page = DiagramPage(
            page_id=page_id,
            name=page_name,
            width=int(raw_page.get("width") or 1600),
            height=int(raw_page.get("height") or 1000),
            layers=layers,
        )
        raw_nodes = list(raw_page.get("nodes") or [])
        raw_edges = list(raw_page.get("edges") or [])
        positions = _layout(raw_nodes, raw_edges)
        node_ids = {
            _node_key(raw_node, index): stable_id(
                namespace, "node", f"{page_name}:{_node_key(raw_node, index)}"
            )
            for index, raw_node in enumerate(raw_nodes)
        }
        for index, raw_node in enumerate(raw_nodes):
            key = _node_key(raw_node, index)
            node_id = node_ids[key]
            x, y = positions[key]
            layer_key = str(raw_node.get("layer") or "main")
            parent_key = str(raw_node.get("parent_key") or "")
            sibling_index = sum(
                1 for prior in raw_nodes[:index] if str(prior.get("parent_key") or "") == parent_key
            )
            is_container = bool(raw_node.get("container")) or str(raw_node.get("role") or "") in {
                "container",
                "group",
            }
            page.cells.append(
                DiagramCell(
                    cell_id=node_id,
                    kind="vertex",
                    label=str(raw_node.get("label") or key)[:500],
                    x=float(raw_node.get("x", 20 if parent_key else x)),
                    y=float(raw_node.get("y", 50 + sibling_index * 100 if parent_key else y)),
                    width=float(raw_node.get("width", 320 if is_container else 190)),
                    height=float(raw_node.get("height", 240 if is_container else 80)),
                    parent=node_ids.get(parent_key, layer_ids.get(layer_key, next(iter(layers)))),
                    style=str(
                        raw_node.get("style") or (CONTAINER_STYLE if is_container else NODE_STYLE)
                    ),
                    metadata={
                        "semantic_key": key,
                        "role": str(
                            raw_node.get("role") or ("container" if is_container else "node")
                        ),
                    },
                )
            )
        for index, raw_edge in enumerate(raw_edges):
            source_key = str(raw_edge.get("source") or "")
            target_key = str(raw_edge.get("target") or "")
            layer_key = str(raw_edge.get("layer") or "main")
            edge_key = str(raw_edge.get("key") or f"{source_key}-to-{target_key}-{index}")
            page.cells.append(
                DiagramCell(
                    cell_id=stable_id(namespace, "edge", f"{page_name}:{edge_key}"),
                    kind="edge",
                    label=str(raw_edge.get("label") or "")[:240],
                    parent=layer_ids.get(layer_key, next(iter(layers))),
                    source=node_ids.get(source_key, source_key),
                    target=node_ids.get(target_key, target_key),
                    style=str(raw_edge.get("style") or EDGE_STYLE),
                    metadata={"semantic_key": edge_key, "role": "connector"},
                )
            )
        pages.append(page)
    if not pages:
        raise ValueError("Diagram spec must contain at least one page")
    return DiagramDocument(document_id=document_id, title=title, pages=pages)


def recipe_spec(recipe_id: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    title = str(parameters.get("title") or "Synthetic Research System")
    if recipe_id == "research-framework-v1":
        top = [
            ("target", "01 · Research Target"),
            ("inputs", "02 · Multimodal Inputs"),
            ("fusion", "03 · Feature Extraction & Fusion"),
            ("learning", "04 · Teacher–Student Learning"),
            ("outcomes", "05 · Experimental Outcomes"),
        ]
        nodes = [
            {
                "key": key,
                "label": label,
                "x": 50 + index * 300,
                "y": 90,
                "width": 250,
                "height": 250,
                "style": ACCENT_STYLE,
                "role": "stage",
            }
            for index, (key, label) in enumerate(top)
        ]
        nodes.extend(
            [
                {
                    "key": "analysis",
                    "label": "Interoperability Analysis",
                    "x": 140,
                    "y": 470,
                    "width": 360,
                    "height": 130,
                    "style": SUMMARY_STYLE,
                    "role": "summary",
                },
                {
                    "key": "conclusions",
                    "label": "Main Conclusions",
                    "x": 620,
                    "y": 470,
                    "width": 360,
                    "height": 130,
                    "style": SUMMARY_STYLE,
                    "role": "summary",
                },
                {
                    "key": "applications",
                    "label": "Broad Applicability",
                    "x": 1100,
                    "y": 470,
                    "width": 360,
                    "height": 130,
                    "style": SUMMARY_STYLE,
                    "role": "summary",
                },
            ]
        )
        edges = [
            {"source": source, "target": target}
            for source, target in zip(
                [item[0] for item in top[:-1]], [item[0] for item in top[1:]], strict=True
            )
        ]
        edges.extend(
            [
                {"source": "outcomes", "target": "analysis"},
                {"source": "analysis", "target": "conclusions"},
                {"source": "conclusions", "target": "applications"},
            ]
        )
        return {
            "title": title,
            "namespace": str(parameters.get("namespace") or "research-framework-v1"),
            "pages": [
                {
                    "key": "framework",
                    "name": "Research Framework",
                    "width": 1600,
                    "height": 900,
                    "layers": [
                        {"key": "main", "name": "Framework"},
                        {"key": "notes", "name": "Annotations"},
                    ],
                    "nodes": nodes,
                    "edges": edges,
                }
            ],
        }
    if recipe_id == "system-architecture-v1":
        return {
            "title": str(parameters.get("title") or "CreNexus Safe Architecture"),
            "namespace": str(parameters.get("namespace") or "system-architecture-v1"),
            "pages": [
                {
                    "key": "architecture",
                    "name": "System Architecture",
                    "layers": [
                        {"key": "clients", "name": "Clients"},
                        {"key": "runtime", "name": "Runtime"},
                        {"key": "evidence", "name": "Evidence"},
                    ],
                    "nodes": [
                        {"key": "codex", "label": "Codex Skill", "layer": "clients"},
                        {"key": "mcp", "label": "CreNexus MCP", "layer": "runtime"},
                        {"key": "recipe", "label": "Typed Recipe DSL", "layer": "runtime"},
                        {"key": "adapter", "label": "Safe Adapter", "layer": "runtime"},
                        {"key": "software", "label": "Local Creative Software", "layer": "clients"},
                        {"key": "evidence", "label": "Evidence + Hash Gate", "layer": "evidence"},
                    ],
                    "edges": [
                        {"source": "codex", "target": "mcp"},
                        {"source": "mcp", "target": "recipe"},
                        {"source": "recipe", "target": "adapter"},
                        {"source": "adapter", "target": "software"},
                        {"source": "software", "target": "evidence"},
                        {"source": "evidence", "target": "mcp", "label": "verified state"},
                    ],
                }
            ],
        }
    raise ValueError(f"Unknown DiagramForge recipe: {recipe_id}")


def spec_from_outline(text: str, *, title: str = "Outline Diagram") -> dict[str, Any]:
    labels = [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]
    if not labels:
        raise ValueError("Outline input must contain at least one non-empty line")
    nodes = [{"key": f"item-{index + 1}", "label": label} for index, label in enumerate(labels)]
    edges = [
        {"source": f"item-{index}", "target": f"item-{index + 1}"} for index in range(1, len(nodes))
    ]
    return {"title": title, "pages": [{"name": "Outline", "nodes": nodes, "edges": edges}]}


_MERMAID_EDGE = re.compile(
    r"^\s*([A-Za-z0-9_-]+)(?:\[([^\]]+)\])?\s*--?>\s*([A-Za-z0-9_-]+)(?:\[([^\]]+)\])?"
)


def spec_from_mermaid(text: str, *, title: str = "Mermaid Import") -> dict[str, Any]:
    labels: dict[str, str] = {}
    edges: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _MERMAID_EDGE.match(line)
        if not match:
            continue
        source, source_label, target, target_label = match.groups()
        labels[source] = source_label or labels.get(source, source)
        labels[target] = target_label or labels.get(target, target)
        edges.append({"source": source, "target": target})
    if not edges:
        raise ValueError("Supported Mermaid input requires at least one A --> B edge")
    nodes = [{"key": key, "label": label} for key, label in labels.items()]
    return {"title": title, "pages": [{"name": "Mermaid", "nodes": nodes, "edges": edges}]}


def spec_from_csv(text: str, *, title: str = "CSV Import") -> dict[str, Any]:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV input must include a header and at least one row")
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        row_id = str(row.get("id") or f"row-{index + 1}")
        if row.get("source") and row.get("target"):
            edges.append(
                {
                    "source": str(row["source"]),
                    "target": str(row["target"]),
                    "label": str(row.get("label") or ""),
                }
            )
            continue
        nodes[row_id] = {"key": row_id, "label": str(row.get("label") or row_id)}
    for edge in edges:
        nodes.setdefault(edge["source"], {"key": edge["source"], "label": edge["source"]})
        nodes.setdefault(edge["target"], {"key": edge["target"], "label": edge["target"]})
    return {
        "title": title,
        "pages": [{"name": "CSV", "nodes": list(nodes.values()), "edges": edges}],
    }


def compile_input(
    *,
    input_format: str,
    content: str | None = None,
    spec: dict[str, Any] | None = None,
    recipe_id: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> DiagramDocument:
    if recipe_id:
        return compile_spec(recipe_spec(recipe_id, parameters))
    normalized = input_format.lower()
    if normalized in {"spec", "natural_language"} and spec:
        return compile_spec(spec)
    if normalized in {"outline", "natural_language"}:
        return compile_spec(spec_from_outline(content or ""))
    if normalized == "mermaid":
        return compile_spec(spec_from_mermaid(content or ""))
    if normalized == "csv":
        return compile_spec(spec_from_csv(content or ""))
    if normalized == "drawio_xml":
        return from_drawio_xml(content or "")
    raise ValueError(
        "input_format must be spec, natural_language, outline, mermaid, csv, or drawio_xml"
    )
