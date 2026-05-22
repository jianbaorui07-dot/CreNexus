import argparse
import math
import pathlib
import time
from collections import defaultdict

import cv2
import numpy as np
import pythoncom
import win32com.client


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
IMAGE_PATH: pathlib.Path | None = None
OUTPUT = WORKSPACE / "output" / "girl_rose_reference_vector.dwg"
PREVIEW = WORKSPACE / "output" / "girl_rose_reference_vector_preview.png"


ROI = {
    "x0": 300,
    "y0": 75,
    "x1": 1210,
    "y1": 760,
}
CAD_WIDTH = 220.0


def vt_doubles(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


def connect_autocad():
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")
        app.Visible = True
        time.sleep(8)

    app.Visible = True
    try:
        doc = app.ActiveDocument
    except Exception:
        doc = app.Documents.Add()
        time.sleep(2)
    return app, doc, doc.ModelSpace


def clear_modelspace(model):
    for index in range(model.Count - 1, -1, -1):
        try:
            model.Item(index).Delete()
        except Exception:
            pass


def ensure_layer(doc, name, color):
    try:
        layer = doc.Layers.Item(name)
    except Exception:
        layer = doc.Layers.Add(name)
    layer.Color = color
    return layer


def add_polyline(model, points, layer, color, lineweight=25):
    if len(points) < 2:
        return None
    coords = []
    for x, y in points:
        coords.extend([x, y])
    entity = model.AddLightWeightPolyline(vt_doubles(coords))
    entity.Layer = layer
    entity.Color = color
    try:
        entity.LineWeight = lineweight
    except Exception:
        pass
    return entity


def filter_components(mask, min_area, remove_bottom_bar=False):
    mask_u8 = (mask.astype(np.uint8) * 255)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, 8)
    keep = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape

    for label in range(1, count):
        x, y, bw, bh, area = stats[label]
        if area < min_area:
            continue
        if remove_bottom_bar and y > h - 45 and bw > w * 0.35 and bh < 35:
            continue
        if bw > w * 0.45 and bh < 4:
            continue
        keep[labels == label] = True
    return keep


def remove_bottom_horizontal_runs(mask):
    clean = mask.copy()
    h, w = clean.shape
    for y in range(max(0, h - 105), h):
        row = clean[y]
        x = 0
        while x < w:
            if not row[x]:
                x += 1
                continue
            start = x
            while x < w and row[x]:
                x += 1
            end = x
            if end - start > 120:
                y0 = max(0, y - 4)
                y1 = min(h, y + 5)
                clean[y0:y1, start:end] = False
    return clean


def zhang_suen_thin(binary):
    img = binary.astype(np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p2 = img[:-2, 1:-1]
            p3 = img[:-2, 2:]
            p4 = img[1:-1, 2:]
            p5 = img[2:, 2:]
            p6 = img[2:, 1:-1]
            p7 = img[2:, :-2]
            p8 = img[1:-1, :-2]
            p9 = img[:-2, :-2]
            p1 = img[1:-1, 1:-1]

            neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
            transitions = sum(((neighbors[i] == 0) & (neighbors[(i + 1) % 8] == 1)) for i in range(8))
            neighbor_count = sum(neighbors)

            if step == 0:
                marker = (
                    (p1 == 1)
                    & (neighbor_count >= 2)
                    & (neighbor_count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p6) == 0)
                    & ((p4 * p6 * p8) == 0)
                )
            else:
                marker = (
                    (p1 == 1)
                    & (neighbor_count >= 2)
                    & (neighbor_count <= 6)
                    & (transitions == 1)
                    & ((p2 * p4 * p8) == 0)
                    & ((p2 * p6 * p8) == 0)
                )

            if marker.any():
                img[1:-1, 1:-1][marker] = 0
                changed = True
    return img.astype(bool)


NEIGHBOR_OFFSETS = [
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
]


def skeleton_to_paths(skeleton, min_pixels=8):
    ys, xs = np.nonzero(skeleton)
    pixels = set(zip(xs.tolist(), ys.tolist()))
    if not pixels:
        return []

    def neighbors(pixel):
        x, y = pixel
        result = []
        for dx, dy in NEIGHBOR_OFFSETS:
            candidate = (x + dx, y + dy)
            if candidate in pixels:
                result.append(candidate)
        return result

    degree = {pixel: len(neighbors(pixel)) for pixel in pixels}
    nodes = {pixel for pixel, deg in degree.items() if deg != 2}
    visited_edges = set()
    paths = []

    def edge_key(a, b):
        return tuple(sorted((a, b)))

    def trace(start, nxt):
        path = [start, nxt]
        visited_edges.add(edge_key(start, nxt))
        prev, cur = start, nxt
        while cur not in nodes:
            options = [p for p in neighbors(cur) if p != prev]
            if not options:
                break
            next_pixel = None
            for candidate in options:
                if edge_key(cur, candidate) not in visited_edges:
                    next_pixel = candidate
                    break
            if next_pixel is None:
                break
            visited_edges.add(edge_key(cur, next_pixel))
            path.append(next_pixel)
            prev, cur = cur, next_pixel
        return path

    for node in nodes:
        for nxt in neighbors(node):
            if edge_key(node, nxt) not in visited_edges:
                path = trace(node, nxt)
                if len(path) >= min_pixels:
                    paths.append(path)

    for pixel in pixels:
        available = [n for n in neighbors(pixel) if edge_key(pixel, n) not in visited_edges]
        if not available:
            continue
        path = [pixel]
        prev = pixel
        cur = available[0]
        visited_edges.add(edge_key(prev, cur))
        while True:
            path.append(cur)
            options = [n for n in neighbors(cur) if n != prev and edge_key(cur, n) not in visited_edges]
            if not options:
                break
            nxt = options[0]
            visited_edges.add(edge_key(cur, nxt))
            prev, cur = cur, nxt
            if cur == pixel:
                path.append(cur)
                break
        if len(path) >= min_pixels:
            paths.append(path)

    return paths


def simplify_path(path, epsilon=1.6):
    arr = np.array(path, dtype=np.float32).reshape((-1, 1, 2))
    simplified = cv2.approxPolyDP(arr, epsilon, False).reshape((-1, 2))
    return [(float(x), float(y)) for x, y in simplified]


def pixel_to_cad(points, roi_width, roi_height):
    scale = CAD_WIDTH / roi_width
    return [(x * scale, (roi_height - y) * scale) for x, y in points]


def build_masks():
    if IMAGE_PATH is None:
        raise ValueError("Set IMAGE_PATH through the --image argument.")
    image = cv2.imread(str(IMAGE_PATH))
    if image is None:
        raise FileNotFoundError(IMAGE_PATH)

    roi = image[ROI["y0"] : ROI["y1"], ROI["x0"] : ROI["x1"]]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    red = (((hsv[:, :, 0] < 8) | (hsv[:, :, 0] > 168)) & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90))
    green = ((hsv[:, :, 0] > 38) & (hsv[:, :, 0] < 80) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 90))
    white = ((hsv[:, :, 1] < 75) & (hsv[:, :, 2] > 155))
    white[:20, :] = False

    masks = {}
    for name, mask in {"red": red, "green": green, "white": white}.items():
        mask = cv2.medianBlur(mask.astype(np.uint8) * 255, 3) > 0
        mask = filter_components(mask, 16 if name != "white" else 20, remove_bottom_bar=(name == "white"))
        if name == "white":
            mask = remove_bottom_horizontal_runs(mask)
        masks[name] = mask

    # Remove any red/green pixels from the white layer so the hand and flower stay on distinct layers.
    masks["white"] = masks["white"] & ~masks["red"] & ~masks["green"]

    preview = np.zeros_like(roi)
    preview[masks["white"]] = (255, 255, 255)
    preview[masks["green"]] = (0, 255, 0)
    preview[masks["red"]] = (0, 0, 255)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(PREVIEW), preview)
    return masks, roi.shape[1], roi.shape[0]


def vectorize_masks(masks, roi_width, roi_height):
    result = defaultdict(list)
    for name, mask in masks.items():
        skeleton = zhang_suen_thin(mask)
        paths = skeleton_to_paths(skeleton, min_pixels=10 if name == "white" else 8)
        for path in paths:
            xs = [p[0] for p in path]
            ys = [p[1] for p in path]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            if name == "white" and min(ys) > roi_height - 105 and width > 110 and height < 14:
                continue
            simplified = simplify_path(path, epsilon=1.5 if name == "white" else 1.2)
            if len(simplified) < 2:
                continue
            result[name].append(pixel_to_cad(simplified, roi_width, roi_height))
    return result


def draw():
    masks, roi_width, roi_height = build_masks()
    paths = vectorize_masks(masks, roi_width, roi_height)

    app, doc, model = connect_autocad()
    clear_modelspace(model)

    ensure_layer(doc, "GIRL_WHITE_TRACE", 7)
    ensure_layer(doc, "ROSE_RED_TRACE", 1)
    ensure_layer(doc, "STEM_LEAF_GREEN_TRACE", 3)

    layer_info = {
        "white": ("GIRL_WHITE_TRACE", 7, 18),
        "red": ("ROSE_RED_TRACE", 1, 18),
        "green": ("STEM_LEAF_GREEN_TRACE", 3, 18),
    }

    entity_count = 0
    for name in ("green", "red", "white"):
        layer, color, weight = layer_info[name]
        for path in paths[name]:
            add_polyline(model, path, layer, color, weight)
            entity_count += 1

    try:
        app.ZoomExtents()
    except Exception:
        doc.SendCommand("_.ZOOM _E ")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        if OUTPUT.exists() and doc.FullName.lower() != str(OUTPUT).lower():
            OUTPUT.unlink()
    except Exception:
        pass
    doc.SaveAs(str(OUTPUT))
    return doc.Name, OUTPUT, PREVIEW, entity_count, {key: len(value) for key, value in paths.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trace a local reference image into AutoCAD polylines.")
    parser.add_argument("--image", required=True, help="Local reference image path. The path is not stored in Git.")
    args = parser.parse_args()
    IMAGE_PATH = pathlib.Path(args.image)
    doc_name, output, preview, entity_count, path_counts = draw()
    print(f"active_document={doc_name}")
    print(f"output={output}")
    print(f"preview={preview}")
    print(f"entity_count={entity_count}")
    print(f"path_counts={path_counts}")
