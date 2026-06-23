"""Reduce dense vector line work into closed contour paths.

Input is the `lines.json` produced by extract_vector_lines.py. The script uses a
temporary high-resolution mask to integrate nearby lines and emit closed SVG
contours that can be opened by Illustrator.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

try:
    import cv2  # type: ignore[import-not-found]
    import fitz  # type: ignore[import-not-found]
    import numpy as np
except ImportError as exc:  # pragma: no cover - optional example dependency
    raise SystemExit("Install optional dependencies: python -m pip install pymupdf opencv-python numpy") from exc


TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def cubic_point(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], t: float) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
    )


def path_samples(path_d: str, samples_per_curve: int = 10) -> list[list[tuple[float, float]]]:
    tokens = TOKEN_RE.findall(path_d)
    index = 0
    current: tuple[float, float] | None = None
    segments: list[list[tuple[float, float]]] = []
    while index < len(tokens):
        command = tokens[index]
        index += 1
        if command == "M":
            current = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
        elif command == "L":
            end = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            if current:
                segments.append([current, end])
            current = end
        elif command == "C":
            p1 = (float(tokens[index]), float(tokens[index + 1]))
            p2 = (float(tokens[index + 2]), float(tokens[index + 3]))
            p3 = (float(tokens[index + 4]), float(tokens[index + 5]))
            index += 6
            if current:
                segment = [current]
                for step in range(1, samples_per_curve + 1):
                    segment.append(cubic_point(current, p1, p2, p3, step / samples_per_curve))
                segments.append(segment)
            current = p3
    return segments


def draw_mask(lines: list[dict[str, Any]], scale: float, pad: float) -> tuple[Any, tuple[float, float, float]]:
    x0 = min(line["bbox"][0] for line in lines) - pad
    y0 = min(line["bbox"][1] for line in lines) - pad
    x1 = max(line["bbox"][2] for line in lines) + pad
    y1 = max(line["bbox"][3] for line in lines) + pad
    mask = np.zeros((int(math.ceil((y1 - y0) * scale)), int(math.ceil((x1 - x0) * scale))), dtype=np.uint8)
    for line in lines:
        for segment in path_samples(line["path_d"]):
            points = np.array([[(x - x0) * scale, (y - y0) * scale] for x, y in segment], dtype=np.int32)
            if len(points) > 1:
                cv2.polylines(mask, [points], False, 255, 1, cv2.LINE_AA)
    return mask, (x0, y0, scale)


def contour_path(contour: Any, transform: tuple[float, float, float]) -> str:
    x0, y0, scale = transform
    points = contour.reshape(-1, 2)
    parts: list[str] = []
    for index, (px, py) in enumerate(points):
        x = x0 + float(px) / scale
        y = y0 + float(py) / scale
        parts.append(("M" if index == 0 else "L") + f" {x:.3f} {y:.3f}")
    parts.append("Z")
    return " ".join(parts)


def write_svg(path: Path, width: float, height: float, contours: list[dict[str, Any]]) -> None:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.4f}pt" height="{height:.4f}pt" viewBox="0 0 {width:.4f} {height:.4f}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g fill="none" stroke="#8a8a8a" stroke-width="0.35" stroke-linejoin="round">',
    ]
    for contour in contours:
        parts.append(
            f'<path id="closed-contour-{contour["id"]}" d="{escape(contour["path_d"])}">'
            f'<title>{contour["kind"]}; area {contour["area_pt2"]:.2f} pt2</title></path>'
        )
    parts.append("</g>")
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def parameters_for_mode(mode: str) -> dict[str, float | int]:
    if mode == "coarse":
        return {"scale": 8.0, "dilate_px": 8, "close_px": 18, "min_area_pt2": 10.0, "epsilon_ratio": 0.0018}
    if mode == "fine":
        return {"scale": 10.0, "dilate_px": 5, "close_px": 12, "min_area_pt2": 3.0, "epsilon_ratio": 0.0007}
    return {"scale": 8.0, "dilate_px": 8, "close_px": 18, "min_area_pt2": 10.0, "epsilon_ratio": 0.0018}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lines-json", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["coarse", "fine", "outer-only"], default="fine")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(Path(args.lines_json).read_text(encoding="utf-8"))
    lines = payload["lines"]
    width, height = payload["summary"]["page_size_pt"]
    params = parameters_for_mode(args.mode)

    mask, transform = draw_mask(lines, float(params["scale"]), pad=16)
    dilate_px = int(params["dilate_px"])
    close_px = int(params["close_px"])
    blob = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1)))
    blob = cv2.morphologyEx(blob, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_px * 2 + 1, close_px * 2 + 1)))
    contours, hierarchy = cv2.findContours(blob, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)

    exported: list[dict[str, Any]] = []
    if hierarchy is not None:
        for index, contour in enumerate(contours):
            parent = hierarchy[0][index][3]
            if args.mode == "outer-only" and parent != -1:
                continue
            area_pt2 = abs(cv2.contourArea(contour)) / float(params["scale"]) ** 2
            if area_pt2 < float(params["min_area_pt2"]):
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, max(0.8, float(params["epsilon_ratio"]) * perimeter), True)
            exported.append(
                {
                    "id": len(exported),
                    "kind": "outer" if parent == -1 else "inner",
                    "area_pt2": round(area_pt2, 3),
                    "vertices": int(len(approx)),
                    "path_d": contour_path(approx, transform),
                }
            )

    exported.sort(key=lambda item: (item["kind"] != "outer", -item["area_pt2"]))
    for index, contour in enumerate(exported):
        contour["id"] = index

    svg_path = out_dir / "closed_contours.svg"
    write_svg(svg_path, float(width), float(height), exported)
    pdf_doc = fitz.open("pdf", fitz.open("svg", svg_path.read_bytes()).convert_to_pdf())
    pdf_doc.save(out_dir / "closed_contours.pdf")
    (out_dir / "closed_contours_summary.json").write_text(
        json.dumps(
            {
                "summary": {
                    "source_lines": len(lines),
                    "closed_contours": len(exported),
                    "outer_contours": sum(1 for item in exported if item["kind"] == "outer"),
                    "inner_contours": sum(1 for item in exported if item["kind"] == "inner"),
                    "total_vertices": sum(item["vertices"] for item in exported),
                    "mode": args.mode,
                    "parameters": params,
                },
                "contours": exported,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

