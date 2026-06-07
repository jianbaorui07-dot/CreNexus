from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "examples" / "output" / "illustrator" / "trace-practice"
MAX_WORK_DIMENSION = 1200


@dataclass(frozen=True)
class TracePreset:
    name: str
    colors: int
    blur: int
    edge_weight: float
    canny_low: int
    canny_high: int
    min_area: float
    simplify: float
    saturation: float
    contrast: float
    note: str


PRESETS: dict[str, TracePreset] = {
    "flat_8": TracePreset(
        name="flat_8",
        colors=8,
        blur=7,
        edge_weight=0.20,
        canny_low=60,
        canny_high=150,
        min_area=110.0,
        simplify=0.010,
        saturation=1.05,
        contrast=1.04,
        note="large color blocks, low detail, easiest to edit",
    ),
    "flat_16": TracePreset(
        name="flat_16",
        colors=16,
        blur=5,
        edge_weight=0.26,
        canny_low=50,
        canny_high=140,
        min_area=75.0,
        simplify=0.008,
        saturation=1.08,
        contrast=1.06,
        note="balanced flat illustration preset",
    ),
    "line_color_16": TracePreset(
        name="line_color_16",
        colors=16,
        blur=3,
        edge_weight=0.42,
        canny_low=38,
        canny_high=120,
        min_area=45.0,
        simplify=0.006,
        saturation=1.02,
        contrast=1.12,
        note="keeps ink-like line detail over limited colors",
    ),
    "nianhua_24": TracePreset(
        name="nianhua_24",
        colors=24,
        blur=3,
        edge_weight=0.36,
        canny_low=34,
        canny_high=115,
        min_area=32.0,
        simplify=0.005,
        saturation=1.12,
        contrast=1.10,
        note="higher-detail new-year-picture style preview",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate controllable local trace previews for Illustrator practice.")
    parser.add_argument("--input", required=True, help="Source image path. This path is not written into the public report.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Ignored local output directory.")
    parser.add_argument("--presets", default="flat_8,flat_16,line_color_16,nianhua_24", help="Comma-separated preset names.")
    parser.add_argument("--commit-preset", default="", help="Copy one preset to final.svg/final_preview.png.")
    parser.add_argument("--max-dimension", type=int, default=MAX_WORK_DIMENSION)
    return parser.parse_args()


def safe_output_dir(value: str) -> Path:
    target = Path(value)
    if not target.is_absolute():
        target = REPO_ROOT / target
    resolved = target.resolve()
    allowed = (REPO_ROOT / "examples" / "output" / "illustrator").resolve()
    if not resolved.is_relative_to(allowed):
        raise SystemExit(f"Output directory must stay inside {allowed}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def load_image(path: str, max_dimension: int) -> tuple[np.ndarray, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise SystemExit(f"Input image does not exist: {source}")
    with Image.open(source) as im:
        im = im.convert("RGB")
        original_size = im.size
        scale = min(1.0, max_dimension / max(original_size))
        if scale < 1.0:
            new_size = (max(1, round(original_size[0] * scale)), max(1, round(original_size[1] * scale)))
            im = im.resize(new_size, Image.Resampling.LANCZOS)
        rgb = np.array(im)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return rgb, {
        "source_name": source.name,
        "source_sha256_12": digest,
        "original_width": original_size[0],
        "original_height": original_size[1],
        "work_width": int(rgb.shape[1]),
        "work_height": int(rgb.shape[0]),
    }


def adjust_color(rgb: np.ndarray, preset: TracePreset) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * preset.saturation, 0, 255)
    rgb2 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    lab = cv2.cvtColor(rgb2, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l = np.clip((l.astype(np.float32) - 128.0) * preset.contrast + 128.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2RGB)


def quantize(rgb: np.ndarray, colors: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pixels = rgb.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.8)
    _, labels, centers = cv2.kmeans(pixels, colors, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8)
    labels = labels.flatten()
    quantized = centers[labels].reshape(rgb.shape)
    return quantized, labels.reshape(rgb.shape[:2]), centers


def edge_overlay(rgb: np.ndarray, preset: TracePreset) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, preset.canny_low, preset.canny_high)
    if preset.edge_weight <= 0:
        return rgb, edges
    dark = np.zeros_like(rgb)
    edge_mask = (edges > 0)[:, :, None].astype(np.float32)
    mixed = rgb.astype(np.float32) * (1.0 - edge_mask * preset.edge_weight) + dark * (edge_mask * preset.edge_weight)
    return np.clip(mixed, 0, 255).astype(np.uint8), edges


def run_preset(rgb: np.ndarray, preset: TracePreset) -> dict[str, Any]:
    adjusted = adjust_color(rgb, preset)
    if preset.blur > 1:
        blur = preset.blur if preset.blur % 2 == 1 else preset.blur + 1
        adjusted = cv2.bilateralFilter(adjusted, blur, 55, 55)
    quantized, labels, centers = quantize(adjusted, preset.colors)
    preview, edges = edge_overlay(quantized, preset)
    paths, contour_count, skipped_count = build_svg_paths(labels, centers, preset)
    edge_density = float(np.count_nonzero(edges)) / float(edges.size)
    return {
        "preview": preview,
        "paths": paths,
        "contour_count": contour_count,
        "skipped_count": skipped_count,
        "edge_density": edge_density,
        "palette": [rgb_hex(center) for center in centers],
    }


def rgb_hex(color: np.ndarray) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(color[0]), int(color[1]), int(color[2]))


def build_svg_paths(labels: np.ndarray, centers: np.ndarray, preset: TracePreset) -> tuple[list[str], int, int]:
    paths: list[str] = []
    contour_count = 0
    skipped_count = 0
    for idx, center in enumerate(centers):
        mask = (labels == idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        fill = rgb_hex(center)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < preset.min_area:
                skipped_count += 1
                continue
            perimeter = cv2.arcLength(contour, True)
            epsilon = max(0.6, perimeter * preset.simplify)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            if len(approx) < 3:
                skipped_count += 1
                continue
            points = approx.reshape((-1, 2))
            path = "M " + " L ".join(f"{int(x)} {int(y)}" for x, y in points) + " Z"
            paths.append(f'<path d="{path}" fill="{fill}" stroke="none"/>')
            contour_count += 1
    return paths, contour_count, skipped_count


def write_svg(path: Path, width: int, height: int, paths: list[str]) -> None:
    body = "\n  ".join(paths)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <rect width="{width}" height="{height}" fill="#ffffff"/>\n'
        f"  {body}\n"
        "</svg>\n",
        encoding="utf-8",
    )


def save_preview(path: Path, rgb: np.ndarray) -> None:
    Image.fromarray(rgb).save(path)


def make_contact_sheet(previews: list[tuple[str, Path, dict[str, Any]]], output_path: Path) -> None:
    thumbs: list[tuple[str, Image.Image, dict[str, Any]]] = []
    for name, preview_path, metrics in previews:
        image = Image.open(preview_path).convert("RGB")
        image.thumbnail((360, 540), Image.Resampling.LANCZOS)
        thumbs.append((name, image.copy(), metrics))
    if not thumbs:
        return
    cols = 2
    rows = math.ceil(len(thumbs) / cols)
    cell_w, cell_h = 430, 650
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#f3f4f6")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, (name, image, metrics) in enumerate(thumbs):
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        sheet.paste(image, (x + 35, y + 25))
        lines = [
            name,
            f"paths: {metrics['path_count']}  colors: {metrics['color_count']}",
            f"edge: {metrics['edge_density']:.3f}  score: {metrics['control_score']:.1f}",
        ]
        for line_idx, line in enumerate(lines):
            draw.text((x + 35, y + 580 + line_idx * 18), line, fill="#111827", font=font)
    sheet.save(output_path)


def score_metrics(path_count: int, edge_density: float, colors: int) -> float:
    path_penalty = min(path_count / 2200.0, 1.8)
    edge_bonus = min(edge_density * 4.0, 1.0)
    color_penalty = max(colors - 16, 0) / 32.0
    return max(0.0, 100.0 - path_penalty * 42.0 + edge_bonus * 12.0 - color_penalty * 12.0)


def main() -> None:
    args = parse_args()
    output_dir = safe_output_dir(args.output_dir)
    rgb, source_meta = load_image(args.input, args.max_dimension)
    preset_names = [name.strip() for name in args.presets.split(",") if name.strip()]
    unknown = [name for name in preset_names if name not in PRESETS]
    if unknown:
        raise SystemExit(f"Unknown preset(s): {', '.join(unknown)}")

    report: dict[str, Any] = {
        "bridge": "illustrator",
        "task": "trace_photo_preview",
        "source": source_meta,
        "output_dir": output_dir.relative_to(REPO_ROOT).as_posix(),
        "presets": [],
        "recommended_preset": None,
        "final": None,
        "warnings": [
            "This is a local controllability practice run, not a claim of production Illustrator Image Trace parity.",
            "Source image paths are not written to this report.",
        ],
    }
    contact_inputs: list[tuple[str, Path, dict[str, Any]]] = []
    width, height = int(rgb.shape[1]), int(rgb.shape[0])

    for name in preset_names:
        preset = PRESETS[name]
        result = run_preset(rgb, preset)
        preview_path = output_dir / f"{name}_preview.png"
        svg_path = output_dir / f"{name}.svg"
        save_preview(preview_path, result["preview"])
        write_svg(svg_path, width, height, result["paths"])
        svg_size = svg_path.stat().st_size
        metrics = {
            "name": name,
            "note": preset.note,
            "color_count": preset.colors,
            "path_count": result["contour_count"],
            "skipped_small_regions": result["skipped_count"],
            "edge_density": round(result["edge_density"], 5),
            "svg_size_kb": round(svg_size / 1024.0, 1),
            "preview": preview_path.relative_to(REPO_ROOT).as_posix(),
            "svg": svg_path.relative_to(REPO_ROOT).as_posix(),
            "palette": result["palette"],
        }
        metrics["control_score"] = round(score_metrics(metrics["path_count"], result["edge_density"], preset.colors), 1)
        report["presets"].append(metrics)
        contact_inputs.append((name, preview_path, metrics))

    best = max(report["presets"], key=lambda item: item["control_score"]) if report["presets"] else None
    report["recommended_preset"] = best["name"] if best else None
    contact_sheet = output_dir / "trace_contact_sheet.png"
    make_contact_sheet(contact_inputs, contact_sheet)
    report["contact_sheet"] = contact_sheet.relative_to(REPO_ROOT).as_posix()

    if args.commit_preset:
        if args.commit_preset not in preset_names:
            raise SystemExit("--commit-preset must be one of the generated presets")
        final_svg = output_dir / "final_trace.svg"
        final_preview = output_dir / "final_preview.png"
        shutil.copyfile(output_dir / f"{args.commit_preset}.svg", final_svg)
        shutil.copyfile(output_dir / f"{args.commit_preset}_preview.png", final_preview)
        report["final"] = {
            "preset": args.commit_preset,
            "svg": final_svg.relative_to(REPO_ROOT).as_posix(),
            "preview": final_preview.relative_to(REPO_ROOT).as_posix(),
        }

    report_path = output_dir / "trace_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": report_path.relative_to(REPO_ROOT).as_posix(), "recommended_preset": report["recommended_preset"], "final": report["final"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
