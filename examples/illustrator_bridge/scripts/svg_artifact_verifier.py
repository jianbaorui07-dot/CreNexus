from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_ALLOWED_ELEMENTS = {"svg", "rect", "path"}
_ALLOWED_ATTRIBUTES = {
    "svg": {"width", "height", "viewBox"},
    "rect": {"width", "height", "fill"},
    "path": {"d", "fill", "fill-opacity", "fill-rule", "stroke"},
}
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_MOVE_COMMAND = re.compile(r"(?:^|[\s,])M(?:[\s,]|$)", re.IGNORECASE)
_NUMBER = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?"
_SUBPATH = rf"M\s+{_NUMBER}\s+{_NUMBER}(?:\s+L\s+{_NUMBER}\s+{_NUMBER}){{2,}}\s+Z"
_COMPOUND_PATH = re.compile(rf"\A{_SUBPATH}(?:\s+{_SUBPATH})*\Z")
_COORDINATE_NUMBER = re.compile(_NUMBER)
_MAX_SVG_BYTES = 64 * 1024 * 1024


class SvgArtifactError(ValueError):
    """Raised when an SVG cannot prove the editable-vector artifact contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _tag_parts(tag: str) -> tuple[str, str]:
    if tag.startswith("{") and "}" in tag:
        namespace, local_name = tag[1:].split("}", 1)
        return namespace, local_name
    return "", tag


def _positive_number(value: str | None, field: str) -> float:
    try:
        number = float(value or "")
    except ValueError as exc:
        raise SvgArtifactError("invalid_dimensions", f"SVG {field} must be numeric.") from exc
    if not math.isfinite(number) or number <= 0:
        raise SvgArtifactError("invalid_dimensions", f"SVG {field} must be positive.")
    return number


def _view_box(value: str | None) -> list[float]:
    parts = re.split(r"[\s,]+", (value or "").strip())
    if len(parts) != 4:
        raise SvgArtifactError("invalid_view_box", "SVG viewBox must contain four numbers.")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise SvgArtifactError("invalid_view_box", "SVG viewBox must be numeric.") from exc
    if not all(math.isfinite(number) for number in numbers) or numbers[2] <= 0 or numbers[3] <= 0:
        raise SvgArtifactError("invalid_view_box", "SVG viewBox extent must be positive.")
    return numbers


def _fill_opacity(value: str | None) -> float:
    if value is None:
        return 1.0
    try:
        opacity = float(value)
    except ValueError as exc:
        raise SvgArtifactError("invalid_fill_opacity", "SVG fill opacity must be numeric.") from exc
    if not math.isfinite(opacity) or opacity < 0 or opacity > 1:
        raise SvgArtifactError("invalid_fill_opacity", "SVG fill opacity must be between 0 and 1.")
    return opacity


def verify_svg_artifact(
    path: Path,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> dict[str, Any]:
    """Fail closed unless *path* is a non-empty, editable, raster-free SVG artifact."""

    if not path.is_file():
        raise SvgArtifactError("artifact_missing", "SVG artifact was not created.")
    payload = path.read_bytes()
    if not payload:
        raise SvgArtifactError("artifact_empty", "SVG artifact is empty.")
    if len(payload) > _MAX_SVG_BYTES:
        raise SvgArtifactError("artifact_too_large", "SVG artifact exceeds the verifier limit.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SvgArtifactError(
            "unsupported_encoding", "SVG artifact must use UTF-8 encoding."
        ) from exc
    if text.startswith("\ufeff") or "\x00" in text:
        raise SvgArtifactError(
            "unsupported_encoding", "SVG artifact must use plain UTF-8 encoding."
        )
    upper_text = text.upper()
    if "<!DOCTYPE" in upper_text or "<!ENTITY" in upper_text:
        raise SvgArtifactError(
            "unsafe_xml_declaration", "SVG contains a forbidden XML declaration."
        )
    if "<?" in text:
        raise SvgArtifactError(
            "unsafe_processing_instruction", "SVG contains a forbidden processing instruction."
        )

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SvgArtifactError("invalid_xml", "SVG artifact is not valid XML.") from exc

    namespace, root_name = _tag_parts(root.tag)
    if namespace != SVG_NAMESPACE or root_name != "svg":
        raise SvgArtifactError("invalid_svg_root", "Artifact root must be an SVG element.")

    width = _positive_number(root.get("width"), "width")
    height = _positive_number(root.get("height"), "height")
    view_box = _view_box(root.get("viewBox"))
    if expected_width is not None and not math.isclose(width, expected_width):
        raise SvgArtifactError("dimension_mismatch", "SVG width does not match the source canvas.")
    if expected_height is not None and not math.isclose(height, expected_height):
        raise SvgArtifactError("dimension_mismatch", "SVG height does not match the source canvas.")
    if not math.isclose(view_box[2], width) or not math.isclose(view_box[3], height):
        raise SvgArtifactError("dimension_mismatch", "SVG viewBox does not match its dimensions.")
    if not math.isclose(view_box[0], 0.0) or not math.isclose(view_box[1], 0.0):
        raise SvgArtifactError("dimension_mismatch", "SVG viewBox origin must be zero.")

    paths: list[ET.Element] = []
    fills: set[str] = set()
    paints: set[tuple[str, float]] = set()
    subpath_count = 0
    for element in root.iter():
        element_namespace, local_name = _tag_parts(element.tag)
        if element_namespace != SVG_NAMESPACE or local_name not in _ALLOWED_ELEMENTS:
            raise SvgArtifactError(
                "unsafe_svg_element",
                "SVG contains an element outside the generated vector contract.",
            )
        for raw_name, raw_value in element.attrib.items():
            attribute_namespace, attribute_name = _tag_parts(raw_name)
            attribute_lower = attribute_name.lower()
            value_lower = raw_value.strip().lower()
            if attribute_lower in {"href", "src"} or attribute_lower.startswith("on"):
                raise SvgArtifactError("external_reference", "SVG contains an external reference.")
            if "url(" in value_lower:
                raise SvgArtifactError("external_reference", "SVG contains a URL reference.")
            if attribute_namespace or attribute_name not in _ALLOWED_ATTRIBUTES[local_name]:
                raise SvgArtifactError(
                    "unsafe_svg_attribute",
                    "SVG contains an attribute outside the generated vector contract.",
                )
        if local_name == "rect":
            rect_width = _positive_number(element.get("width"), "background width")
            rect_height = _positive_number(element.get("height"), "background height")
            if (
                not math.isclose(rect_width, width)
                or not math.isclose(rect_height, height)
                or element.get("fill", "").lower() != "#ffffff"
            ):
                raise SvgArtifactError(
                    "invalid_background", "SVG background must match the verified canvas."
                )
        if local_name != "path":
            continue
        path_data = (element.get("d") or "").strip()
        fill = (element.get("fill") or "").strip()
        if not path_data or not _COMPOUND_PATH.fullmatch(path_data):
            raise SvgArtifactError(
                "invalid_path_data", "SVG path is not a closed generated polygon."
            )
        if not _HEX_COLOR.fullmatch(fill):
            raise SvgArtifactError("invalid_fill", "SVG paths must use explicit RGB fills.")
        opacity = _fill_opacity(element.get("fill-opacity"))
        if element.get("fill-rule") != "evenodd" or element.get("stroke") != "none":
            raise SvgArtifactError(
                "invalid_path_style", "SVG paths must use the generated editable fill contract."
            )
        coordinates = [float(value) for value in _COORDINATE_NUMBER.findall(path_data)]
        if any(
            coordinate < 0 or coordinate > (width if index % 2 == 0 else height)
            for index, coordinate in enumerate(coordinates)
        ):
            raise SvgArtifactError(
                "path_outside_canvas", "SVG path coordinates must stay inside the canvas."
            )
        paths.append(element)
        fills.add(fill.lower())
        paints.add((fill.lower(), opacity))
        subpath_count += len(_MOVE_COMMAND.findall(path_data))

    if not paths:
        raise SvgArtifactError("no_vector_paths", "SVG contains no editable vector paths.")

    return {
        "verified": True,
        "media_type": "image/svg+xml",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "width": width,
        "height": height,
        "view_box": view_box,
        "path_count": len(paths),
        "subpath_count": subpath_count,
        "color_count": len(fills),
        "paint_count": len(paints),
        "embedded_raster_count": 0,
    }
