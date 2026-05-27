from __future__ import annotations

import copy
from typing import Any


SUPPORTED_UNITS = {"mm", "cm", "m", "inch"}
SUPPORTED_ENTITY_TYPES = {"line", "polyline", "circle", "rectangle", "text"}
DEFAULT_LAYERS = [
    {"name": "OUTLINE", "color": 7},
    {"name": "AUX", "color": 8},
    {"name": "TEXT", "color": 2},
]


def _point2(value: Any, field: str) -> tuple[list[float] | None, str | None]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None, f"{field} must be [x, y]"
    try:
        return [float(value[0]), float(value[1])], None
    except (TypeError, ValueError):
        return None, f"{field} must contain numeric x/y values"


def _positive_number(value: Any, field: str) -> tuple[float | None, str | None]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{field} must be a number"
    if number <= 0:
        return None, f"{field} must be greater than 0"
    return number, None


def normalize_layer(layer: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(layer, dict):
        return None, [f"layers[{index}] must be an object"]
    name = str(layer.get("name", "")).strip()
    if not name:
        errors.append(f"layers[{index}].name is required")
    color = layer.get("color", 7)
    try:
        color = max(1, min(int(color), 255))
    except (TypeError, ValueError):
        errors.append(f"layers[{index}].color must be an integer")
        color = 7
    if errors:
        return None, errors
    return {"name": name, "color": color}, []


def normalize_entity(entity: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(entity, dict):
        return None, [f"entities[{index}] must be an object"]

    entity_type = str(entity.get("type", "")).strip().lower()
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        return None, [f"entities[{index}].type '{entity_type}' is not supported"]

    normalized = copy.deepcopy(entity)
    normalized["type"] = entity_type
    normalized["layer"] = str(entity.get("layer", "0")).strip() or "0"

    if entity_type == "line":
        for field in ("start", "end"):
            point, error = _point2(entity.get(field), f"entities[{index}].{field}")
            if error:
                errors.append(error)
            else:
                normalized[field] = point
    elif entity_type == "polyline":
        points = entity.get("points")
        if not isinstance(points, list) or len(points) < 2:
            errors.append(f"entities[{index}].points must contain at least 2 points")
        else:
            normalized_points = []
            for point_index, raw_point in enumerate(points):
                point, error = _point2(raw_point, f"entities[{index}].points[{point_index}]")
                if error:
                    errors.append(error)
                else:
                    normalized_points.append(point)
            normalized["points"] = normalized_points
        normalized["closed"] = bool(entity.get("closed", False))
    elif entity_type == "circle":
        point, error = _point2(entity.get("center"), f"entities[{index}].center")
        if error:
            errors.append(error)
        else:
            normalized["center"] = point
        radius, error = _positive_number(entity.get("radius"), f"entities[{index}].radius")
        if error:
            errors.append(error)
        else:
            normalized["radius"] = radius
    elif entity_type == "rectangle":
        for field in ("x", "y"):
            try:
                normalized[field] = float(entity.get(field))
            except (TypeError, ValueError):
                errors.append(f"entities[{index}].{field} must be a number")
        for field in ("width", "height"):
            number, error = _positive_number(entity.get(field), f"entities[{index}].{field}")
            if error:
                errors.append(error)
            else:
                normalized[field] = number
    elif entity_type == "text":
        position, error = _point2(entity.get("position"), f"entities[{index}].position")
        if error:
            errors.append(error)
        else:
            normalized["position"] = position
        normalized["value"] = str(entity.get("value", ""))
        height, error = _positive_number(entity.get("height", 180), f"entities[{index}].height")
        if error:
            errors.append(error)
        else:
            normalized["height"] = height

    if errors:
        return None, errors
    return normalized, []


def normalize_plan(plan: Any) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return {}, ["plan must be an object"], []
    if not plan:
        return {}, ["plan must not be empty"], []

    normalized = copy.deepcopy(plan)
    units = str(plan.get("units", "")).strip().lower()
    if not units:
        errors.append("units is required")
        units = "mm"
    elif units not in SUPPORTED_UNITS:
        warnings.append(f"units '{units}' is not explicitly supported; using mm")
        units = "mm"
    normalized["units"] = units

    raw_layers = plan.get("layers", DEFAULT_LAYERS)
    if not isinstance(raw_layers, list):
        errors.append("layers must be a list")
        raw_layers = DEFAULT_LAYERS
    layers: list[dict[str, Any]] = []
    seen_layers: set[str] = set()
    for index, layer in enumerate(raw_layers):
        normalized_layer, layer_errors = normalize_layer(layer, index)
        if layer_errors:
            errors.extend(layer_errors)
            continue
        assert normalized_layer is not None
        if normalized_layer["name"] in seen_layers:
            warnings.append(f"duplicate layer '{normalized_layer['name']}' ignored")
            continue
        seen_layers.add(normalized_layer["name"])
        layers.append(normalized_layer)
    if "0" not in seen_layers:
        layers.insert(0, {"name": "0", "color": 7})
        seen_layers.add("0")
    normalized["layers"] = layers

    raw_entities = plan.get("entities")
    if raw_entities is None:
        errors.append("entities is required")
        raw_entities = []
    elif not isinstance(raw_entities, list):
        errors.append("entities must be a list")
        raw_entities = []
    elif not raw_entities:
        warnings.append("entities is empty")

    entities: list[dict[str, Any]] = []
    for index, entity in enumerate(raw_entities):
        normalized_entity, entity_errors = normalize_entity(entity, index)
        if entity_errors:
            errors.extend(entity_errors)
            continue
        assert normalized_entity is not None
        layer_name = normalized_entity.get("layer", "0")
        if layer_name not in seen_layers:
            warnings.append(f"layer '{layer_name}' was not declared; adding it")
            seen_layers.add(layer_name)
            layers.append({"name": layer_name, "color": 7})
        entities.append(normalized_entity)
    normalized["entities"] = entities

    output = plan.get("output")
    if output is None:
        warnings.append("output is not set; write_dxf requires an explicit output_path")
    elif not isinstance(output, str):
        errors.append("output must be a string when provided")
    else:
        normalized["output"] = output

    return normalized, errors, warnings
