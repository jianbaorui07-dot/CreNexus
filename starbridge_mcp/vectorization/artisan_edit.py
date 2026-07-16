from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

MAX_EDIT_INDEX_BYTES = 2 * 1024 * 1024
SHAPE_ID = re.compile(r"^shape-[0-9]{4,}$")
INTENT_SELECTOR = re.compile(r"^intent:[a-z][a-z-]{0,31}$")
EDIT_REF = re.compile(r"^edit:[0-9a-f]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
INTENT_ORDER = (
    "flow-contour",
    "ornament",
    "detail",
    "micro-detail",
    "unclassified",
    "paint-region",
)
DESIGNER_NAME_PREFIX = {
    "flow-contour": "主轮廓",
    "ornament": "装饰纹",
    "detail": "细节",
    "micro-detail": "微细节",
    "unclassified": "描边",
    "paint-region": "基础块面",
}


class EditIndexError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _selector_rows(objects: list[list[Any]]) -> list[list[Any]]:
    intents = [intent for intent in INTENT_ORDER if any(item[1] == intent for item in objects)]
    intents.extend(sorted({str(item[1]) for item in objects} - set(INTENT_ORDER)))
    return [
        [
            f"intent:{intent}",
            len(members),
            sum(int(item[3]) for item in members),
            sum(int(item[4]) for item in members),
        ]
        for intent in intents
        if (members := [item for item in objects if item[1] == intent])
    ]


def designer_names(shape_intents: list[tuple[str, str]]) -> dict[str, str]:
    counters: dict[str, int] = {}
    names: dict[str, str] = {}
    for shape_id, intent in shape_intents:
        counters[intent] = counters.get(intent, 0) + 1
        prefix = DESIGNER_NAME_PREFIX.get(intent, "矢量对象")
        names[shape_id] = f"{prefix}-{counters[intent]:03d}"
    return names


def build_edit_index(
    *,
    structure_ref: str,
    strategy: str,
    svg_sha256: str,
    objects: list[list[Any]],
    parent_edit_ref: str | None = None,
) -> dict[str, Any]:
    core = {
        "schema_version": 2,
        "structure_ref": structure_ref,
        "strategy": strategy,
        "svg_sha256": svg_sha256,
        "parent_edit_ref": parent_edit_ref,
        "selectors": _selector_rows(objects),
        "objects": objects,
        "edit_reference_format": "<edit_ref> <intent:selector|shape-id> <change>",
    }
    canonical = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return {
        **core,
        "edit_index_sha256": digest,
        "edit_ref": f"edit:{digest[:12]}",
        "local_analysis_only": True,
        "external_ai_calls": 0,
    }


def load_edit_index(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise EditIndexError("invalid_edit_index", "Edit index must be one explicit JSON file.")
    if path.stat().st_size > MAX_EDIT_INDEX_BYTES:
        raise EditIndexError("edit_index_too_large", "Edit index exceeds the local size limit.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EditIndexError("invalid_edit_index", "Edit index is not valid UTF-8 JSON.") from exc
    if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
        raise EditIndexError("unsupported_edit_index", "Edit index schema is not supported.")
    schema_version = int(value["schema_version"])
    objects = value.get("objects")
    selectors = value.get("selectors")
    if not EDIT_REF.fullmatch(str(value.get("edit_ref", ""))) or not isinstance(objects, list):
        raise EditIndexError("invalid_edit_index", "Edit index is missing required records.")
    if not isinstance(selectors, list) or not all(
        isinstance(item, list)
        and len(item) == 4
        and INTENT_SELECTOR.fullmatch(str(item[0]))
        and all(isinstance(number, int) and number >= 0 for number in item[1:])
        for item in selectors
    ):
        raise EditIndexError("invalid_edit_index", "Edit index selectors are invalid.")
    expected_object_length = 6 if schema_version == 2 else 5
    if not all(
        isinstance(item, list)
        and len(item) == expected_object_length
        and SHAPE_ID.fullmatch(str(item[0]))
        and isinstance(item[1], str)
        and isinstance(item[2], list)
        and len(item[2]) == 4
        and all(isinstance(number, int) and number >= 0 for number in item[2])
        and isinstance(item[3], int)
        and item[3] >= 0
        and isinstance(item[4], int)
        and item[4] >= 0
        and (
            schema_version == 1
            or (
                isinstance(item[5], str)
                and 0 < len(item[5]) <= 64
                and all(character.isalnum() or character in " -_" for character in item[5])
            )
        )
        for item in objects
    ):
        raise EditIndexError("invalid_edit_index", "Edit index object records are invalid.")
    if len({item[0] for item in objects}) != len(objects):
        raise EditIndexError("invalid_edit_index", "Edit index shape IDs must be unique.")
    core_keys = [
        "schema_version",
        "structure_ref",
        "strategy",
        "selectors",
        "objects",
        "edit_reference_format",
    ]
    if schema_version == 2:
        core_keys[3:3] = ["svg_sha256", "parent_edit_ref"]
        if not SHA256.fullmatch(str(value.get("svg_sha256", ""))):
            raise EditIndexError("invalid_edit_index", "Edit index SVG digest is invalid.")
        parent_ref = value.get("parent_edit_ref")
        if parent_ref is not None and not EDIT_REF.fullmatch(str(parent_ref)):
            raise EditIndexError("invalid_edit_index", "Edit index parent reference is invalid.")
    if any(key not in value for key in core_keys):
        raise EditIndexError("invalid_edit_index", "Edit index is missing canonical fields.")
    canonical = json.dumps(
        {key: value[key] for key in core_keys},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    if value.get("edit_index_sha256") != digest or value["edit_ref"] != f"edit:{digest[:12]}":
        raise EditIndexError("edit_index_integrity_failed", "Edit index digest does not match.")
    return value


def _load_index(path_value: str) -> dict[str, Any]:
    return load_edit_index(path_value)


def _bbox_union(objects: list[list[Any]]) -> list[int]:
    boxes = [item[2] for item in objects]
    minimum_x = min(int(box[0]) for box in boxes)
    minimum_y = min(int(box[1]) for box in boxes)
    maximum_x = max(int(box[0]) + int(box[2]) for box in boxes)
    maximum_y = max(int(box[1]) + int(box[3]) for box in boxes)
    return [minimum_x, minimum_y, maximum_x - minimum_x, maximum_y - minimum_y]


def inspect_edit_index(
    path_value: str,
    selector: str,
    *,
    object_limit: int = 24,
) -> dict[str, Any]:
    index = load_edit_index(path_value)
    if INTENT_SELECTOR.fullmatch(selector):
        intent = selector.removeprefix("intent:")
        objects = [item for item in index["objects"] if item[1] == intent]
    elif SHAPE_ID.fullmatch(selector):
        objects = [item for item in index["objects"] if item[0] == selector]
    else:
        raise EditIndexError(
            "invalid_selector", "Selector must be intent:<name> or one stable shape ID."
        )
    if not objects:
        raise EditIndexError("selector_not_found", "Selector did not match an indexed object.")
    limit = max(1, min(100, object_limit))
    object_ids = [str(item[0]) for item in objects]
    designer_names = [str(item[5]) for item in objects if len(item) >= 6]
    return {
        "ok": True,
        "edit_ref": index["edit_ref"],
        "selector": selector,
        "object_count": len(objects),
        "anchors": sum(int(item[3]) for item in objects),
        "subpaths": sum(int(item[4]) for item in objects),
        "bbox": _bbox_union(objects),
        "object_ids": object_ids[:limit],
        "designer_names": designer_names[:limit],
        "object_ids_truncated": len(object_ids) > limit,
        "edit_prompt": f"{index['edit_ref']} {selector} <change>",
        "external_ai_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect one local Artisan compact edit scope.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--selector", required=True)
    parser.add_argument("--object-limit", type=int, default=24)
    try:
        args = parser.parse_args(argv)
        result = inspect_edit_index(
            args.index,
            args.selector,
            object_limit=args.object_limit,
        )
    except EditIndexError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
