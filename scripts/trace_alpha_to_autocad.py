"""Trace one transparent raster into a new, visibly rendered AutoCAD drawing."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import pythoncom
import win32com.client


def variant_doubles(values: list[float]):
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(value) for value in values]
    )


def variant_point(x: float, y: float, z: float = 0.0):
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)]
    )


def read_image(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RuntimeError("unable_to_decode_input_image")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    return image


def simplified_contours(mask: np.ndarray, *, external: bool, limit: int) -> list[np.ndarray]:
    mode = cv2.RETR_EXTERNAL if external else cv2.RETR_LIST
    contours, _ = cv2.findContours(mask, mode, cv2.CHAIN_APPROX_NONE)
    contours = sorted(contours, key=lambda value: cv2.arcLength(value, True), reverse=True)
    result: list[np.ndarray] = []
    for contour in contours:
        length = cv2.arcLength(contour, True)
        if length < 18:
            continue
        epsilon = max(0.8, length * (0.0015 if external else 0.0035))
        simplified = cv2.approxPolyDP(contour, epsilon, True)
        if 3 <= len(simplified) <= 900:
            result.append(simplified)
        if len(result) >= limit:
            break
    return result


def extract_paths(image: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    alpha = image[:, :, 3]
    subject = (alpha > 12).astype(np.uint8) * 255
    subject = cv2.morphologyEx(subject, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    silhouette = simplified_contours(subject, external=True, limit=8)

    gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 65, 155)
    edges[subject == 0] = 0
    details = simplified_contours(edges, external=False, limit=320)
    return silhouette, details


def to_cad_points(contour: np.ndarray, width: int, height: int, cad_width: float) -> list[float]:
    scale = cad_width / float(width)
    result: list[float] = []
    for point in contour[:, 0, :]:
        result.extend([float(point[0]) * scale, float(height - point[1]) * scale])
    return result


def unique_output(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("unable_to_allocate_output_name")


def ensure_layer(document, name: str, color: int):
    try:
        layer = document.Layers.Item(name)
    except Exception:
        layer = document.Layers.Add(name)
    layer.Color = color
    return layer


def add_contour(model, contour, width, height, cad_width, layer, color):
    coordinates = to_cad_points(contour, width, height, cad_width)
    entity = model.AddLightWeightPolyline(variant_doubles(coordinates))
    entity.Layer = layer
    entity.Color = color
    entity.Closed = True
    return entity


def connect_new_document():
    pythoncom.CoInitialize()
    try:
        application = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        application = win32com.client.Dispatch("AutoCAD.Application")
        time.sleep(7)
    application.Visible = True
    try:
        application.WindowState = 3
    except Exception:
        pass
    document = application.Documents.Add()
    time.sleep(1)
    return application, document, document.ModelSpace


def draw(image_path: Path, output_path: Path) -> dict[str, object]:
    image = read_image(image_path)
    silhouette, details = extract_paths(image)
    height, width = image.shape[:2]
    cad_width = 240.0

    application, document, model = connect_new_document()
    ensure_layer(document, "CODEX_SILHOUETTE", 5)
    ensure_layer(document, "CODEX_DETAIL", 4)
    document.Utility.Prompt("\n[Codex 20%] 正在建立人物外轮廓图层...\n")

    count = 0
    for contour in silhouette:
        add_contour(model, contour, width, height, cad_width, "CODEX_SILHOUETTE", 5)
        count += 1
    document.Regen(1)
    application.ZoomExtents()
    time.sleep(0.8)

    document.Utility.Prompt("\n[Codex 55%] 正在分批重绘服饰与五官纹样...\n")
    for index, contour in enumerate(details, start=1):
        add_contour(model, contour, width, height, cad_width, "CODEX_DETAIL", 4)
        count += 1
        if index % 24 == 0:
            document.Regen(1)
            application.ZoomExtents()
            time.sleep(0.12)

    model.AddText("CODEX VECTOR REDRAW · 52-7", variant_point(0, -16), 7.0)
    document.Regen(1)
    application.ZoomExtents()
    document.Utility.Prompt("\n[Codex 100%] CAD 人物矢量重绘完成。\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_output = unique_output(output_path)
    document.SaveAs(str(final_output))
    return {
        "ok": True,
        "output": str(final_output),
        "entities": count + 1,
        "silhouette_paths": len(silhouette),
        "detail_paths": len(details),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    result = draw(Path(arguments.image), Path(arguments.output))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
