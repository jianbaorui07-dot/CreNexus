from __future__ import annotations

import math
import os
import shutil
import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import ezdxf
import numpy as np
from ezdxf import units


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "examples" / "cad" / "output" / "wechat_design_traces" / "ultra_fine_reference_cad"
DXF_PATH = OUTPUT_DIR / "ultra_fine_reference_cad.dxf"


@dataclass(frozen=True)
class SheetSpec:
    file_name: str
    title: str
    target_width_mm: float
    calibration_note: str


SHEETS = [
    SheetSpec("7f00b729498ec53cf6ae82a4348cb8e1.png", "图2-0-1 家装原始结构图", 8400, "总宽8400mm"),
    SheetSpec("a441dcce858e6e7a3518406ff89f2c73.png", "室内地面材料铺装图", 8400, "总宽8400mm"),
    SheetSpec("749be60e3981b184173004a2e1cd4b0b.png", "室内家具平面布置图", 8400, "总宽8400mm"),
    SheetSpec("0ec18e1868ae7ddba6378ff0319d39d6.png", "室内顶面布置图", 8400, "总宽8400mm"),
    SheetSpec("29435ea16f086e5c558cde23d3519862.png", "图6-0-1 室内客厅B立面布置图", 7740, "立面总宽7740mm"),
    SheetSpec("0de5ff1f03b585cab21b9a4ddf5795b2.png", "1-1剖面图", 2700, "总高2700mm近似校准"),
    SheetSpec("17b56cb369472c6640f03a6d3b54f7da.png", "节点2 施工节点图", 800, "节点宽800mm"),
    SheetSpec("586031740ab444899a187feb7b2f3efa.png", "图9-0-1 施工节点图", 650, "底部宽650mm近似校准"),
]


def setup_doc() -> ezdxf.EzDxf:
    doc = ezdxf.new("R2010")
    doc.units = units.MM
    doc.header["$INSUNITS"] = units.MM
    layers = [
        ("UNDERLAY_IMAGE", 9),
        ("TRACE_CONTOUR_MAJOR", 7),
        ("TRACE_CONTOUR_FINE", 8),
        ("TRACE_STRAIGHT_LINES", 4),
        ("TRACE_DARK_PIXELS", 250),
        ("REFERENCE_FRAME", 3),
        ("REFERENCE_TEXT", 2),
        ("CALIBRATION_DIM", 1),
    ]
    for name, color in layers:
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)
    if "CHINESE" not in doc.styles:
        doc.styles.add("CHINESE", font="simhei.ttf")
    return doc


def add_text(msp, text: str, x: float, y: float, h: float, layer: str = "REFERENCE_TEXT") -> None:
    msp.add_text(text, height=h, dxfattribs={"layer": layer, "style": "CHINESE"}).set_placement((x, y))


def add_frame(msp, x: float, y: float, w: float, h: float) -> None:
    pad = max(w, h) * 0.02
    msp.add_lwpolyline(
        [(x - pad, y - pad), (x + w + pad, y - pad), (x + w + pad, y + h + pad), (x - pad, y + h + pad)],
        close=True,
        dxfattribs={"layer": "REFERENCE_FRAME"},
    )


def add_dim(msp, x: float, y: float, w: float, label: str) -> None:
    yy = y - max(160, w * 0.016)
    tick = max(35, w * 0.0035)
    msp.add_line((x, yy), (x + w, yy), dxfattribs={"layer": "CALIBRATION_DIM"})
    msp.add_line((x, y), (x, yy), dxfattribs={"layer": "CALIBRATION_DIM"})
    msp.add_line((x + w, y), (x + w, yy), dxfattribs={"layer": "CALIBRATION_DIM"})
    msp.add_line((x - tick, yy - tick), (x + tick, yy + tick), dxfattribs={"layer": "CALIBRATION_DIM"})
    msp.add_line((x + w - tick, yy - tick), (x + w + tick, yy + tick), dxfattribs={"layer": "CALIBRATION_DIM"})
    add_text(msp, label, x + w * 0.46, yy + tick * 1.4, max(65, w * 0.012), "CALIBRATION_DIM")


def image_masks(path: Path):
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise FileNotFoundError(path)
    denoised = cv2.bilateralFilter(gray, 5, 35, 35)
    adaptive = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        19,
        7,
    )
    dark = cv2.threshold(denoised, 185, 255, cv2.THRESH_BINARY_INV)[1]
    combined = cv2.bitwise_or(adaptive, dark)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
    edges = cv2.Canny(denoised, 40, 120, apertureSize=3)
    return gray, combined, edges


def transform_point(px: float, py: float, ox: float, oy: float, scale: float, image_h: int):
    return ox + px * scale, oy + (image_h - py) * scale


def add_contours(msp, mask, ox: float, oy: float, scale: float, image_h: int) -> int:
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    img_area = mask.shape[0] * mask.shape[1]
    min_area = max(1.0, img_area * 0.00000045)
    count = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter < 5:
            continue
        epsilon = max(0.28, perimeter * 0.0009)
        approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        if len(approx) < 2:
            continue
        if len(approx) > 420:
            approx = approx[:: math.ceil(len(approx) / 420)]
        points = [transform_point(float(px), float(py), ox, oy, scale, image_h) for px, py in approx]
        layer = "TRACE_CONTOUR_MAJOR" if area > min_area * 18 or perimeter > 220 else "TRACE_CONTOUR_FINE"
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
        count += 1
    return count


def add_hough_lines(msp, edges, ox: float, oy: float, scale: float, image_h: int) -> int:
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=28, minLineLength=18, maxLineGap=4)
    if lines is None:
        return 0
    seen = set()
    count = 0
    for raw in lines[:, 0, :]:
        x1, y1, x2, y2 = map(float, raw)
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 12:
            continue
        # Deduplicate very close line segments; Hough often returns doubles.
        key = tuple(round(v / 4) for v in (x1, y1, x2, y2))
        reverse_key = tuple(round(v / 4) for v in (x2, y2, x1, y1))
        if key in seen or reverse_key in seen:
            continue
        seen.add(key)
        p1 = transform_point(x1, y1, ox, oy, scale, image_h)
        p2 = transform_point(x2, y2, ox, oy, scale, image_h)
        msp.add_line(p1, p2, dxfattribs={"layer": "TRACE_STRAIGHT_LINES"})
        count += 1
    return count


def add_dark_pixel_runs(msp, mask, ox: float, oy: float, scale: float, image_h: int) -> int:
    # Add sparse horizontal/vertical run centerlines for tiny text, hatch, and furniture texture.
    # This layer is intentionally light gray and can be hidden if the drawing feels too dense.
    step = 3
    min_run = 10
    count = 0
    small = cv2.resize(mask, (mask.shape[1] // step, mask.shape[0] // step), interpolation=cv2.INTER_NEAREST)
    for row_idx in range(small.shape[0]):
        cols = np.where(small[row_idx] > 0)[0]
        if len(cols) == 0:
            continue
        splits = np.split(cols, np.where(np.diff(cols) > 1)[0] + 1)
        for run in splits:
            if len(run) < min_run:
                continue
            x1, x2 = float(run[0] * step), float(run[-1] * step)
            y = float(row_idx * step)
            p1 = transform_point(x1, y, ox, oy, scale, image_h)
            p2 = transform_point(x2, y, ox, oy, scale, image_h)
            msp.add_line(p1, p2, dxfattribs={"layer": "TRACE_DARK_PIXELS"})
            count += 1
    return count


def add_sheet(doc: ezdxf.EzDxf, source_dir: Path, spec: SheetSpec, ox: float, oy: float) -> tuple[float, float, int]:
    src = source_dir / spec.file_name
    copied = OUTPUT_DIR / spec.file_name
    shutil.copy2(src, copied)
    gray, mask, edges = image_masks(src)
    image_h, image_w = gray.shape
    scale = spec.target_width_mm / image_w
    width_mm = image_w * scale
    height_mm = image_h * scale

    msp = doc.modelspace()
    image_def = doc.add_image_def(copied.name, (image_w, image_h))
    image = msp.add_image(image_def, insert=(ox, oy), size_in_units=(width_mm, height_mm), dxfattribs={"layer": "UNDERLAY_IMAGE"})
    image.dxf.clipping = 1
    add_frame(msp, ox, oy, width_mm, height_mm)

    contour_count = add_contours(msp, mask, ox, oy, scale, image_h)
    line_count = add_hough_lines(msp, edges, ox, oy, scale, image_h)
    run_count = add_dark_pixel_runs(msp, mask, ox, oy, scale, image_h)

    title_h = max(90, width_mm * 0.017)
    add_text(msp, spec.title, ox, oy + height_mm + title_h * 1.55, title_h)
    add_text(msp, f"精细版：{spec.calibration_note}；含底图、轮廓线、直线识别、灰色细节层。", ox, oy + height_mm + title_h * 0.38, title_h * 0.52)
    add_dim(msp, ox, oy, width_mm, str(int(spec.target_width_mm)))
    return width_mm, height_mm, contour_count + line_count + run_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an ultra-fine CAD reference trace from supplied drawing PNGs.")
    parser.add_argument(
        "--source-dir",
        default=os.environ.get("STARBRIDGE_CAD_REFERENCE_IMAGE_DIR", ""),
        help="Directory containing the eight reference PNG files. Can also be set with STARBRIDGE_CAD_REFERENCE_IMAGE_DIR.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source_dir:
        raise SystemExit("Provide --source-dir or set STARBRIDGE_CAD_REFERENCE_IMAGE_DIR.")
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        raise SystemExit(f"Reference image directory does not exist: {source_dir}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = setup_doc()
    cursor_x = 0.0
    cursor_y = 0.0
    row_h = 0.0
    gap = 1900.0
    row_limit = 21000.0
    total_entities = 0

    for spec in SHEETS:
        w, h, count = add_sheet(doc, source_dir, spec, cursor_x, cursor_y)
        total_entities += count
        cursor_x += w + gap
        row_h = max(row_h, h)
        if cursor_x > row_limit:
            cursor_x = 0.0
            cursor_y -= row_h + gap
            row_h = 0.0

    add_text(
        doc.modelspace(),
        "超精细复刻版：请在AutoCAD中保留UNDERLAY_IMAGE作校核；可隐藏TRACE_DARK_PIXELS减少灰色细节密度。",
        0,
        1700,
        155,
    )
    doc.saveas(DXF_PATH)
    print(DXF_PATH)
    print(f"detail_entities={total_entities}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
