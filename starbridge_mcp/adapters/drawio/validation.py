from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from .model import DiagramCell, DiagramDocument

_UNSAFE_HTML_LABEL = re.compile(
    r"<\s*(?:script|img|iframe|object|embed|style|link|svg|math)\b", re.IGNORECASE
)
_UNSAFE_STYLE_VALUE = re.compile(
    r"(?:^|;)(?:link|image|imageData|source)=|javascript:|data:|https?://",
    re.IGNORECASE,
)


@dataclass
class DiagramValidationReport:
    ok: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def _overlap(a: DiagramCell, b: DiagramCell) -> float:
    width = max(0.0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
    height = max(0.0, min(a.y + a.height, b.y + b.height) - max(a.y, b.y))
    return width * height


def _absolute_position(
    cell: DiagramCell, vertices: dict[str, DiagramCell], trail: set[str] | None = None
) -> tuple[float, float]:
    trail = set(trail or ())
    if cell.cell_id in trail:
        raise ValueError("parent_cycle")
    parent = vertices.get(cell.parent)
    if parent is None:
        return cell.x, cell.y
    trail.add(cell.cell_id)
    parent_x, parent_y = _absolute_position(parent, vertices, trail)
    return parent_x + cell.x, parent_y + cell.y


def _style_map(style: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in style.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
    return result


def _rgb(hex_color: str) -> tuple[float, float, float] | None:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_color):
        return None
    values = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linear(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return tuple(linear(value) for value in values)  # type: ignore[return-value]


def _contrast(background: str, foreground: str) -> float | None:
    bg, fg = _rgb(background), _rgb(foreground)
    if bg is None or fg is None:
        return None
    bg_l = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]
    fg_l = 0.2126 * fg[0] + 0.7152 * fg[1] + 0.0722 * fg[2]
    light, dark = max(bg_l, fg_l), min(bg_l, fg_l)
    return (light + 0.05) / (dark + 0.05)


def validate_document(document: DiagramDocument) -> DiagramValidationReport:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    vertex_count = 0
    edge_count = 0
    for page in document.pages:
        page_ids = set(page.layers)
        for cell in page.cells:
            if _UNSAFE_HTML_LABEL.search(cell.label):
                errors.append(
                    {"code": "unsafe_html_label", "page": page.name, "element_id": cell.cell_id}
                )
            if _UNSAFE_STYLE_VALUE.search(cell.style):
                errors.append(
                    {
                        "code": "unsafe_external_style",
                        "page": page.name,
                        "element_id": cell.cell_id,
                    }
                )
            if cell.cell_id in identifiers:
                errors.append(
                    {"code": "duplicate_id", "page": page.name, "element_id": cell.cell_id}
                )
            identifiers.add(cell.cell_id)
            page_ids.add(cell.cell_id)
        vertices = [cell for cell in page.cells if cell.kind != "edge"]
        vertices_by_id = {cell.cell_id: cell for cell in vertices}
        edges = [cell for cell in page.cells if cell.kind == "edge"]
        vertex_ids = {cell.cell_id for cell in vertices}
        valid_parents = set(page.layers) | vertex_ids
        vertex_count += len(vertices)
        edge_count += len(edges)
        for cell in vertices:
            if cell.parent not in valid_parents:
                errors.append(
                    {"code": "missing_parent", "page": page.name, "element_id": cell.cell_id}
                )
            if cell.parent == cell.cell_id:
                errors.append(
                    {"code": "self_parent", "page": page.name, "element_id": cell.cell_id}
                )
            parent = vertices_by_id.get(cell.parent)
            if parent is not None and (
                cell.x < 0
                or cell.y < 0
                or cell.x + cell.width > parent.width
                or cell.y + cell.height > parent.height
            ):
                errors.append(
                    {
                        "code": "child_out_of_parent",
                        "page": page.name,
                        "element_id": cell.cell_id,
                    }
                )
            if cell.width <= 0 or cell.height <= 0:
                errors.append(
                    {"code": "invalid_geometry", "page": page.name, "element_id": cell.cell_id}
                )
            try:
                absolute_x, absolute_y = _absolute_position(cell, vertices_by_id)
            except ValueError:
                errors.append(
                    {"code": "parent_cycle", "page": page.name, "element_id": cell.cell_id}
                )
                absolute_x, absolute_y = cell.x, cell.y
            if (
                absolute_x < 0
                or absolute_y < 0
                or absolute_x + cell.width > page.width
                or absolute_y + cell.height > page.height
            ):
                errors.append(
                    {"code": "out_of_bounds", "page": page.name, "element_id": cell.cell_id}
                )
            estimated_lines = max(1, math.ceil(len(cell.label) * 7 / max(1, cell.width - 20)))
            if estimated_lines * 19 > cell.height - 12:
                warnings.append(
                    {"code": "text_may_clip", "page": page.name, "element_id": cell.cell_id}
                )
            style = _style_map(cell.style)
            ratio = _contrast(style.get("fillColor", ""), style.get("fontColor", ""))
            if ratio is not None and ratio < 4.5:
                warnings.append(
                    {
                        "code": "low_text_contrast",
                        "page": page.name,
                        "element_id": cell.cell_id,
                        "ratio": round(ratio, 2),
                    }
                )
        for index, first in enumerate(vertices):
            for second in vertices[index + 1 :]:
                if first.parent == second.parent and _overlap(first, second) > 1:
                    warnings.append(
                        {
                            "code": "element_overlap",
                            "page": page.name,
                            "element_ids": [first.cell_id, second.cell_id],
                        }
                    )
        for edge in edges:
            if not edge.source or edge.source not in page_ids:
                errors.append(
                    {"code": "missing_edge_source", "page": page.name, "element_id": edge.cell_id}
                )
            if not edge.target or edge.target not in page_ids:
                errors.append(
                    {"code": "missing_edge_target", "page": page.name, "element_id": edge.cell_id}
                )
            if edge.parent not in page.layers:
                errors.append(
                    {"code": "missing_layer", "page": page.name, "element_id": edge.cell_id}
                )
    return DiagramValidationReport(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        metrics={
            "page_count": len(document.pages),
            "layer_count": sum(len(page.layers) for page in document.pages),
            "element_count": vertex_count + edge_count,
            "vertex_count": vertex_count,
            "connector_count": edge_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    )
