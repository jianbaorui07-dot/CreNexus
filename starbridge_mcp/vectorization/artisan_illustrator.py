from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .artisan_direction import (
    DIRECTION_REF,
    MAP_REF,
    SHA256,
    ArtisanDirectionError,
    load_art_direction,
    load_illustrator_map,
)
from .artisan_edit import EDIT_REF, EditIndexError, load_edit_index

MAX_APPLY_PLAN_BYTES = 64 * 1024
PLAN_REF = re.compile(r"^apply-plan:[0-9a-f]{12}$")
TRANSACTION_REF = re.compile(r"^apply:[0-9a-f]{12}$")
APPROVAL_REF = re.compile(r"^approve:[0-9a-f]{12}$")
Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class ArtisanIllustratorError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _assemble_plan(
    *,
    svg_sha256: str,
    edit_ref: str,
    direction_ref: str,
    map_ref: str,
    expected_state_revision: int,
    layer_targets: int,
    object_targets: int,
) -> dict[str, Any]:
    if (
        not SHA256.fullmatch(svg_sha256)
        or not EDIT_REF.fullmatch(edit_ref)
        or not DIRECTION_REF.fullmatch(direction_ref)
        or not MAP_REF.fullmatch(map_ref)
    ):
        raise ArtisanIllustratorError(
            "invalid_apply_bindings", "Apply plan contains invalid immutable refs."
        )
    if not 1 <= expected_state_revision <= 2_147_483_647:
        raise ArtisanIllustratorError(
            "invalid_state_revision", "Expected Illustrator state revision must be positive."
        )
    if not 0 <= layer_targets <= 4 or not 0 <= object_targets <= 128:
        raise ArtisanIllustratorError(
            "invalid_apply_targets", "Illustrator naming targets exceed protocol limits."
        )
    if layer_targets + object_targets == 0:
        raise ArtisanIllustratorError(
            "empty_illustrator_map", "Illustrator map does not contain naming work."
        )
    base = {
        "schema_version": 1,
        "svg_sha256": svg_sha256,
        "edit_ref": edit_ref,
        "direction_ref": direction_ref,
        "map_ref": map_ref,
        "expected_state_revision": expected_state_revision,
        "layer_targets": layer_targets,
        "object_targets": object_targets,
        "risk_level": "L2-confirmed-write",
        "requires_confirmation": True,
        "rollback_required_on_readback_failure": True,
        "local_proxy_only": True,
        "external_ai_calls": 0,
    }
    transaction_digest = _sha256(_canonical(base))
    core = {**base, "transaction_ref": f"apply:{transaction_digest[:12]}"}
    digest = _sha256(_canonical(core))
    return {
        **core,
        "plan_sha256": digest,
        "plan_ref": f"apply-plan:{digest[:12]}",
        "approval_ref": f"approve:{digest[:12]}",
    }


def compile_apply_plan(
    *,
    svg_path: str,
    index_path: str,
    direction_path: str,
    map_path: str,
    expected_state_revision: int,
) -> dict[str, Any]:
    svg = Path(svg_path).expanduser()
    if not svg.is_file() or svg.suffix.lower() != ".svg":
        raise ArtisanIllustratorError("invalid_svg", "Apply plan requires one explicit SVG.")
    try:
        index = load_edit_index(index_path)
        direction = load_art_direction(direction_path)
        mapping = load_illustrator_map(map_path)
    except (EditIndexError, ArtisanDirectionError) as exc:
        raise ArtisanIllustratorError(exc.code, str(exc)) from exc
    svg_sha256 = _sha256(svg.read_bytes())
    if (
        index.get("schema_version") != 2
        or index.get("svg_sha256") != svg_sha256
        or mapping["svg_sha256"] != svg_sha256
        or mapping["edit_ref"] != index["edit_ref"]
        or mapping["direction_ref"] != direction["direction_ref"]
    ):
        raise ArtisanIllustratorError(
            "illustrator_apply_binding_mismatch",
            "SVG, edit index, art direction, and Illustrator map are not one bound set.",
        )
    return _assemble_plan(
        svg_sha256=svg_sha256,
        edit_ref=index["edit_ref"],
        direction_ref=direction["direction_ref"],
        map_ref=mapping["map_ref"],
        expected_state_revision=expected_state_revision,
        layer_targets=len(mapping["layers"]),
        object_targets=len(mapping["objects"]),
    )


def load_apply_plan(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanIllustratorError(
            "invalid_apply_plan", "Apply plan must be one explicit JSON file."
        )
    if path.stat().st_size > MAX_APPLY_PLAN_BYTES:
        raise ArtisanIllustratorError(
            "apply_plan_too_large", "Apply plan exceeds the local size limit."
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanIllustratorError(
            "invalid_apply_plan", "Apply plan is not valid UTF-8 JSON."
        ) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ArtisanIllustratorError(
            "unsupported_apply_plan", "Apply plan schema is not supported."
        )
    try:
        expected = _assemble_plan(
            svg_sha256=str(value.get("svg_sha256", "")),
            edit_ref=str(value.get("edit_ref", "")),
            direction_ref=str(value.get("direction_ref", "")),
            map_ref=str(value.get("map_ref", "")),
            expected_state_revision=int(value.get("expected_state_revision", 0)),
            layer_targets=int(value.get("layer_targets", -1)),
            object_targets=int(value.get("object_targets", -1)),
        )
    except (TypeError, ValueError) as exc:
        raise ArtisanIllustratorError(
            "invalid_apply_plan", "Apply plan contains invalid counters."
        ) from exc
    if (
        value != expected
        or not PLAN_REF.fullmatch(str(value.get("plan_ref", "")))
        or not TRANSACTION_REF.fullmatch(str(value.get("transaction_ref", "")))
        or not APPROVAL_REF.fullmatch(str(value.get("approval_ref", "")))
    ):
        raise ArtisanIllustratorError(
            "apply_plan_integrity_failed", "Apply plan digest or content does not match."
        )
    return value


def _default_transport(proxy_url: str) -> Transport:
    base = proxy_url.rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ArtisanIllustratorError(
            "unsafe_proxy_url", "Illustrator apply accepts a loopback HTTP proxy only."
        )

    def call(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        if operation == "state":
            request = urllib.request.Request(f"{base}/state?max_age_ms=2000", method="GET")
        elif operation == "rpc":
            request = urllib.request.Request(
                f"{base}/rpc",
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            raise ValueError("unknown transport operation")
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    return call


def _receipt(core: dict[str, Any]) -> dict[str, Any]:
    digest = _sha256(_canonical(core))
    return {**core, "receipt_sha256": digest, "receipt_ref": f"receipt:{digest[:12]}"}


def _rpc(
    transport: Transport,
    *,
    request_id: int,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = transport(
        "rpc",
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
    )
    if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
        raise ArtisanIllustratorError("invalid_proxy_response", "Proxy response is invalid.")
    if "error" in response:
        message = str(response.get("error", {}).get("message", "proxy_error"))
        raise ArtisanIllustratorError("illustrator_proxy_error", message)
    result = response.get("result")
    if not isinstance(result, dict):
        raise ArtisanIllustratorError("invalid_proxy_response", "Proxy result is invalid.")
    return result


def probe_illustrator_state(
    *,
    proxy_url: str = "http://127.0.0.1:8972",
    transport: Transport | None = None,
) -> dict[str, Any]:
    active_transport = transport or _default_transport(proxy_url)
    try:
        state = active_transport("state", {})
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return {
            "ok": False,
            "ready": False,
            "status": "not_available",
            "state_revision": 0,
            "document_open": False,
            "external_ai_calls": 0,
        }
    state_value = state.get("state") if isinstance(state, dict) else None
    document_open = bool(isinstance(state_value, dict) and state_value.get("document") is not None)
    ready = bool(
        isinstance(state, dict) and state.get("ok") and not state.get("stale") and document_open
    )
    return {
        "ok": ready,
        "ready": ready,
        "status": "ready" if ready else "not_available",
        "state_revision": int(state.get("revision", 0)) if isinstance(state, dict) else 0,
        "document_open": document_open,
        "external_ai_calls": 0,
    }


def execute_apply_plan(
    *,
    plan_path: str,
    map_path: str,
    confirm_write: bool,
    approval_ref: str,
    proxy_url: str = "http://127.0.0.1:8972",
    transport: Transport | None = None,
) -> dict[str, Any]:
    plan = load_apply_plan(plan_path)
    try:
        mapping = load_illustrator_map(map_path)
    except ArtisanDirectionError as exc:
        raise ArtisanIllustratorError(exc.code, str(exc)) from exc
    if (
        mapping["map_ref"] != plan["map_ref"]
        or mapping["svg_sha256"] != plan["svg_sha256"]
        or mapping["edit_ref"] != plan["edit_ref"]
        or mapping["direction_ref"] != plan["direction_ref"]
        or len(mapping["layers"]) != plan["layer_targets"]
        or len(mapping["objects"]) != plan["object_targets"]
    ):
        raise ArtisanIllustratorError(
            "apply_map_binding_mismatch", "Apply plan and Illustrator map do not match."
        )
    common = {
        "schema_version": 1,
        "plan_ref": plan["plan_ref"],
        "transaction_ref": plan["transaction_ref"],
        "map_ref": plan["map_ref"],
        "layer_targets": plan["layer_targets"],
        "object_targets": plan["object_targets"],
        "external_ai_calls": 0,
    }
    if not confirm_write or approval_ref != plan["approval_ref"]:
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "awaiting_approval",
                "executed": False,
                "verified": False,
                "rolled_back": False,
                "error_code": "explicit_approval_required",
            }
        )
    active_transport = transport or _default_transport(proxy_url)
    try:
        state = active_transport("state", {})
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "not_available",
                "executed": False,
                "verified": False,
                "rolled_back": False,
                "error_code": "illustrator_adapter_not_available",
            }
        )
    state_value = state.get("state") if isinstance(state, dict) else None
    if (
        not isinstance(state, dict)
        or not state.get("ok")
        or state.get("stale")
        or not isinstance(state_value, dict)
        or state_value.get("document") is None
    ):
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "not_available",
                "executed": False,
                "verified": False,
                "rolled_back": False,
                "error_code": "fresh_illustrator_document_required",
            }
        )
    if state.get("revision") != plan["expected_state_revision"]:
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "stale_plan",
                "executed": False,
                "verified": False,
                "rolled_back": False,
                "error_code": "state_revision_changed",
            }
        )
    apply_params = {
        "confirm_write": True,
        "transaction_ref": plan["transaction_ref"],
        "map_ref": plan["map_ref"],
        "expected_state_revision": plan["expected_state_revision"],
        "layers": mapping["layers"],
        "objects": mapping["objects"],
    }
    readback_params = {
        "transaction_ref": plan["transaction_ref"],
        "map_ref": plan["map_ref"],
    }
    try:
        applied = _rpc(
            active_transport,
            request_id=1,
            method="illustrator.apply_artisan_map",
            params=apply_params,
        )
    except (ArtisanIllustratorError, OSError, TimeoutError, urllib.error.URLError):
        try:
            rollback = _rpc(
                active_transport,
                request_id=4,
                method="illustrator.rollback_artisan_map",
                params={**readback_params, "confirm_write": True},
            )
            rolled_back = bool(
                rollback.get("ok")
                and rollback.get("restored") == plan["layer_targets"] + plan["object_targets"]
            )
        except (ArtisanIllustratorError, OSError, TimeoutError, urllib.error.URLError):
            rolled_back = False
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "rolled_back" if rolled_back else "repair_needed",
                "executed": rolled_back,
                "verified": False,
                "rolled_back": rolled_back,
                "error_code": "artisan_apply_failed",
            }
        )
    if not applied.get("ok"):
        return _receipt(
            {
                **common,
                "ok": False,
                "status": "failed",
                "executed": False,
                "verified": False,
                "rolled_back": False,
                "error_code": "artisan_apply_rejected",
            }
        )
    expected = plan["layer_targets"] + plan["object_targets"]
    apply_counts_match = bool(
        applied.get("applied_layers") == plan["layer_targets"]
        and applied.get("applied_objects") == plan["object_targets"]
    )
    verified = False
    if apply_counts_match:
        try:
            readback = _rpc(
                active_transport,
                request_id=2,
                method="illustrator.readback_artisan_map",
                params=readback_params,
            )
            verified = bool(
                readback.get("ok")
                and readback.get("matched") == expected
                and readback.get("expected") == expected
            )
        except (ArtisanIllustratorError, OSError, TimeoutError, urllib.error.URLError):
            verified = False
    if verified:
        try:
            committed = _rpc(
                active_transport,
                request_id=3,
                method="illustrator.commit_artisan_map",
                params=readback_params,
            )
            commit_ok = bool(committed.get("ok") and committed.get("committed") == expected)
        except (ArtisanIllustratorError, OSError, TimeoutError, urllib.error.URLError):
            commit_ok = False
        if commit_ok:
            return _receipt(
                {
                    **common,
                    "ok": True,
                    "status": "completed",
                    "executed": True,
                    "verified": True,
                    "rolled_back": False,
                    "error_code": None,
                }
            )
    try:
        rollback = _rpc(
            active_transport,
            request_id=4 if verified else 3,
            method="illustrator.rollback_artisan_map",
            params={**readback_params, "confirm_write": True},
        )
        rolled_back = bool(rollback.get("ok") and rollback.get("restored") == expected)
    except (ArtisanIllustratorError, OSError, TimeoutError, urllib.error.URLError):
        rolled_back = False
    return _receipt(
        {
            **common,
            "ok": False,
            "status": "rolled_back" if rolled_back else "repair_needed",
            "executed": True,
            "verified": False,
            "rolled_back": rolled_back,
            "error_code": (
                "commit_failed"
                if verified
                else "readback_failed"
                if apply_counts_match
                else "apply_count_mismatch"
            ),
        }
    )


def _write_json(path_value: str, value: dict[str, Any], *, error_code: str) -> None:
    path = Path(path_value).expanduser()
    if path.exists():
        raise ArtisanIllustratorError(error_code, "Output already exists.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan or apply verified Artisan Illustrator names."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("--proxy-url", default="http://127.0.0.1:8972")
    probe_parser.add_argument("--soft-exit", action="store_true")
    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--svg", required=True)
    plan_parser.add_argument("--index", required=True)
    plan_parser.add_argument("--direction", required=True)
    plan_parser.add_argument("--map", required=True)
    plan_parser.add_argument("--state-revision", required=True, type=int)
    plan_parser.add_argument("--output", required=True)
    execute_parser = commands.add_parser("execute")
    execute_parser.add_argument("--plan", required=True)
    execute_parser.add_argument("--map", required=True)
    execute_parser.add_argument("--approval-ref", required=True)
    execute_parser.add_argument("--confirm-write", action="store_true")
    execute_parser.add_argument("--proxy-url", default="http://127.0.0.1:8972")
    execute_parser.add_argument("--receipt")
    execute_parser.add_argument("--soft-exit", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.command == "probe":
            result = probe_illustrator_state(proxy_url=args.proxy_url)
        elif args.command == "plan":
            plan = compile_apply_plan(
                svg_path=args.svg,
                index_path=args.index,
                direction_path=args.direction,
                map_path=args.map,
                expected_state_revision=args.state_revision,
            )
            _write_json(args.output, plan, error_code="apply_plan_exists")
            result = {
                "ok": True,
                "plan_ref": plan["plan_ref"],
                "approval_ref": plan["approval_ref"],
                "transaction_ref": plan["transaction_ref"],
                "external_ai_calls": 0,
            }
        else:
            result = execute_apply_plan(
                plan_path=args.plan,
                map_path=args.map,
                confirm_write=args.confirm_write,
                approval_ref=args.approval_ref,
                proxy_url=args.proxy_url,
            )
            if args.receipt:
                _write_json(args.receipt, result, error_code="apply_receipt_exists")
    except ArtisanIllustratorError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if result.get("ok"):
        return 0
    if (
        "args" in locals()
        and getattr(args, "soft_exit", False)
        and result.get("status") == "not_available"
    ):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
