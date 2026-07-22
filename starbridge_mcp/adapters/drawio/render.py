from __future__ import annotations

import html

from .model import DiagramCell, DiagramDocument, to_drawio_xml


def _style_value(style: str, key: str, default: str) -> str:
    prefix = f"{key}="
    for part in style.split(";"):
        if part.startswith(prefix):
            return part[len(prefix) :]
    return default


def _absolute_position(
    cell: DiagramCell, vertices: dict[str, DiagramCell], trail: set[str] | None = None
) -> tuple[float, float]:
    trail = set(trail or ())
    if cell.cell_id in trail:
        return cell.x, cell.y
    parent = vertices.get(cell.parent)
    if parent is None:
        return cell.x, cell.y
    trail.add(cell.cell_id)
    parent_x, parent_y = _absolute_position(parent, vertices, trail)
    return parent_x + cell.x, parent_y + cell.y


def render_svg(document: DiagramDocument, *, page_index: int = 0) -> str:
    page = document.pages[page_index]
    vertices = {cell.cell_id: cell for cell in page.cells if cell.kind != "edge"}
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.width}" '
            f'height="{page.height}" viewBox="0 0 {page.width} {page.height}" '
            f'content="{html.escape(to_drawio_xml(document), quote=True)}">'
        ),
        '<defs><marker id="arrow" markerWidth="10" markerHeight="7" refX="9" '
        'refY="3.5" orient="auto"><path d="M0,0 L10,3.5 L0,7 z" '
        'fill="#475569"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]
    for cell in page.cells:
        if cell.kind != "edge" or cell.source not in vertices or cell.target not in vertices:
            continue
        source, target = vertices[cell.source], vertices[cell.target]
        source_x, source_y = _absolute_position(source, vertices)
        target_x, target_y = _absolute_position(target, vertices)
        x1, y1 = source_x + source.width / 2, source_y + source.height / 2
        x2, y2 = target_x + target.width / 2, target_y + target.height / 2
        middle = (x1 + x2) / 2
        lines.append(
            f'<path d="M{x1:g},{y1:g} L{middle:g},{y1:g} L{middle:g},{y2:g} L{x2:g},{y2:g}" '
            'fill="none" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>'
        )
        if cell.label:
            lines.append(
                f'<text x="{middle:g}" y="{min(y1, y2) - 8:g}" text-anchor="middle" '
                f'font-family="Arial" font-size="12" fill="#334155">{html.escape(cell.label)}</text>'
            )
    for cell in page.cells:
        if cell.kind == "edge":
            continue
        fill = _style_value(cell.style, "fillColor", "#F8FAFC")
        stroke = _style_value(cell.style, "strokeColor", "#334155")
        font = _style_value(cell.style, "fontColor", "#0F172A")
        cell_x, cell_y = _absolute_position(cell, vertices)
        lines.append(
            f'<rect x="{cell_x:g}" y="{cell_y:g}" width="{cell.width:g}" '
            f'height="{cell.height:g}" rx="12" fill="{html.escape(fill)}" '
            f'stroke="{html.escape(stroke)}" stroke-width="2"/>'
        )
        label = html.escape(cell.label)
        words = label.split()
        max_chars = max(10, int((cell.width - 24) / 8))
        wrapped: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                wrapped.append(current)
                current = word
            else:
                current = candidate
        if current:
            wrapped.append(current)
        if not wrapped:
            wrapped = [label]
        start_y = cell_y + cell.height / 2 - (len(wrapped) - 1) * 9
        lines.append(
            f'<text x="{cell_x + cell.width / 2:g}" y="{start_y:g}" text-anchor="middle" '
            f'font-family="Arial" font-size="14" fill="{html.escape(font)}">'
        )
        for index, row in enumerate(wrapped[:6]):
            lines.append(
                f'<tspan x="{cell_x + cell.width / 2:g}" dy="{0 if index == 0 else 18}">{row}</tspan>'
            )
        lines.append("</text>")
    lines.append("</svg>")
    return "\n".join(lines)
