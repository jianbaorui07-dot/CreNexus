from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .artisan_edit import EDIT_REF, SHAPE_ID

MAX_DIRECTION_BYTES = 64 * 1024
MAX_PALETTE_GROUPS = 32
MAX_PALETTE_SOURCES = 128
MAX_OBJECT_NAMES = 128
STYLE_REF = re.compile(r"^style:[0-9a-f]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DIRECTION_REF = re.compile(r"^direction:[0-9a-f]{12}$")
MAP_REF = re.compile(r"^imap:[0-9a-f]{12}$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
LAYER_ROLES = ("foundation", "subject", "detail", "accent")


class ArtisanDirectionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _valid_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 64
        and all(character.isalnum() or character in " -_" for character in value)
    )


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compile_art_direction(spec_value: Any) -> dict[str, Any]:
    """Compile explicit client art direction into a compact immutable contract."""
    required = {
        "base_edit_ref",
        "profile_ref",
        "palette_groups",
        "object_names",
        "layer_names",
    }
    if not isinstance(spec_value, dict) or set(spec_value) != required:
        raise ArtisanDirectionError(
            "invalid_direction_spec",
            "Direction must contain edit/profile refs, palette groups, object names, and layer names.",
        )
    base_edit_ref = spec_value["base_edit_ref"]
    profile_ref = spec_value["profile_ref"]
    if not EDIT_REF.fullmatch(str(base_edit_ref)) or not STYLE_REF.fullmatch(str(profile_ref)):
        raise ArtisanDirectionError(
            "invalid_direction_binding", "Direction refs are missing or invalid."
        )

    palette_value = spec_value["palette_groups"]
    if not isinstance(palette_value, list) or len(palette_value) > MAX_PALETTE_GROUPS:
        raise ArtisanDirectionError(
            "invalid_palette_groups", "Palette groups exceed the compact direction limit."
        )
    palette_groups: list[list[Any]] = []
    used_sources: set[str] = set()
    for row in palette_value:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not HEX_COLOR.fullmatch(str(row[0]))
            or not isinstance(row[1], list)
            or not 1 <= len(row[1]) <= 16
        ):
            raise ArtisanDirectionError(
                "invalid_palette_groups", "Each palette group must contain one target and sources."
            )
        target = str(row[0]).lower()
        sources = [str(source).lower() for source in row[1]]
        if (
            any(not HEX_COLOR.fullmatch(source) for source in sources)
            or len(set(sources)) != len(sources)
            or used_sources.intersection(sources)
        ):
            raise ArtisanDirectionError(
                "invalid_palette_groups", "Palette sources must be valid and belong to one group."
            )
        used_sources.update(sources)
        palette_groups.append([target, sources])
    if len(used_sources) > MAX_PALETTE_SOURCES:
        raise ArtisanDirectionError(
            "invalid_palette_groups", "Palette sources exceed the compact direction limit."
        )

    object_value = spec_value["object_names"]
    if not isinstance(object_value, list) or len(object_value) > MAX_OBJECT_NAMES:
        raise ArtisanDirectionError(
            "invalid_object_names", "Object names exceed the compact direction limit."
        )
    object_names: list[list[str]] = []
    object_ids: set[str] = set()
    for row in object_value:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not SHAPE_ID.fullmatch(str(row[0]))
            or not _valid_name(row[1])
            or str(row[0]) in object_ids
        ):
            raise ArtisanDirectionError(
                "invalid_object_names", "Object names must use unique stable shape IDs."
            )
        object_ids.add(str(row[0]))
        object_names.append([str(row[0]), str(row[1])])

    layer_value = spec_value["layer_names"]
    if not isinstance(layer_value, list) or len(layer_value) > len(LAYER_ROLES):
        raise ArtisanDirectionError(
            "invalid_layer_names", "Layer names exceed the supported design layers."
        )
    layer_names: list[list[str]] = []
    layer_roles: set[str] = set()
    for row in layer_value:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or row[0] not in LAYER_ROLES
            or not _valid_name(row[1])
            or str(row[0]) in layer_roles
        ):
            raise ArtisanDirectionError(
                "invalid_layer_names", "Layer names must use unique supported roles."
            )
        layer_roles.add(str(row[0]))
        layer_names.append([str(row[0]), str(row[1])])
    if not palette_groups and not object_names and not layer_names:
        raise ArtisanDirectionError(
            "empty_direction", "Direction must contain at least one explicit client decision."
        )

    core = {
        "schema_version": 1,
        "base_edit_ref": str(base_edit_ref),
        "profile_ref": str(profile_ref),
        "palette_groups": palette_groups,
        "object_names": object_names,
        "layer_names": layer_names,
        "client_explicit": True,
        "local_analysis_only": True,
        "external_ai_calls": 0,
    }
    digest = hashlib.sha256(_canonical(core)).hexdigest()
    return {
        **core,
        "direction_sha256": digest,
        "direction_ref": f"direction:{digest[:12]}",
    }


def load_art_direction(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanDirectionError(
            "invalid_art_direction", "Art direction must be one explicit JSON file."
        )
    if path.stat().st_size > MAX_DIRECTION_BYTES:
        raise ArtisanDirectionError(
            "art_direction_too_large", "Art direction exceeds the local size limit."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanDirectionError(
            "invalid_art_direction", "Art direction is not valid UTF-8 JSON."
        ) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ArtisanDirectionError(
            "unsupported_art_direction", "Art direction schema is not supported."
        )
    expected = compile_art_direction(
        {
            "base_edit_ref": value.get("base_edit_ref"),
            "profile_ref": value.get("profile_ref"),
            "palette_groups": value.get("palette_groups"),
            "object_names": value.get("object_names"),
            "layer_names": value.get("layer_names"),
        }
    )
    if value != expected:
        raise ArtisanDirectionError(
            "art_direction_integrity_failed", "Art direction digest or content does not match."
        )
    return value


def palette_mapping(direction: dict[str, Any]) -> dict[str, str]:
    return {source: target for target, sources in direction["palette_groups"] for source in sources}


def build_illustrator_map(
    *,
    direction_ref: str,
    svg_sha256: str,
    edit_ref: str,
    layer_names: list[list[str]],
    object_names: list[list[str]],
) -> dict[str, Any]:
    if (
        not DIRECTION_REF.fullmatch(direction_ref)
        or not SHA256.fullmatch(svg_sha256)
        or not EDIT_REF.fullmatch(edit_ref)
    ):
        raise ArtisanDirectionError(
            "invalid_illustrator_map_binding", "Illustrator map refs are invalid."
        )
    if not all(
        isinstance(row, list)
        and len(row) == 2
        and row[0] in {f"layer-{role}" for role in LAYER_ROLES}
        and _valid_name(row[1])
        for row in layer_names
    ) or len({row[0] for row in layer_names}) != len(layer_names):
        raise ArtisanDirectionError(
            "invalid_illustrator_layer_map", "Illustrator layer mappings are invalid."
        )
    if not all(
        isinstance(row, list)
        and len(row) == 2
        and SHAPE_ID.fullmatch(str(row[0]))
        and _valid_name(row[1])
        for row in object_names
    ) or len({row[0] for row in object_names}) != len(object_names):
        raise ArtisanDirectionError(
            "invalid_illustrator_object_map", "Illustrator object mappings are invalid."
        )
    core = {
        "schema_version": 1,
        "svg_sha256": svg_sha256,
        "edit_ref": edit_ref,
        "direction_ref": direction_ref,
        "layers": layer_names,
        "objects": object_names,
        "requires_user_confirmed_illustrator_write": True,
        "local_analysis_only": True,
        "external_ai_calls": 0,
    }
    digest = hashlib.sha256(_canonical(core)).hexdigest()
    return {**core, "map_sha256": digest, "map_ref": f"imap:{digest[:12]}"}


def load_illustrator_map(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanDirectionError(
            "invalid_illustrator_map", "Illustrator map must be one explicit JSON file."
        )
    if path.stat().st_size > MAX_DIRECTION_BYTES:
        raise ArtisanDirectionError(
            "illustrator_map_too_large", "Illustrator map exceeds the local size limit."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanDirectionError(
            "invalid_illustrator_map", "Illustrator map is not valid UTF-8 JSON."
        ) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ArtisanDirectionError(
            "unsupported_illustrator_map", "Illustrator map schema is not supported."
        )
    expected = build_illustrator_map(
        direction_ref=str(value.get("direction_ref", "")),
        svg_sha256=str(value.get("svg_sha256", "")),
        edit_ref=str(value.get("edit_ref", "")),
        layer_names=value.get("layers") if isinstance(value.get("layers"), list) else [],
        object_names=value.get("objects") if isinstance(value.get("objects"), list) else [],
    )
    if value != expected or not MAP_REF.fullmatch(str(value.get("map_ref", ""))):
        raise ArtisanDirectionError(
            "illustrator_map_integrity_failed", "Illustrator map digest or content does not match."
        )
    return value


def _load_spec(path_value: str) -> Any:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanDirectionError("invalid_direction_spec", "Spec must be one JSON file.")
    if path.stat().st_size > MAX_DIRECTION_BYTES:
        raise ArtisanDirectionError("direction_spec_too_large", "Spec exceeds the local limit.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanDirectionError(
            "invalid_direction_spec", "Spec is not valid UTF-8 JSON."
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile compact explicit Artisan art direction.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    try:
        args = parser.parse_args(argv)
        direction = compile_art_direction(_load_spec(args.spec))
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(direction, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        result = {
            "ok": True,
            "direction_ref": direction["direction_ref"],
            "direction_sha256": direction["direction_sha256"],
            "external_ai_calls": 0,
        }
    except ArtisanDirectionError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
