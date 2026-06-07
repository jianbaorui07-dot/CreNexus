from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "examples" / "output" / "photoshop" / "subject-layer-practice"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create local subject cutout layers for Photoshop practice.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--rect", default="70,330,900,850", help="GrabCut rectangle: x,y,w,h")
    parser.add_argument("--iterations", type=int, default=5)
    return parser.parse_args()


def safe_output_dir(value: str) -> Path:
    target = Path(value)
    if not target.is_absolute():
        target = REPO_ROOT / target
    resolved = target.resolve()
    allowed = (REPO_ROOT / "examples" / "output" / "photoshop").resolve()
    if not resolved.is_relative_to(allowed):
        raise SystemExit(f"Output directory must stay inside {allowed}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def parse_rect(value: str) -> tuple[int, int, int, int]:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise SystemExit("--rect must be x,y,w,h")
    return tuple(parts)  # type: ignore[return-value]


def load_rgb(path: str) -> tuple[np.ndarray, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        raise SystemExit(f"Input image does not exist: {source}")
    with Image.open(source) as im:
        im = im.convert("RGB")
        rgb = np.array(im)
    return rgb, {
        "source_name": source.name,
        "source_sha256_12": hashlib.sha256(source.read_bytes()).hexdigest()[:12],
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
    }


def grabcut_subject(rgb: np.ndarray, rect: tuple[int, int, int, int], iterations: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    x, y, rw, rh = rect
    x = max(0, min(x, w - 2))
    y = max(0, min(y, h - 2))
    rw = max(2, min(rw, w - x))
    rh = max(2, min(rh, h - y))
    mask = np.full((h, w), cv2.GC_BGD, np.uint8)
    mask[y : y + rh, x : x + rw] = cv2.GC_PR_FGD
    add_subject_seeds(mask)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.grabCut(bgr, mask, None, bgd_model, fgd_model, iterations, cv2.GC_INIT_WITH_MASK)
    foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    foreground = keep_subject_components(foreground)
    kernel = np.ones((5, 5), np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    foreground = cv2.GaussianBlur(foreground, (5, 5), 0)
    return foreground


def add_subject_seeds(mask: np.ndarray) -> None:
    h, w = mask.shape
    seeds = [
        ((0.60, 0.38), (0.15, 0.12), 0),   # child face and head
        ((0.50, 0.50), (0.20, 0.16), -18),  # blue upper body
        ((0.61, 0.59), (0.34, 0.18), 0),   # red fish body
        ((0.25, 0.55), (0.22, 0.16), -8),  # fish tail
        ((0.56, 0.68), (0.18, 0.10), 0),   # hands and lower body
        ((0.82, 0.45), (0.13, 0.11), 20),  # fish eye/head area
    ]
    for (cx, cy), (ax, ay), angle in seeds:
        center = (int(w * cx), int(h * cy))
        axes = (max(4, int(w * ax)), max(4, int(h * ay)))
        cv2.ellipse(mask, center, axes, angle, 0, 360, cv2.GC_FGD, -1)


def keep_subject_components(mask: np.ndarray) -> np.ndarray:
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if num <= 1:
        return mask
    h, w = mask.shape
    # Keep the child/fish body cluster and large nearby attached components; reject poster text and distant waves.
    seed = np.zeros_like(mask)
    seed[int(h * 0.28) : int(h * 0.76), int(w * 0.25) : int(w * 0.98)] = 255
    kept = np.zeros_like(mask)
    for label in range(1, num):
        area = stats[label, cv2.CC_STAT_AREA]
        component = labels == label
        overlaps_seed = bool(np.any(component & (seed > 0)))
        if overlaps_seed and area > 800:
            kept[component] = 255
        elif area > 18000 and stats[label, cv2.CC_STAT_TOP] > int(h * 0.25):
            kept[component] = 255
    return kept


def rgba_from_mask(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    rgba = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def layer_alpha(mask: np.ndarray, selector: np.ndarray) -> np.ndarray:
    selected = np.where((mask > 16) & selector, mask, 0).astype(np.uint8)
    selected = cv2.medianBlur(selected, 3)
    return selected


def build_layer_masks(rgb: np.ndarray, subject: np.ndarray) -> dict[str, np.ndarray]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    dark = (gray < 92) | ((v < 125) & (s < 80))
    red = ((h < 12) | (h > 168)) & (s > 55) & (r > g + 18)
    orange = (h >= 7) & (h < 24) & (s > 40) & (r > b + 18)
    pink = ((h < 8) | (h > 168)) & (s > 30) & (v > 120) & (r > g + 8)
    blue = (h >= 82) & (h <= 112) & (s > 22) & (b >= r - 8)
    green = (h >= 35) & (h <= 86) & (s > 25)
    skin = (h >= 4) & (h <= 22) & (s >= 16) & (s <= 105) & (v > 128) & (r > b + 10)
    light = (v > 186) & (s < 90)
    line_art = cv2.Canny(gray, 50, 145) > 0

    return {
        "00_subject_full": subject,
        "01_ink_lines": layer_alpha(subject, dark | line_art),
        "02_skin_face_hands": layer_alpha(subject, skin),
        "03_red_fish_body": layer_alpha(subject, red),
        "04_blue_clothing": layer_alpha(subject, blue),
        "05_orange_tail_and_warm_shadow": layer_alpha(subject, orange & ~skin),
        "06_pink_lotus_and_blush": layer_alpha(subject, pink & ~red),
        "07_green_leaf_and_eye_details": layer_alpha(subject, green),
        "08_light_highlights": layer_alpha(subject, light),
    }


def save_layers(rgb: np.ndarray, masks: dict[str, np.ndarray], output_dir: Path) -> list[dict[str, Any]]:
    layer_dir = output_dir / "layers"
    layer_dir.mkdir(parents=True, exist_ok=True)
    layers: list[dict[str, Any]] = []
    for name, alpha in masks.items():
        path = layer_dir / f"{name}.png"
        rgba_from_mask(rgb, alpha).save(path)
        pixels = int(np.count_nonzero(alpha))
        layers.append(
            {
                "name": name,
                "file": path.relative_to(REPO_ROOT).as_posix(),
                "nontransparent_pixels": pixels,
                "coverage": round(pixels / float(alpha.size), 5),
            }
        )
    return layers


def make_contact_sheet(layers: list[dict[str, Any]], output_path: Path) -> None:
    thumbs: list[tuple[str, Image.Image, dict[str, Any]]] = []
    for layer in layers:
        image = Image.open(REPO_ROOT / layer["file"]).convert("RGBA")
        bbox = image.getbbox()
        if bbox:
            image = image.crop(bbox)
        image.thumbnail((260, 260), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (300, 300), (245, 245, 245, 255))
        canvas.alpha_composite(image, ((300 - image.width) // 2, (300 - image.height) // 2))
        thumbs.append((layer["name"], canvas.convert("RGB"), layer))
    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 360, rows * 380), "#f3f4f6")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, (name, image, layer) in enumerate(thumbs):
        x = (idx % cols) * 360
        y = (idx // cols) * 380
        sheet.paste(image, (x + 30, y + 20))
        draw.text((x + 30, y + 330), name, fill="#111827", font=font)
        draw.text((x + 30, y + 350), f"coverage: {layer['coverage']}", fill="#374151", font=font)
    sheet.save(output_path)


def main() -> None:
    args = parse_args()
    output_dir = safe_output_dir(args.output_dir)
    rgb, source = load_rgb(args.input)
    subject = grabcut_subject(rgb, parse_rect(args.rect), args.iterations)
    masks = build_layer_masks(rgb, subject)
    layers = save_layers(rgb, masks, output_dir)
    contact_sheet = output_dir / "subject_layers_contact_sheet.png"
    make_contact_sheet(layers, contact_sheet)

    report = {
        "bridge": "photoshop",
        "task": "subject_layer_practice",
        "source": source,
        "output_dir": output_dir.relative_to(REPO_ROOT).as_posix(),
        "mask_rect": args.rect,
        "layers": layers,
        "contact_sheet": contact_sheet.relative_to(REPO_ROOT).as_posix(),
        "warnings": [
            "This is a local dual-track practice result: Photoshop validates the workflow, structured masks create controllable layers.",
            "Source image paths are not written to this report.",
            "Layer masks are heuristic and should be manually reviewed in Photoshop before production use.",
        ],
    }
    report_path = output_dir / "subject_layer_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "report": report_path.relative_to(REPO_ROOT).as_posix(), "layers": len(layers)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
