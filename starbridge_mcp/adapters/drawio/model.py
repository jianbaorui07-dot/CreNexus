from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any


def stable_id(namespace: str, kind: str, key: str) -> str:
    """Return a repeatable Draw.io-safe identifier for semantic elements."""

    digest = hashlib.sha256(f"{namespace}:{kind}:{key}".encode()).hexdigest()[:14]
    return f"df_{kind[:2]}_{digest}"


@dataclass
class DiagramCell:
    cell_id: str
    kind: str
    label: str = ""
    x: float = 0
    y: float = 0
    width: float = 160
    height: float = 72
    parent: str = "layer-main"
    source: str | None = None
    target: str | None = None
    style: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagramPage:
    page_id: str
    name: str
    width: int = 1600
    height: int = 1000
    layers: dict[str, str] = field(default_factory=lambda: {"layer-main": "Main"})
    cells: list[DiagramCell] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "layers": dict(self.layers),
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass
class DiagramDocument:
    document_id: str
    title: str
    pages: list[DiagramPage]
    schema_version: str = "diagramforge.document.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "title": self.title,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DiagramDocument:
        pages: list[DiagramPage] = []
        for raw_page in payload.get("pages") or []:
            page = DiagramPage(
                page_id=str(raw_page["page_id"]),
                name=str(raw_page.get("name") or "Page"),
                width=int(raw_page.get("width") or 1600),
                height=int(raw_page.get("height") or 1000),
                layers={str(k): str(v) for k, v in (raw_page.get("layers") or {}).items()},
            )
            page.cells = [DiagramCell(**cell) for cell in raw_page.get("cells") or []]
            pages.append(page)
        return cls(
            document_id=str(payload["document_id"]),
            title=str(payload.get("title") or "DiagramForge document"),
            pages=pages,
            schema_version=str(payload.get("schema_version") or "diagramforge.document.v1"),
        )


def cell_hash(cell: DiagramCell) -> str:
    canonical = {
        "cell_id": cell.cell_id,
        "kind": cell.kind,
        "label": cell.label,
        "x": float(cell.x),
        "y": float(cell.y),
        "width": float(cell.width),
        "height": float(cell.height),
        "parent": cell.parent,
        "source": cell.source,
        "target": cell.target,
        "style": cell.style,
    }
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def document_cell_hashes(document: DiagramDocument) -> dict[str, str]:
    return {cell.cell_id: cell_hash(cell) for page in document.pages for cell in page.cells}


def document_sha256(document: DiagramDocument) -> str:
    payload = json.dumps(
        document.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _geometry(cell: DiagramCell) -> ET.Element:
    if cell.kind == "edge":
        return ET.Element("mxGeometry", {"relative": "1", "as": "geometry"})
    return ET.Element(
        "mxGeometry",
        {
            "x": f"{cell.x:g}",
            "y": f"{cell.y:g}",
            "width": f"{cell.width:g}",
            "height": f"{cell.height:g}",
            "as": "geometry",
        },
    )


def to_drawio_xml(document: DiagramDocument) -> str:
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "CreNexus",
            "agent": "DiagramForge",
            "version": "1.0",
            "type": "device",
            "id": document.document_id,
            "title": document.title,
        },
    )
    for page in document.pages:
        diagram = ET.SubElement(mxfile, "diagram", {"id": page.page_id, "name": page.name})
        graph = ET.SubElement(
            diagram,
            "mxGraphModel",
            {
                "dx": "1200",
                "dy": "800",
                "grid": "1",
                "gridSize": "10",
                "page": "1",
                "pageWidth": str(page.width),
                "pageHeight": str(page.height),
                "math": "0",
                "shadow": "0",
            },
        )
        root = ET.SubElement(graph, "root")
        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
        for layer_id, layer_name in page.layers.items():
            ET.SubElement(
                root,
                "mxCell",
                {"id": layer_id, "value": layer_name, "parent": "0"},
            )
        for cell in page.cells:
            attrs = {
                "id": cell.cell_id,
                "value": cell.label,
                "parent": cell.parent,
                "style": cell.style,
            }
            if cell.metadata.get("semantic_key"):
                attrs["dfSemanticKey"] = str(cell.metadata["semantic_key"])
            if cell.metadata.get("role"):
                attrs["dfRole"] = str(cell.metadata["role"])
            if cell.kind == "edge":
                attrs["edge"] = "1"
                if cell.source:
                    attrs["source"] = cell.source
                if cell.target:
                    attrs["target"] = cell.target
            else:
                attrs["vertex"] = "1"
            xml_cell = ET.SubElement(root, "mxCell", attrs)
            xml_cell.append(_geometry(cell))
        diagram.text = None
    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode", xml_declaration=False)


def _number(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def from_drawio_xml(xml_text: str) -> DiagramDocument:
    root = ET.fromstring(xml_text)
    if root.tag != "mxfile":
        raise ValueError("Draw.io document root must be mxfile")
    pages: list[DiagramPage] = []
    for page_index, diagram in enumerate(root.findall("diagram")):
        graph = diagram.find("mxGraphModel")
        graph_root = graph.find("root") if graph is not None else None
        if graph is None or graph_root is None:
            raise ValueError("Each diagram must contain mxGraphModel/root")
        page = DiagramPage(
            page_id=str(diagram.get("id") or f"page-{page_index + 1}"),
            name=str(diagram.get("name") or f"Page {page_index + 1}"),
            width=int(_number(graph.get("pageWidth"), 1600)),
            height=int(_number(graph.get("pageHeight"), 1000)),
            layers={},
        )
        raw_cells = graph_root.findall("mxCell")
        known_layers = {
            str(cell.get("id")): str(cell.get("value") or "Layer")
            for cell in raw_cells
            if cell.get("parent") == "0" and cell.get("id") not in {"0", "1"}
        }
        page.layers = known_layers or {"layer-main": "Main"}
        for raw in raw_cells:
            cell_id = str(raw.get("id") or "")
            if not cell_id or cell_id in {"0", "1"} or cell_id in page.layers:
                continue
            is_edge = raw.get("edge") == "1"
            geometry = raw.find("mxGeometry")
            page.cells.append(
                DiagramCell(
                    cell_id=cell_id,
                    kind="edge" if is_edge else "vertex",
                    label=str(raw.get("value") or ""),
                    x=_number(geometry.get("x") if geometry is not None else None, 0),
                    y=_number(geometry.get("y") if geometry is not None else None, 0),
                    width=_number(geometry.get("width") if geometry is not None else None, 160),
                    height=_number(geometry.get("height") if geometry is not None else None, 72),
                    parent=str(raw.get("parent") or next(iter(page.layers))),
                    source=raw.get("source"),
                    target=raw.get("target"),
                    style=str(raw.get("style") or ""),
                    metadata={
                        "semantic_key": str(raw.get("dfSemanticKey") or ""),
                        "role": str(raw.get("dfRole") or ""),
                    },
                )
            )
        pages.append(page)
    if not pages:
        raise ValueError("Draw.io document must contain at least one diagram page")
    title = str(root.get("title") or pages[0].name)
    return DiagramDocument(
        document_id=str(root.get("id") or stable_id(title, "document", title)),
        title=title,
        pages=pages,
    )
