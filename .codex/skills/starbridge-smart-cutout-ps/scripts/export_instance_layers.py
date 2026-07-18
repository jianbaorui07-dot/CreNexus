#!/usr/bin/env python
"""Export prompted instance masks as disjoint StarBridge Photoshop layers."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "starbridge.image_to_editable_psd.v1"
SPEC_VERSION = "starbridge.smart_cutout_spec.v1"
GROUPS_BOTTOM_TO_TOP = (
    "04_背景",
    "03_装饰",
    "02_主体",
    "01_文字",
    "00_原始参考",
    "99_QA",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export local instance masks to a Photoshop-ready StarBridge manifest."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--model",
        required=True,
        type=Path,
        help="Explicit local segmentation model file; automatic downloads are refused.",
    )
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("Repository root could not be located")


def safe_output_dir(value: Path, root: Path) -> Path:
    path = value if value.is_absolute() else root / value
    resolved = path.resolve()
    allowed = (root / "examples" / "output" / "photoshop").resolve()
    if not resolved.is_relative_to(allowed):
        raise ValueError("Output must stay inside examples/output/photoshop")
    return resolved


def load_runtime() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        from ultralytics import SAM
    except ImportError as exc:
        raise RuntimeError(
            "Missing optional runtime. Install it explicitly with: python -m pip install ultralytics"
        ) from exc
    return cv2, np, Image, ImageDraw, ImageFont, SAM


def scale_box(box: list[float], width: int, height: int, normalized: bool) -> list[float]:
    if len(box) != 4:
        raise ValueError("Each layer.box must contain four values")
    if normalized:
        x1, y1, x2, y2 = (
            box[0] * width,
            box[1] * height,
            box[2] * width,
            box[3] * height,
        )
    else:
        x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("A prompt box is outside the image or has invalid bounds")
    return [float(x1), float(y1), float(x2), float(y2)]


def scale_points(
    points: list[list[float]], width: int, height: int, normalized: bool
) -> list[list[float]]:
    output: list[list[float]] = []
    for point in points:
        if len(point) != 2:
            raise ValueError("Each background point must contain two values")
        x, y = (point[0] * width, point[1] * height) if normalized else point
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("A background point is outside the image")
        output.append([float(x), float(y)])
    return output


def resize_mask(cv2: Any, np: Any, mask: Any, width: int, height: int) -> Any:
    return (
        cv2.resize(mask.astype(np.float32), (width, height), interpolation=cv2.INTER_LINEAR) > 0.5
    )


def remove_small_components(cv2: Any, np: Any, mask: Any) -> Any:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if count <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    threshold = max(60, int(areas.max() * 0.002))
    keep = np.flatnonzero(areas >= threshold) + 1
    return np.isin(labels, keep)


def refine_sky(cv2: Any, np: Any, rgb: Any, sky: Any) -> Any:
    height, width = sky.shape
    rows = np.arange(height)
    reference = np.full((height, 3), np.nan, dtype=np.float32)
    for y in range(height):
        row = rgb[y]
        hsv = cv2.cvtColor(row[None, :, :], cv2.COLOR_RGB2HSV)[0]
        likely = (hsv[:, 0] >= 90) & (hsv[:, 0] <= 120) & (hsv[:, 2] >= 100)
        if np.count_nonzero(likely) >= max(20, width // 50):
            reference[y] = np.median(row[likely], axis=0)
    for channel in range(3):
        valid = np.isfinite(reference[:, channel])
        if not np.any(valid):
            return sky
        reference[:, channel] = np.interp(rows, rows[valid], reference[valid, channel])
    distance = np.linalg.norm(rgb.astype(np.float32) - reference[:, None, :], axis=2)
    ring = cv2.dilate(sky.astype(np.uint8), np.ones((9, 9), np.uint8), iterations=1) > 0
    return sky | (ring & (distance < 18.0))


def save_rgba(Image: Any, np: Any, path: Path, rgb: Any, mask: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = np.dstack([rgb, mask.astype(np.uint8) * 255])
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def write_index_preview(
    Image: Any, ImageDraw: Any, ImageFont: Any, np: Any, path: Path, rgb: Any, masks: list[Any]
) -> None:
    colors = np.asarray(
        [
            (230, 74, 74),
            (245, 139, 48),
            (249, 196, 65),
            (172, 213, 71),
            (66, 190, 107),
            (55, 190, 168),
            (58, 167, 218),
            (73, 128, 232),
            (108, 92, 231),
            (151, 83, 221),
            (199, 74, 199),
            (232, 79, 150),
        ],
        dtype=np.float32,
    )
    image = rgb.astype(np.float32).copy()
    for index, mask in enumerate(masks):
        image[mask] = image[mask] * 0.58 + colors[index % len(colors)] * 0.42
    preview = Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    for index, mask in enumerate(masks, start=1):
        ys, xs = np.where(mask)
        if not len(xs):
            continue
        x, y = int(np.median(xs)), max(10, int(ys.min()) - 12)
        label = f"{index:02d}"
        box = draw.textbbox((x, y), label, font=font, anchor="mm")
        draw.rectangle((box[0] - 4, box[1] - 2, box[2] + 4, box[3] + 2), fill=(12, 18, 28))
        draw.text((x, y), label, font=font, fill=(255, 255, 255), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    preview.save(path, quality=94)


def write_cutout_preview(
    Image: Any, ImageDraw: Any, ImageFont: Any, np: Any, path: Path, rgb: Any, masks: list[Any]
) -> None:
    columns, cell_w, cell_h = 4, 400, 250
    rows = (len(masks) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), (24, 29, 37))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, mask in enumerate(masks):
        col, row = index % columns, index // columns
        x0, y0 = col * cell_w, row * cell_h
        for y in range(y0 + 28, y0 + cell_h, 14):
            for x in range(x0 + 8, x0 + cell_w - 8, 14):
                shade = 238 if ((x - x0) // 14 + (y - y0) // 14) % 2 else 211
                draw.rectangle((x, y, x + 13, y + 13), fill=(shade, shade, shade))
        draw.text((x0 + 8, y0 + 7), f"SUBJECT {index + 1:02d}", font=font, fill=(248, 250, 253))
        ys, xs = np.where(mask)
        if not len(xs):
            continue
        left, right = int(xs.min()), int(xs.max()) + 1
        top, bottom = int(ys.min()), int(ys.max()) + 1
        cutout = Image.fromarray(
            np.dstack(
                [rgb[top:bottom, left:right], mask[top:bottom, left:right].astype(np.uint8) * 255]
            ),
            "RGBA",
        )
        scale = min((cell_w - 36) / cutout.width, (cell_h - 58) / cutout.height, 1.0)
        cutout = cutout.resize(
            (max(1, int(cutout.width * scale)), max(1, int(cutout.height * scale))),
            Image.Resampling.LANCZOS,
        )
        paste_x = x0 + (cell_w - cutout.width) // 2
        paste_y = y0 + 34 + (cell_h - 40 - cutout.height) // 2
        canvas.paste(cutout, (paste_x, paste_y), cutout)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.confirm_write:
        raise PermissionError("This write operation requires --confirm-write")
    root = repo_root()
    input_path = args.input.expanduser().resolve()
    spec_path = args.spec.expanduser().resolve()
    model_path = args.model.expanduser().resolve()
    output_path = safe_output_dir(args.out_dir, root)
    if not input_path.is_file():
        raise FileNotFoundError("Input image does not exist")
    if not spec_path.is_file():
        raise FileNotFoundError("Instance spec does not exist")
    if not model_path.is_file():
        raise FileNotFoundError("Segmentation model must be an explicit local file")
    manifest_path = output_path / "manifest.json"
    if manifest_path.exists() and not args.force:
        raise FileExistsError("Output job already exists; inspect it or rerun with --force")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != SPEC_VERSION:
        raise ValueError("Unsupported smart cutout spec schema_version")
    layers = spec.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("spec.layers must contain at least one subject")
    names = [str(layer.get("name") or "").strip() for layer in layers]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("Every subject layer name must be non-empty and unique")

    cv2, np, Image, ImageDraw, ImageFont, SAM = load_runtime()
    pil_image = Image.open(input_path).convert("RGB")
    rgb = np.asarray(pil_image)
    height, width = rgb.shape[:2]
    normalized = spec.get("box_mode", "pixels") == "normalized"
    if spec.get("box_mode", "pixels") not in {"pixels", "normalized"}:
        raise ValueError("box_mode must be pixels or normalized")
    boxes = np.asarray(
        [scale_box(layer["box"], width, height, normalized) for layer in layers],
        dtype=np.float32,
    )

    model = SAM(str(model_path))
    result = model.predict(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), bboxes=boxes, verbose=False)[0]
    if result.masks is None:
        raise RuntimeError("The segmentation model returned no subject masks")
    raw_masks = [
        resize_mask(cv2, np, mask, width, height) for mask in result.masks.data.cpu().numpy()
    ]
    if len(raw_masks) != len(layers):
        raise RuntimeError("The segmentation model did not return one mask per prompt box")

    background_spec = spec.get("background") or {}
    background_points = background_spec.get("points") or []
    if background_points:
        points = np.asarray(
            [scale_points(background_points, width, height, normalized)], dtype=np.float32
        )
        labels = np.ones((1, len(background_points)), dtype=np.int32)
        background_result = model.predict(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
            points=points,
            labels=labels,
            verbose=False,
        )[0]
        if background_result.masks is None:
            raise RuntimeError("The segmentation model returned no background mask")
        background = resize_mask(
            cv2, np, background_result.masks.data[0].cpu().numpy(), width, height
        )
        if background_spec.get("refine") == "sky":
            background = refine_sky(cv2, np, rgb, background)
        elif background_spec.get("refine", "none") != "none":
            raise ValueError("background.refine must be none or sky")
        available = ~background
    else:
        background = np.zeros((height, width), dtype=bool)
        available = np.ones((height, width), dtype=bool)

    candidates = [
        cv2.morphologyEx(
            remove_small_components(cv2, np, mask).astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((3, 3), np.uint8),
        ).astype(bool)
        & available
        for mask in raw_masks
    ]
    priority_order = sorted(
        range(len(layers)),
        key=lambda index: int(layers[index].get("priority", len(layers) - index)),
        reverse=True,
    )
    assigned = np.zeros((height, width), dtype=bool)
    masks = [np.zeros_like(assigned) for _ in layers]
    for index in priority_order:
        masks[index] = candidates[index] & ~assigned
        assigned |= masks[index]

    remainder = (~background) & ~assigned if background_points else np.zeros_like(background)
    if not background_points:
        background = ~assigned
    coverage = background.astype(np.uint8) + remainder.astype(np.uint8)
    for mask in masks:
        coverage += mask.astype(np.uint8)
    if not np.all(coverage == 1):
        raise RuntimeError("Layer partition is not exact and disjoint")

    background_rel = Path("layers/04_background/background.png")
    remainder_rel = Path("layers/04_background/remainder.png")
    reference_rel = Path("layers/00_original_reference.png")
    save_rgba(Image, np, output_path / background_rel, rgb, background)
    save_rgba(Image, np, output_path / remainder_rel, rgb, remainder)
    (output_path / reference_rel).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, "RGB").save(output_path / reference_rel)

    manifest_layers: list[dict[str, Any]] = [
        {
            "id": "background",
            "name": str(background_spec.get("name") or "背景"),
            "group": "04_背景",
            "type": "pixel",
            "source": background_rel.as_posix(),
            "visible": True,
            "locked": False,
            "z_index": 10,
        },
        {
            "id": "remainder",
            "name": str(spec.get("remainder_name") or "其他未分配前景"),
            "group": "04_背景",
            "type": "pixel",
            "source": remainder_rel.as_posix(),
            "visible": True,
            "locked": False,
            "z_index": 20,
        },
    ]
    for index, (name, mask) in enumerate(zip(names, masks), start=1):
        subject_rel = Path(f"layers/02_subjects/subject_{index:02d}.png")
        save_rgba(Image, np, output_path / subject_rel, rgb, mask)
        manifest_layers.append(
            {
                "id": f"subject_{index:02d}",
                "name": name,
                "group": "02_主体",
                "type": "pixel",
                "source": subject_rel.as_posix(),
                "visible": True,
                "locked": False,
                "z_index": 30 + index,
            }
        )
    manifest_layers.append(
        {
            "id": "original_reference",
            "name": "原图参考_锁定_默认隐藏",
            "group": "00_原始参考",
            "type": "pixel",
            "source": reference_rel.as_posix(),
            "visible": False,
            "locked": True,
            "z_index": 90,
        }
    )

    preview_index_rel = Path("preview/layer-index.jpg")
    preview_cutout_rel = Path("preview/cutout-preview.png")
    write_index_preview(
        Image, ImageDraw, ImageFont, np, output_path / preview_index_rel, rgb, masks
    )
    write_cutout_preview(
        Image, ImageDraw, ImageFont, np, output_path / preview_cutout_rel, rgb, masks
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"sha256": file_sha256(input_path)},
        "canvas": {
            "width": int(width),
            "height": int(height),
            "resolution": int(round(float(pil_image.info.get("dpi", (72, 72))[0] or 72))),
            "color_mode": "RGB",
        },
        "groups_bottom_to_top": list(GROUPS_BOTTOM_TO_TOP),
        "layers": manifest_layers,
        "analysis": {"subject_count": len(layers), "box_mode": spec.get("box_mode", "pixels")},
        "quality": {"partition_exact": True, "requires_manual_review": True},
        "pipeline": {"engine": "local_prompted_instance_segmentation"},
    }
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    relative_job = output_path.relative_to(root).as_posix()
    return {
        "ok": True,
        "job_dir": relative_job,
        "manifest": f"{relative_job}/manifest.json",
        "subject_count": len(layers),
        "canvas": [width, height],
        "partition_exact": True,
        "previews": [
            f"{relative_job}/{preview_index_rel.as_posix()}",
            f"{relative_job}/{preview_cutout_rel.as_posix()}",
        ],
        "private_paths_recorded": False,
    }


def main() -> int:
    args = parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        message = str(exc)
        for value in (args.input, args.spec, args.model, args.out_dir, Path.home()):
            try:
                private_path = str(value.expanduser().resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            message = message.replace(private_path, "<LOCAL_PATH>")
            message = message.replace(private_path.replace("\\", "/"), "<LOCAL_PATH>")
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": message},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
