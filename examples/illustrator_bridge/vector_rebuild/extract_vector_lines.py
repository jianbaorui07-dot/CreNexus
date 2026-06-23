"""Extract stroke paths from PDF-compatible AI/PDF/SVG files.

This is a local-only prototype helper for StarBridge Illustrator research.
It does not require Illustrator to be open and does not upload source artwork.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

try:
    import fitz  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - optional example dependency
    raise SystemExit("Install optional dependency first: python -m pip install pymupdf") from exc


Point = tuple[float, float]


def xy(point: Any) -> Point:
    return float(point.x), float(point.y)


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def color_to_hex(color: Any) -> str:
    if not color:
        return "#000000"
    return "#" + "".join(f"{max(0, min(255, round(float(c) * 255))):02x}" for c in color[:3])


def path_data_and_length(items: list[Any], samples_per_curve: int) -> tuple[str, float]:
    commands: list[str] = []
    length = 0.0
    for item in items:
        kind = item[0]
        if kind == "l":
            p0 = xy(item[1])
            p1 = xy(item[2])
            commands.append(f"M {p0[0]:.4f} {p0[1]:.4f} L {p1[0]:.4f} {p1[1]:.4f}")
            length += distance(p0, p1)
        elif kind == "c":
            p0 = xy(item[1])
            p1 = xy(item[2])
            p2 = xy(item[3])
            p3 = xy(item[4])
            commands.append(
                f"M {p0[0]:.4f} {p0[1]:.4f} "
                f"C {p1[0]:.4f} {p1[1]:.4f}, {p2[0]:.4f} {p2[1]:.4f}, {p3[0]:.4f} {p3[1]:.4f}"
            )
            previous = p0
            for step in range(1, samples_per_curve + 1):
                current = cubic_point(p0, p1, p2, p3, step / samples_per_curve)
                length += distance(previous, current)
                previous = current
    return " ".join(commands), length


def write_svg(path: Path, width: float, height: float, lines: list[dict[str, Any]]) -> None:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.4f}pt" height="{height:.4f}pt" viewBox="0 0 {width:.4f} {height:.4f}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for line in lines:
        parts.append(
            f'<path id="line-{line["id"]}" d="{escape(line["path_d"])}" '
            f'stroke="{color_to_hex(line.get("color"))}" stroke-width="{line["width_pt"]:.4f}">'
            f'<title>line {line["id"]}; length {line["length_pt"]:.4f} pt</title></path>'
        )
    parts.append("</g>")
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="PDF-compatible .ai, PDF, or SVG input")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--samples-per-curve", type=int, default=12)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(args.input)
    page = doc[0]
    drawings = page.get_drawings()

    item_types: Counter[str] = Counter()
    layers: Counter[str] = Counter()
    widths: Counter[float] = Counter()
    lines: list[dict[str, Any]] = []
    for index, drawing in enumerate(drawings):
        path_d, length = path_data_and_length(drawing["items"], args.samples_per_curve)
        for item in drawing["items"]:
            item_types[item[0]] += 1
        layer = drawing.get("layer") or ""
        layers[layer] += 1
        width = round(float(drawing.get("width") or 0), 4)
        widths[width] += 1
        rect = drawing["rect"]
        lines.append(
            {
                "id": index,
                "layer": layer,
                "path_d": path_d,
                "bbox": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
                "length_pt": round(length, 4),
                "width_pt": width,
                "color": list(drawing.get("color") or (0, 0, 0)),
            }
        )

    summary = {
        "source": str(Path(args.input)),
        "page_size_pt": [float(page.rect.width), float(page.rect.height)],
        "line_count": len(lines),
        "item_types": dict(item_types),
        "layers": dict(layers),
        "stroke_widths_pt": {str(k): v for k, v in widths.items()},
        "total_centerline_length_pt": round(sum(line["length_pt"] for line in lines), 4),
    }
    (out_dir / "lines.json").write_text(
        json.dumps({"summary": summary, "lines": lines}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_svg(out_dir / "rebuild.svg", float(page.rect.width), float(page.rect.height), lines)


if __name__ == "__main__":
    main()

