from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .svg_verify import SvgArtifactError, verify_svg_artifact

RENDERER_VERSION = "starbridge-path-renderer-v2"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
PATH_LEXEME = re.compile(rf"[MmLlCcZz]|{NUMBER}")
HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6})\Z")


class SvgRenderError(ValueError):
    pass


def _number(value: str | None, *, label: str) -> float:
    if value is None:
        raise SvgRenderError(f"SVG {label} is missing.")
    match = re.match(NUMBER, value.strip())
    if match is None:
        raise SvgRenderError(f"SVG {label} is not numeric.")
    result = float(match.group(0))
    if not math.isfinite(result) or result <= 0:
        raise SvgRenderError(f"SVG {label} must be positive.")
    return result


def _color(value: str | None) -> tuple[int, int, int] | None:
    if value in {None, "none"}:
        return None
    match = HEX_COLOR.fullmatch(value)
    if match is None:
        raise SvgRenderError("The local renderer accepts only six-digit hexadecimal paints.")
    packed = match.group(1)
    return tuple(int(packed[index : index + 2], 16) for index in (0, 2, 4))


def _opacity(value: str | None) -> float:
    if value is None:
        return 1.0
    try:
        result = float(value)
    except ValueError as exc:
        raise SvgRenderError("SVG opacity is not numeric.") from exc
    return min(1.0, max(0.0, result))


def _cubic(
    start: tuple[float, float],
    control_1: tuple[float, float],
    control_2: tuple[float, float],
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    control_length = (
        math.dist(start, control_1) + math.dist(control_1, control_2) + math.dist(control_2, end)
    )
    samples = min(48, max(6, math.ceil(control_length / 4.0)))
    points: list[tuple[float, float]] = []
    for index in range(1, samples + 1):
        t = index / samples
        inverse = 1.0 - t
        points.append(
            (
                inverse**3 * start[0]
                + 3 * inverse**2 * t * control_1[0]
                + 3 * inverse * t**2 * control_2[0]
                + t**3 * end[0],
                inverse**3 * start[1]
                + 3 * inverse**2 * t * control_1[1]
                + 3 * inverse * t**2 * control_2[1]
                + t**3 * end[1],
            )
        )
    return points


def _parse_path(value: str) -> list[tuple[list[tuple[float, float]], bool]]:
    lexemes = PATH_LEXEME.findall(value.replace(",", " "))
    paths: list[tuple[list[tuple[float, float]], bool]] = []
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    start = current
    command: str | None = None
    index = 0

    def coordinate(offset: int) -> float:
        try:
            return float(lexemes[index + offset])
        except (IndexError, ValueError) as exc:
            raise SvgRenderError("SVG path data is incomplete.") from exc

    while index < len(lexemes):
        lexeme = lexemes[index]
        if lexeme.isalpha():
            command = lexeme
            index += 1
            if command in {"Z", "z"}:
                if points:
                    paths.append((points, True))
                points = []
                current = start
                command = None
            continue
        if command is None:
            raise SvgRenderError("SVG path data has coordinates without a command.")
        relative = command.islower()
        upper = command.upper()
        if upper in {"M", "L"}:
            x, y = coordinate(0), coordinate(1)
            index += 2
            if relative:
                x += current[0]
                y += current[1]
            current = (x, y)
            if upper == "M":
                if points:
                    paths.append((points, False))
                points = [current]
                start = current
                command = "l" if relative else "L"
            else:
                points.append(current)
        elif upper == "C":
            values = [coordinate(offset) for offset in range(6)]
            index += 6
            control_1 = (values[0], values[1])
            control_2 = (values[2], values[3])
            end = (values[4], values[5])
            if relative:
                control_1 = (control_1[0] + current[0], control_1[1] + current[1])
                control_2 = (control_2[0] + current[0], control_2[1] + current[1])
                end = (end[0] + current[0], end[1] + current[1])
            points.extend(_cubic(current, control_1, control_2, end))
            current = end
        else:
            raise SvgRenderError(f"Unsupported SVG path command: {command}")
    if points:
        paths.append((points, False))
    return paths


def _points(
    value: list[tuple[float, float]], scale_x: float, scale_y: float
) -> np.ndarray[Any, Any]:
    array = np.asarray(value, dtype=np.float32)
    array[:, 0] *= scale_x
    array[:, 1] *= scale_y
    return np.rint(array).astype(np.int32).reshape((-1, 1, 2))


def _composite(canvas: np.ndarray[Any, Any], color: tuple[int, int, int], mask: Any) -> None:
    alpha = np.asarray(mask, dtype=np.float32)[:, :, None] / 255.0
    source = np.empty_like(canvas)
    source[:, :, :3] = color
    source[:, :, 3] = 255.0
    canvas[:] = source * alpha + canvas * (1.0 - alpha)


def render_verified_svg(
    svg_path: Path,
    output_path: Path,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
    supersample: int = 2,
    output_width: int | None = None,
    output_height: int | None = None,
) -> dict[str, Any]:
    """Render StarBridge's verified path-only SVG dialect without external applications."""
    if supersample not in {1, 2, 3, 4}:
        raise SvgRenderError("Supersampling must be between one and four.")
    try:
        evidence = verify_svg_artifact(
            svg_path,
            expected_width=expected_width,
            expected_height=expected_height,
        )
    except SvgArtifactError as exc:
        raise SvgRenderError(str(exc)) from exc
    try:
        root = ET.parse(svg_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise SvgRenderError("SVG could not be parsed for local rendering.") from exc
    width = round(_number(root.get("width"), label="width"))
    height = round(_number(root.get("height"), label="height"))
    target_width = output_width or width
    target_height = output_height or height
    if target_width <= 0 or target_height <= 0:
        raise SvgRenderError("Output dimensions must be positive.")
    root_ratio = width / height
    output_ratio = target_width / target_height
    if abs(root_ratio - output_ratio) / root_ratio > 0.005:
        raise SvgRenderError("Output dimensions must preserve the SVG aspect ratio.")
    scale_x = target_width / width * supersample
    scale_y = target_height / height * supersample
    scaled_width = target_width * supersample
    scaled_height = target_height * supersample
    canvas = np.zeros((scaled_height, scaled_width, 4), dtype=np.float32)

    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "path":
            continue
        path_data = element.get("d")
        if not path_data:
            continue
        subpaths = _parse_path(path_data)
        fill = _color(element.get("fill"))
        stroke = _color(element.get("stroke"))
        if fill is not None:
            fill_mask = np.zeros((scaled_height, scaled_width), dtype=np.uint8)
            for path_points, closed in subpaths:
                if not closed or len(path_points) < 3:
                    continue
                contour_mask = np.zeros_like(fill_mask)
                cv2.fillPoly(contour_mask, [_points(path_points, scale_x, scale_y)], 255)
                fill_mask = cv2.bitwise_xor(fill_mask, contour_mask)
            paint_alpha = _opacity(element.get("fill-opacity"))
            if paint_alpha < 1.0:
                fill_mask = np.rint(fill_mask.astype(np.float32) * paint_alpha).astype(np.uint8)
            _composite(canvas, fill, fill_mask)
        if stroke is not None:
            stroke_mask = np.zeros((scaled_height, scaled_width), dtype=np.uint8)
            width_value = float(element.get("stroke-width", "1"))
            thickness = max(1, round(width_value * (scale_x + scale_y) / 2.0))
            for path_points, closed in subpaths:
                if len(path_points) < 2:
                    continue
                cv2.polylines(
                    stroke_mask,
                    [_points(path_points, scale_x, scale_y)],
                    closed,
                    255,
                    thickness,
                    cv2.LINE_AA,
                )
            paint_alpha = _opacity(element.get("stroke-opacity"))
            if paint_alpha < 1.0:
                stroke_mask = np.rint(stroke_mask.astype(np.float32) * paint_alpha).astype(np.uint8)
            _composite(canvas, stroke, stroke_mask)

    if supersample > 1:
        canvas = cv2.resize(canvas, (target_width, target_height), interpolation=cv2.INTER_AREA)
    # The compositor stores premultiplied RGB. PNG uses straight alpha, so restore
    # the paint channels before serialization and keep fully transparent RGB at zero.
    alpha = canvas[:, :, 3:4]
    straight = canvas.copy()
    straight[:, :, :3] = np.divide(
        canvas[:, :, :3] * 255.0,
        alpha,
        out=np.zeros_like(canvas[:, :, :3]),
        where=alpha > 0,
    )
    rgba = np.clip(straight, 0, 255).astype(np.uint8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG")
    return {
        "renderer": RENDERER_VERSION,
        "width": target_width,
        "height": target_height,
        "svg_width": width,
        "svg_height": height,
        "svg_sha256": evidence["sha256"],
        "path_count": evidence["path_count"],
    }
