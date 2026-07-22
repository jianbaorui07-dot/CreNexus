from __future__ import annotations

import base64
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starbridge_mcp.core.bridge_base import BaseBridge
from starbridge_mcp.core.result_schema import make_result

from .batchplay_schema import validate_descriptor
from .camera_raw_protocol import (
    CAMERA_RAW_BLOCKED_REASON,
    CAMERA_RAW_NEXT_STEP,
    build_camera_raw_tune_protocol,
    load_verified_descriptor_fixture,
    resolve_camera_raw_output_dir,
)
from .evidence import (
    build_manifest,
    build_output_artifact,
    manifest_path_for,
    new_job_id,
    preview_path_for,
    write_json,
    write_placeholder_png,
)
from .mock import mock_document, mock_layers, mock_probe
from .node_proxy_client import bridge_status as node_proxy_bridge_status
from .node_proxy_client import health as node_proxy_health
from .node_proxy_client import rpc as node_proxy_rpc


@dataclass
class RequestContext:
    tool_name: str
    job_id: str
    risk_level: str
    requires_confirmation: bool
    dry_run: bool
    writes_files: bool
    touches_user_psd: bool
    bridge_kind: str
    output_dir: str
    repo_root: Path
    evidence_dir: Path
    output_root: Path


def _bool(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


def _safe_name(tool_name: str) -> str:
    return tool_name.replace(".", "_")


_PHOTOSHOP_REAL_OUTPUT_REL = "examples/output/photoshop"


def _resolve_output_dir(repo_root: Path, requested: str) -> Path:
    relative = Path(requested)
    if relative.is_absolute():
        raise ValueError(
            "output_dir must be relative to the repository sandbox or output directories"
        )
    candidate = (repo_root / relative).resolve()
    allowed_roots = [
        (repo_root / "sandbox").resolve(),
        (repo_root / "output").resolve(),
        (repo_root / _PHOTOSHOP_REAL_OUTPUT_REL).resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError(
            "output_dir must stay inside sandbox/, output/, or examples/output/photoshop/"
        )
    return candidate


def _evidence_dir_for(repo_root: Path, output_dir: Path) -> Path:
    real_root = (repo_root / _PHOTOSHOP_REAL_OUTPUT_REL).resolve()
    if output_dir == real_root or real_root in output_dir.parents:
        return (real_root / "evidence").resolve()
    top = output_dir.relative_to(repo_root).parts[0]
    return (repo_root / top / "evidence").resolve()


def _build_context(arguments: dict[str, Any], repo_root: Path, tool_name: str) -> RequestContext:
    requested_output = str(arguments.get("output_dir") or "sandbox/evidence")
    output_root = _resolve_output_dir(repo_root, requested_output)
    evidence_dir = _evidence_dir_for(repo_root, output_root)
    return RequestContext(
        tool_name=tool_name,
        job_id=str(arguments.get("job_id") or new_job_id()),
        risk_level=str(arguments.get("risk_level") or "level_0_read_only"),
        requires_confirmation=_bool(
            arguments.get("requires_confirmation") or arguments.get("confirm_write"), False
        ),
        dry_run=_bool(arguments.get("dry_run"), True),
        writes_files=_bool(arguments.get("writes_files"), False),
        touches_user_psd=_bool(arguments.get("touches_user_psd"), True),
        bridge_kind=str(arguments.get("bridge_kind") or "auto"),
        output_dir=output_root.relative_to(repo_root).as_posix(),
        repo_root=repo_root,
        evidence_dir=evidence_dir,
        output_root=output_root,
    )


def _build_camera_raw_context(arguments: dict[str, Any], repo_root: Path) -> RequestContext:
    raw_output = arguments.get("output") or {}
    requested_output = raw_output.get("dir") if isinstance(raw_output, dict) else None
    output_root = resolve_camera_raw_output_dir(
        repo_root,
        str(requested_output or arguments.get("output_dir") or "examples/output/photoshop"),
    )
    evidence_dir = (output_root / "evidence").resolve()
    return RequestContext(
        tool_name="ps.camera_raw.tune",
        job_id=str(arguments.get("job_id") or new_job_id()),
        risk_level=str(arguments.get("risk_level") or "level_2_confirmed_write"),
        requires_confirmation=_bool(
            arguments.get("requires_confirmation") or arguments.get("confirm_apply"), False
        ),
        dry_run=_bool(arguments.get("dry_run"), True),
        writes_files=_bool(arguments.get("writes_files"), False),
        touches_user_psd=_bool(arguments.get("touches_user_psd"), True),
        bridge_kind=str(arguments.get("bridge_kind") or "auto"),
        output_dir=output_root.relative_to(repo_root).as_posix(),
        repo_root=repo_root,
        evidence_dir=evidence_dir,
        output_root=output_root,
    )


def _probe_com(probe_com: bool) -> tuple[bool, dict[str, Any], Any | None]:
    has_win32com = importlib.util.find_spec("win32com") is not None
    data: dict[str, Any] = {
        "has_win32com": has_win32com,
        "probe_com": probe_com,
        "photoshop_available": False,
        "active_document": False,
        "com_version": None,
        "document_count": 0,
    }
    if not probe_com or not has_win32com:
        return False, data, None
    try:
        import win32com.client  # type: ignore[import-not-found]

        app = win32com.client.GetActiveObject("Photoshop.Application")
        data["photoshop_available"] = True
        data["com_version"] = str(getattr(app, "Version", "unknown"))
        documents = getattr(app, "Documents", None)
        count = int(getattr(documents, "Count", 0)) if documents is not None else 0
        data["document_count"] = count
        data["active_document"] = count > 0
        return True, data, app
    except Exception as exc:  # pragma: no cover
        data["error"] = str(exc)
        return False, data, None


def _com_document_summary(app: Any) -> dict[str, Any]:
    document = app.Application.ActiveDocument if hasattr(app, "Application") else app.ActiveDocument
    active_layer = getattr(document, "ActiveLayer", None)
    layer_name = str(getattr(active_layer, "Name", "")) if active_layer is not None else ""
    return {
        "document_id": str(getattr(document, "ID", "active")),
        "title": str(getattr(document, "Name", "active_document")),
        "name": str(getattr(document, "Name", "active_document")),
        "width": int(float(document.Width)),
        "height": int(float(document.Height)),
        "resolution": int(float(getattr(document, "Resolution", 72))),
        "color_mode": str(getattr(document, "Mode", "unknown")),
        "bit_depth": int(getattr(document, "BitsPerChannel", 8)),
        "active_layer_id": str(getattr(active_layer, "ID", "")) if active_layer is not None else "",
        "active_layer_name": layer_name,
        "layer_count": int(getattr(document.Layers, "Count", 0)),
        "saved": None,
    }


def _extract_layers(
    container: Any, depth: int, max_layers: int, rows: list[dict[str, Any]], path: list[str]
) -> None:
    if len(rows) >= max_layers:
        return
    try:
        count = int(getattr(container.Layers, "Count", 0))
    except Exception:
        count = 0
    for index in range(1, count + 1):
        if len(rows) >= max_layers:
            return
        layer = container.Layers.Item(index)
        type_name = str(
            getattr(layer, "typename", getattr(layer, "__class__", type(layer)).__name__)
        )
        kind = (
            "group"
            if "LayerSet" in type_name or "Group" in type_name
            else str(getattr(layer, "Kind", "layer"))
        )
        name = str(getattr(layer, "Name", f"Layer {index}"))
        row = {
            "id": str(getattr(layer, "ID", f"{depth}-{index}")),
            "name": name,
            "kind": kind,
            "type": kind,
            "visible": bool(getattr(layer, "Visible", True)),
            "locked": bool(getattr(layer, "AllLocked", False)),
            "opacity": int(float(getattr(layer, "Opacity", 100))),
            "blendMode": str(getattr(layer, "BlendMode", "normal")),
            "bounds": None,
            "group_path": "/".join(path),
        }
        rows.append(row)
        if row["kind"] == "group" and hasattr(layer, "Layers"):
            _extract_layers(layer, depth + 1, max_layers, rows, [*path, name])


def _write_manifest_if_requested(ctx: RequestContext, manifest: dict[str, Any]) -> str | None:
    if ctx.dry_run:
        return None
    target = manifest_path_for(ctx.evidence_dir, _safe_name(ctx.tool_name), ctx.job_id)
    write_json(target, manifest)
    return target.relative_to(ctx.repo_root).as_posix()


def _guard_confirmation(
    ctx: RequestContext, *, flag_name: str = "requires_confirmation"
) -> dict[str, Any] | None:
    if ctx.writes_files and not ctx.dry_run and not ctx.requires_confirmation:
        return make_result(
            ok=False,
            bridge="photoshop",
            action=ctx.tool_name.rsplit(".", 1)[-1].replace(".", "_"),
            message=f"{ctx.tool_name} refused because {flag_name} must be true when dry_run is false.",
            details={
                "job_id": ctx.job_id,
                "risk_level": ctx.risk_level,
                "output_dir": ctx.output_dir,
            },
            warnings=["Writes are sandboxed and disabled by default."],
            next_steps=[
                "Repeat with dry_run=true for planning.",
                f"Set {flag_name}=true only for sandbox output.",
            ],
        )
    return None


def _node_proxy_probe() -> dict[str, Any]:
    health = node_proxy_health()
    status = node_proxy_bridge_status() if health.get("ok") else health
    return {
        "health": health,
        "status": status,
        "node_proxy_running": bool(status.get("node_proxy_running")),
        "uxp_client_connected": bool(status.get("uxp_client_connected")),
        "photoshop_host_seen": bool(status.get("photoshop_host_seen")),
    }


def _bridge_priority(ctx: RequestContext) -> list[str]:
    requested = ctx.bridge_kind
    if requested in {"mock", "com", "node_proxy_uxp", "fallback"}:
        return [requested]
    return ["node_proxy_uxp", "com", "mock"]


def _make_manifest(
    ctx: RequestContext,
    *,
    input_summary: dict[str, Any],
    output_files: list[str],
    preview_files: list[str],
    source_files: list[str],
    photoshop_available: bool,
    bridge_kind: str,
    node_proxy_status: dict[str, Any],
    uxp_status: dict[str, Any],
    photoshop_host: dict[str, Any],
    layers_snapshot: list[dict[str, Any]],
    history_state: str | None,
    descriptor_summary: list[dict[str, Any]],
    validation_result: dict[str, Any],
    status: str,
    warnings: list[str],
    errors: list[str],
    output_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_manifest(
        job_id=ctx.job_id,
        tool_name=ctx.tool_name,
        risk_level=ctx.risk_level,
        requires_confirmation=ctx.requires_confirmation,
        dry_run=ctx.dry_run,
        input_summary=input_summary,
        output_files=output_files,
        preview_files=preview_files,
        source_files=source_files,
        photoshop_available=photoshop_available,
        bridge_kind=bridge_kind,
        node_proxy_status=node_proxy_status,
        uxp_status=uxp_status,
        photoshop_host=photoshop_host,
        layers_snapshot=layers_snapshot,
        history_state=history_state,
        descriptor_summary=descriptor_summary,
        validation_result=validation_result,
        status=status,
        warnings=warnings,
        errors=errors,
        output_artifacts=output_artifacts,
    ).to_dict()


class PhotoshopBridgeAdapter(BaseBridge):
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    @property
    def bridge_id(self) -> str:
        return "photoshop"

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    def probe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.probe")
        strict = _bool(arguments.get("strict"), False)
        proxy = _node_proxy_probe()
        com_ok, com_data, _app = _probe_com(probe_com=_bool(arguments.get("probe_com"), True))
        bridge_kind = (
            "node_proxy_uxp" if proxy["uxp_client_connected"] else ("com" if com_ok else "mock")
        )
        details = {
            "job_id": ctx.job_id,
            "bridge_kind": bridge_kind,
            "strict": strict,
            "node_proxy_status": proxy["status"],
            "uxp_client_connected": proxy["uxp_client_connected"],
            "photoshop_host": proxy["status"].get("photoshop_host") or {},
            "com_availability": com_data,
            "mock_fallback": mock_probe(),
        }
        warnings = (
            []
            if proxy["uxp_client_connected"]
            else ["node_proxy_uxp not connected; live UXP routing is unavailable."]
        )
        if strict and bridge_kind == "mock":
            return make_result(
                ok=False,
                bridge="photoshop",
                action="probe",
                message=(
                    "strict=true: refusing to report success on the mock bridge. "
                    "Start the node_proxy and connect the UXP plugin (or enable COM) to pass strict probe."
                ),
                details=details,
                warnings=warnings,
                next_steps=[
                    "Start node_proxy: npm.cmd run photoshop:node-proxy.",
                    "Load uxp/photoshop-bridge in UXP Developer Tool and connect to Photoshop.",
                    "Retry ps.probe with strict=true.",
                ],
            )
        return make_result(
            ok=True,
            bridge="photoshop",
            action="probe",
            message="Photoshop bridge probe completed.",
            details=details,
            warnings=warnings,
            next_steps=[
                "Use ps.document.info for active-document metadata.",
                "Use ps.layers.list for live or mock layer inspection.",
            ],
        )

    def document_info(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.document.info")
        warnings: list[str] = []
        errors: list[str] = []
        proxy = _node_proxy_probe()
        com_ok, com_data, app = _probe_com(probe_com=True)
        document: dict[str, Any] | None = None
        bridge_kind = "fallback"
        uxp_status: dict[str, Any] = {}
        host_info: dict[str, Any] = {}

        for mode in _bridge_priority(ctx):
            if mode == "node_proxy_uxp" and proxy["uxp_client_connected"]:
                try:
                    response = node_proxy_rpc("ps.document.info", {"job_id": ctx.job_id})
                    if "result" in response:
                        payload = response["result"]
                        document = dict(payload.get("document") or {})
                        uxp_status = {"connected": True, "method": "ps.document.info"}
                        host_info = dict(payload.get("photoshop_host") or {})
                        bridge_kind = "node_proxy_uxp"
                        break
                except Exception as exc:
                    warnings.append(f"node_proxy_uxp document_info failed: {type(exc).__name__}")
            if mode == "com" and com_ok and com_data.get("active_document") and app is not None:
                document = _com_document_summary(app)
                bridge_kind = "com"
                host_info = {"version": com_data.get("com_version")}
                break
            if mode == "mock":
                document = mock_document()
                bridge_kind = "mock"
                warnings.append("Mock bridge returned a placeholder document summary.")
                break

        if document is None:
            errors.append("No active Photoshop document is available.")
            document = {}

        manifest = _make_manifest(
            ctx,
            input_summary={
                "include_layer_summary": _bool(arguments.get("include_layer_summary"), True)
            },
            output_files=[],
            preview_files=[],
            source_files=["<active_document>"] if document else [],
            photoshop_available=bridge_kind != "mock" or bool(document),
            bridge_kind=bridge_kind,
            node_proxy_status=proxy["status"],
            uxp_status=uxp_status,
            photoshop_host=host_info,
            layers_snapshot=[],
            history_state=None,
            descriptor_summary=[],
            validation_result={},
            status="ok" if not errors else "not_available",
            warnings=warnings,
            errors=errors,
        )
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action="document_info",
            message="Active Photoshop document summary returned."
            if not errors
            else "No active Photoshop document is available.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": bridge_kind,
                "document": document,
                "node_proxy_status": proxy["status"],
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=warnings,
            next_steps=[
                "Use ps.layers.list against the same bridge.",
                "Keep preview export on sandbox output only.",
            ],
        )

    def layers_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.layers.list")
        max_layers = int(arguments.get("max_layers") or 200)
        warnings: list[str] = []
        errors: list[str] = []
        proxy = _node_proxy_probe()
        com_ok, com_data, app = _probe_com(probe_com=True)
        layers: list[dict[str, Any]] = []
        bridge_kind = "fallback"
        uxp_status: dict[str, Any] = {}
        host_info: dict[str, Any] = {}

        for mode in _bridge_priority(ctx):
            if mode == "node_proxy_uxp" and proxy["uxp_client_connected"]:
                try:
                    response = node_proxy_rpc(
                        "ps.layers.list", {"job_id": ctx.job_id, "max_layers": max_layers}
                    )
                    if "result" in response:
                        payload = response["result"]
                        layers = [dict(item) for item in payload.get("layers") or []][:max_layers]
                        uxp_status = {"connected": True, "method": "ps.layers.list"}
                        host_info = dict(payload.get("photoshop_host") or {})
                        bridge_kind = "node_proxy_uxp"
                        break
                except Exception as exc:
                    warnings.append(f"node_proxy_uxp layers_list failed: {type(exc).__name__}")
            if mode == "com" and com_ok and com_data.get("active_document") and app is not None:
                document = (
                    app.Application.ActiveDocument
                    if hasattr(app, "Application")
                    else app.ActiveDocument
                )
                _extract_layers(document, 0, max_layers, layers, [])
                bridge_kind = "com"
                host_info = {"version": com_data.get("com_version")}
                break
            if mode == "mock":
                layers = mock_layers()[:max_layers]
                bridge_kind = "mock"
                warnings.append("Mock bridge returned a placeholder layer list.")
                break

        if not layers:
            errors.append("No active Photoshop document is available for layer inspection.")

        manifest = _make_manifest(
            ctx,
            input_summary={"max_layers": max_layers},
            output_files=[],
            preview_files=[],
            source_files=["<active_document>"] if layers else [],
            photoshop_available=bridge_kind != "mock" or bool(layers),
            bridge_kind=bridge_kind,
            node_proxy_status=proxy["status"],
            uxp_status=uxp_status,
            photoshop_host=host_info,
            layers_snapshot=layers,
            history_state=None,
            descriptor_summary=[],
            validation_result={},
            status="ok" if layers else "not_available",
            warnings=warnings,
            errors=errors,
        )
        return make_result(
            ok=bool(layers),
            bridge="photoshop",
            action="layers_list",
            message="Photoshop layers list returned."
            if layers
            else "No active Photoshop document is available for layer inspection.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": bridge_kind,
                "layer_count": len(layers),
                "layers": layers,
                "node_proxy_status": proxy["status"],
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=warnings,
            next_steps=[
                "Use preview export only on sandbox output.",
                "Validate any batchPlay descriptor before confirmed execution.",
            ],
        )

    def preview_export(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.preview.export")
        refusal = _guard_confirmation(ctx)
        if refusal is not None:
            return refusal
        strict = _bool(arguments.get("strict"), False)
        allow_placeholder = _bool(arguments.get("allow_placeholder"), False)
        proxy = _node_proxy_probe()
        preview_files: list[str] = []
        output_artifacts: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        layers_snapshot: list[dict[str, Any]] = []
        bridge_kind = "fallback"
        real_output_verified = False
        history_state: str | None = None
        uxp_status: dict[str, Any] = {}
        host_info: dict[str, Any] = {}
        document_name: str | None = None
        width_hint: int | None = None
        height_hint: int | None = None

        if ctx.dry_run:
            if proxy["uxp_client_connected"]:
                bridge_kind = "node_proxy_uxp"
            else:
                bridge_kind = "mock"
                if strict:
                    errors.append(
                        "strict=true: dry-run cannot use the mock bridge because no real UXP link is connected."
                    )
                else:
                    warnings.append(
                        "Dry-run preview export did not contact Photoshop; review plan only."
                    )
        elif proxy["uxp_client_connected"]:
            try:
                preview_path = preview_path_for(ctx.output_root, ctx.job_id)
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                response = node_proxy_rpc(
                    "ps.preview.export",
                    {
                        "job_id": ctx.job_id,
                        "output_path": preview_path.as_posix(),
                        "confirm_write": True,
                        "dry_run": False,
                    },
                )
                if "result" in response:
                    payload = response["result"] or {}
                    if payload.get("ok") is False:
                        errors.append(
                            "UXP refused preview export: "
                            + str(payload.get("message") or "unknown_uxp_error")
                        )
                    else:
                        written = str(payload.get("preview_path") or "").strip()
                        document_name = payload.get("document_name") or None
                        try:
                            width_hint = (
                                int(payload["width"]) if payload.get("width") is not None else None
                            )
                            height_hint = (
                                int(payload["height"])
                                if payload.get("height") is not None
                                else None
                            )
                        except (TypeError, ValueError):
                            width_hint = height_hint = None
                        written_path = Path(written) if written else preview_path
                        if not written_path.is_absolute():
                            written_path = (self.repo_root / written_path).resolve()
                        if written_path.is_file():
                            try:
                                artifact = build_output_artifact(
                                    written_path,
                                    repo_root=self.repo_root,
                                    document_name=document_name,
                                    width_hint=width_hint,
                                    height_hint=height_hint,
                                )
                                output_artifacts.append(artifact)
                                preview_files.append(artifact["relative_path"])
                                real_output_verified = True
                            except (ValueError, FileNotFoundError) as artifact_exc:
                                errors.append(
                                    "preview verification failed: "
                                    f"{type(artifact_exc).__name__}: {artifact_exc}"
                                )
                        else:
                            errors.append(
                                "UXP reported success but the PNG was not found at "
                                f"{written_path.as_posix()}"
                            )
                        layers_snapshot = [
                            dict(item) for item in payload.get("layers_snapshot") or []
                        ]
                        history_state = payload.get("history_state")
                        host_info = dict(payload.get("photoshop_host") or {})
                        uxp_status = {"connected": True, "method": "ps.preview.export"}
                        bridge_kind = "node_proxy_uxp"
                elif "error" in response:
                    rpc_error = response["error"] or {}
                    errors.append(
                        "Node Proxy RPC error: "
                        + str(rpc_error.get("message") or rpc_error.get("code") or "unknown")
                    )
                else:
                    errors.append("Node Proxy did not return a preview export result.")
            except Exception as exc:
                errors.append(f"Node Proxy preview export failed: {type(exc).__name__}")
        elif strict:
            bridge_kind = "mock"
            errors.append(
                "strict=true: refusing to write a placeholder PNG because the UXP bridge is not connected. "
                "Start node_proxy and connect the UXP plugin, then retry."
            )
        elif not allow_placeholder:
            bridge_kind = "mock"
            errors.append(
                "Refusing to write a placeholder PNG because the UXP bridge is not connected. "
                "Set allow_placeholder=true only for local protocol demos; use strict=true for real evidence."
            )
        else:
            bridge_kind = "mock"
            preview_path = preview_path_for(ctx.output_root, ctx.job_id)
            write_placeholder_png(preview_path)
            relative = preview_path.relative_to(ctx.repo_root).as_posix()
            preview_files.append(relative)
            warnings.append(
                "Photoshop UXP was not connected; wrote a placeholder preview in sandbox output."
            )
            try:
                artifact = build_output_artifact(
                    preview_path,
                    repo_root=self.repo_root,
                    document_name=None,
                )
                artifact["placeholder"] = True
                output_artifacts.append(artifact)
            except (ValueError, FileNotFoundError):
                pass

        manifest = _make_manifest(
            ctx,
            input_summary={
                "output_dir": ctx.output_dir,
                "format": str(arguments.get("format") or "png"),
                "strict": strict,
                "allow_placeholder": allow_placeholder,
                "real_output_verified": real_output_verified,
            },
            output_files=preview_files,
            preview_files=preview_files,
            source_files=["<active_document>"],
            photoshop_available=bridge_kind in {"node_proxy_uxp", "com"},
            bridge_kind=bridge_kind,
            node_proxy_status=proxy["status"],
            uxp_status=uxp_status,
            photoshop_host=host_info,
            layers_snapshot=layers_snapshot,
            history_state=history_state,
            descriptor_summary=[],
            validation_result={"real_output_verified": real_output_verified},
            status="ok" if not errors else "not_available",
            warnings=warnings,
            errors=errors,
            output_artifacts=output_artifacts,
        )
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action="preview_export",
            message="Preview export staged." if not errors else "Preview export blocked.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": bridge_kind,
                "strict": strict,
                "allow_placeholder": allow_placeholder,
                "real_output_verified": real_output_verified,
                "preview_files": preview_files,
                "output_artifacts": output_artifacts,
                "layers_snapshot": layers_snapshot,
                "history_state": history_state,
                "node_proxy_status": proxy["status"],
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=warnings,
            next_steps=[
                "Review preview_files and layers_snapshot before follow-up edits.",
                "Keep writes restricted to sandbox copies.",
            ],
        )

    def camera_raw_tune(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_camera_raw_context(arguments, self.repo_root)
        confirm_apply = _bool(arguments.get("confirm_apply"), False)
        confirm_export = _bool(arguments.get("confirm_export"), False)
        plan, errors = build_camera_raw_tune_protocol(arguments, self.repo_root)
        proxy = _node_proxy_probe()
        warnings: list[str] = []
        if errors:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="camera_raw_tune",
                message="Camera Raw tuning plan validation failed.",
                details={
                    "job_id": ctx.job_id,
                    "errors": errors,
                    "dry_run": ctx.dry_run,
                    "confirm_apply": confirm_apply,
                    "confirm_export": confirm_export,
                },
                warnings=["Camera Raw tuning accepts only reviewed numeric slider ranges."],
                next_steps=["Fix params and rerun with dry_run=true."],
            )

        assert plan is not None
        descriptor_fixture, descriptor_errors = load_verified_descriptor_fixture(arguments, plan)
        manifest_status = "ok" if ctx.dry_run else "blocked"
        manifest_errors: list[str] = []
        if not ctx.dry_run and not confirm_apply:
            manifest_errors.append("confirm_apply=true is required when dry_run=false.")
        elif (
            not ctx.dry_run
            and bool(plan["output"].get("export_after_apply"))
            and not confirm_export
        ):
            manifest_errors.append(
                "confirm_export=true is required when output.export_after_apply=true and dry_run=false."
            )
        elif not ctx.dry_run and descriptor_errors:
            manifest_errors.extend(descriptor_errors)
        elif not ctx.dry_run and descriptor_fixture is None:
            manifest_errors.append(CAMERA_RAW_BLOCKED_REASON)

        manifest = _make_manifest(
            ctx,
            input_summary={
                "preset": plan["preset"],
                "params": plan["params"],
                "source": plan["source"],
                "output": plan["output"],
                "confirm_apply": confirm_apply,
                "confirm_export": confirm_export,
                "output_dir": ctx.output_dir,
            },
            output_files=[],
            preview_files=[],
            source_files=["<active_document>"],
            photoshop_available=bool(proxy["uxp_client_connected"]),
            bridge_kind="node_proxy_uxp" if proxy["uxp_client_connected"] else "fallback",
            node_proxy_status=proxy["status"],
            uxp_status={
                "connected": proxy["uxp_client_connected"],
                "method": "ps.camera_raw.tune" if proxy["uxp_client_connected"] else None,
            },
            photoshop_host=dict(proxy["status"].get("photoshop_host") or {}),
            layers_snapshot=[],
            history_state=None,
            descriptor_summary=[],
            validation_result={
                "ok": not errors,
                "descriptor_available": descriptor_fixture is not None,
                "descriptor_count": int(descriptor_fixture.get("descriptor_count", 0))
                if descriptor_fixture
                else 0,
                "blocked_reason": None if descriptor_fixture else CAMERA_RAW_BLOCKED_REASON,
            },
            status=manifest_status,
            warnings=warnings,
            errors=manifest_errors,
        )

        if ctx.dry_run:
            return make_result(
                ok=True,
                bridge="photoshop",
                action="camera_raw_tune",
                message="Camera Raw tuning dry-run plan validated.",
                details={
                    "job_id": ctx.job_id,
                    "dry_run": True,
                    "confirm_apply": confirm_apply,
                    "confirm_export": confirm_export,
                    "plan": plan,
                    "descriptor_fixture": {
                        "available": descriptor_fixture is not None,
                        "errors": descriptor_errors,
                    },
                    "evidence_manifest": manifest,
                    "evidence_path": None,
                },
                warnings=["Camera Raw tuning is experimental; no Photoshop state was modified."],
                next_steps=[
                    "Record and review a Camera Raw Filter BatchPlay descriptor before enabling confirmed apply."
                ],
            )

        if not confirm_apply:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="camera_raw_tune",
                message="ps.camera_raw.tune refused because confirm_apply=true is required when dry_run=false.",
                details={
                    "job_id": ctx.job_id,
                    "dry_run": False,
                    "confirm_apply": False,
                    "confirm_export": confirm_export,
                    "plan": plan,
                    "evidence_manifest": manifest,
                    "evidence_path": _write_manifest_if_requested(ctx, manifest),
                },
                warnings=["Real Camera Raw tuning would modify the active Photoshop document."],
                next_steps=[
                    "Rerun dry_run first, then set confirm_apply=true only after reviewing the plan."
                ],
            )

        if bool(plan["output"].get("export_after_apply")) and not confirm_export:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="camera_raw_tune",
                message="ps.camera_raw.tune refused because confirm_export=true is required for real export.",
                details={
                    "job_id": ctx.job_id,
                    "dry_run": False,
                    "confirm_apply": True,
                    "confirm_export": False,
                    "plan": plan,
                    "evidence_manifest": manifest,
                    "evidence_path": _write_manifest_if_requested(ctx, manifest),
                },
                warnings=[
                    "Real Camera Raw export would write files and must stay inside examples/output/photoshop."
                ],
                next_steps=[
                    "Rerun dry_run first, then set confirm_export=true only for reviewed sandbox output."
                ],
            )

        if descriptor_errors:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="camera_raw_tune",
                message="Camera Raw tuning apply is blocked because the descriptor fixture is invalid.",
                details={
                    "job_id": ctx.job_id,
                    "dry_run": False,
                    "confirm_apply": True,
                    "confirm_export": confirm_export,
                    "descriptor_fixture_errors": descriptor_errors,
                    "plan": plan,
                    "evidence_manifest": manifest,
                    "evidence_path": _write_manifest_if_requested(ctx, manifest),
                },
                warnings=[
                    "Only locally recorded and explicitly verified Camera Raw descriptor fixtures may be used."
                ],
                next_steps=[CAMERA_RAW_NEXT_STEP],
            )

        if descriptor_fixture is not None and proxy["uxp_client_connected"]:
            try:
                response = node_proxy_rpc(
                    "ps.camera_raw.tune",
                    {
                        "job_id": ctx.job_id,
                        "plan": plan,
                        "descriptors": descriptor_fixture["descriptors"],
                        "descriptor_fixture_verified": True,
                        "confirm_apply": True,
                        "confirm_export": confirm_export,
                    },
                )
                if "result" in response:
                    payload = dict(response["result"] or {})
                    executed = bool(payload.get("executed") or payload.get("ok"))
                    if executed:
                        manifest["status"] = "ok"
                        manifest["validation_result"]["blocked_reason"] = None
                    return make_result(
                        ok=executed,
                        bridge="photoshop",
                        action="camera_raw_tune",
                        message="Camera Raw tuning apply completed."
                        if executed
                        else "Camera Raw tuning apply returned without execution.",
                        details={
                            "job_id": ctx.job_id,
                            "dry_run": False,
                            "confirm_apply": True,
                            "confirm_export": confirm_export,
                            "executed": executed,
                            "plan": plan,
                            "uxp_result": payload,
                            "evidence_manifest": manifest,
                            "evidence_path": _write_manifest_if_requested(ctx, manifest),
                        },
                        warnings=[str(item) for item in payload.get("warnings") or []],
                        next_steps=[
                            "Review Photoshop history and exported files before additional edits."
                        ],
                    )
            except Exception as exc:
                manifest["errors"].append(
                    f"Node Proxy camera_raw_tune failed: {type(exc).__name__}"
                )
                return make_result(
                    ok=False,
                    bridge="photoshop",
                    action="camera_raw_tune",
                    message="Camera Raw tuning apply failed through Node Proxy / UXP.",
                    details={
                        "job_id": ctx.job_id,
                        "dry_run": False,
                        "confirm_apply": True,
                        "confirm_export": confirm_export,
                        "error": type(exc).__name__,
                        "plan": plan,
                        "evidence_manifest": manifest,
                        "evidence_path": _write_manifest_if_requested(ctx, manifest),
                    },
                    warnings=["Photoshop UXP bridge must be running and connected for real apply."],
                    next_steps=[
                        "Start the Photoshop node proxy and UXP plugin, then retry the confirmed command."
                    ],
                )

        if descriptor_fixture is not None and not proxy["uxp_client_connected"]:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="camera_raw_tune",
                message="Camera Raw descriptor fixture is ready, but Photoshop UXP is not connected.",
                details={
                    "job_id": ctx.job_id,
                    "dry_run": False,
                    "confirm_apply": True,
                    "confirm_export": confirm_export,
                    "descriptor_fixture": {
                        "available": True,
                        "verified": True,
                        "descriptor_count": descriptor_fixture["descriptor_count"],
                    },
                    "plan": plan,
                    "evidence_manifest": manifest,
                    "evidence_path": _write_manifest_if_requested(ctx, manifest),
                },
                warnings=["Node Proxy / UXP is required for real Photoshop apply."],
                next_steps=[
                    "Run npm.cmd run photoshop:node-proxy and connect the UXP plugin, then retry."
                ],
            )

        return make_result(
            ok=False,
            bridge="photoshop",
            action="camera_raw_tune",
            message="Camera Raw tuning apply is blocked until a verified BatchPlay descriptor is recorded.",
            details={
                "job_id": ctx.job_id,
                "dry_run": False,
                "confirm_apply": True,
                "confirm_export": confirm_export,
                "blocked_reason": CAMERA_RAW_BLOCKED_REASON,
                "next_step": CAMERA_RAW_NEXT_STEP,
                "plan": plan,
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=["No Camera Raw Filter BatchPlay descriptor fixture is bundled yet."],
            next_steps=[CAMERA_RAW_NEXT_STEP],
        )

    def evidence_capture(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.evidence.capture")
        refusal = _guard_confirmation(ctx)
        if refusal is not None:
            return refusal
        proxy = _node_proxy_probe()
        manifest = _make_manifest(
            ctx,
            input_summary={
                "notes": str(arguments.get("notes") or ""),
                "output_dir": ctx.output_dir,
            },
            output_files=[],
            preview_files=[],
            source_files=[str(item) for item in arguments.get("source_files") or []],
            photoshop_available=bool(proxy["photoshop_host_seen"]),
            bridge_kind="node_proxy_uxp" if proxy["uxp_client_connected"] else "fallback",
            node_proxy_status=proxy["status"],
            uxp_status={"connected": proxy["uxp_client_connected"]},
            photoshop_host=dict(proxy["status"].get("photoshop_host") or {}),
            layers_snapshot=[],
            history_state=None,
            descriptor_summary=[],
            validation_result={},
            status="ok",
            warnings=[],
            errors=[],
        )
        return make_result(
            ok=True,
            bridge="photoshop",
            action="evidence_capture",
            message="Evidence manifest captured.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": manifest["bridge_kind"],
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=[],
            next_steps=[
                "Attach document, layer, preview, and validation outputs to the same job_id."
            ],
        )

    def batchplay_validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.batchplay.validate")
        descriptor = arguments.get("descriptor")
        descriptors = arguments.get("descriptors") or []
        if descriptor is not None:
            descriptors = [descriptor, *descriptors]
        if not isinstance(descriptors, list):
            raise ValueError("descriptors must be a list")
        if len(descriptors) > 32:
            raise ValueError("descriptors must contain at most 32 items")

        validations: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        for index, item in enumerate(descriptors, start=1):
            if not isinstance(item, dict):
                errors.append(f"Descriptor {index} must be an object.")
                continue
            validation = {"index": index, **validate_descriptor(item)}
            validations.append(validation)
            if not validation["allowed"]:
                warnings.append(validation["reason"])
        if not descriptors:
            errors.append("At least one descriptor is required.")

        validation_result = {
            "ok": not errors and all(item["allowed"] for item in validations),
            "descriptor_count": len(descriptors),
            "blocked_count": sum(1 for item in validations if not item["allowed"]),
            "validations": validations,
        }
        manifest = _make_manifest(
            ctx,
            input_summary={"descriptor_count": len(descriptors)},
            output_files=[],
            preview_files=[],
            source_files=[],
            photoshop_available=False,
            bridge_kind="fallback",
            node_proxy_status=_node_proxy_probe()["status"],
            uxp_status={},
            photoshop_host={},
            layers_snapshot=[],
            history_state=None,
            descriptor_summary=validations,
            validation_result=validation_result,
            status="ok" if validation_result["ok"] else "blocked",
            warnings=warnings,
            errors=errors,
        )
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action="batchplay_validate",
            message="BatchPlay payload validated."
            if not errors
            else "BatchPlay payload validation failed.",
            details={
                "job_id": ctx.job_id,
                "descriptor_count": len(descriptors),
                "descriptors": validations,
                "validation_result": validation_result,
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
            },
            warnings=warnings,
            next_steps=[
                "Only call ps.batchplay.execute_confirmed after an allowed validation result.",
                "Keep writes on sandbox copies only.",
            ],
        )

    def batchplay_execute_confirmed(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.batchplay.execute_confirmed")
        confirmation = _bool(
            arguments.get("confirm_write") or arguments.get("requires_confirmation"), False
        )
        if not confirmation:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="batchplay_execute_confirmed",
                message="ps.batchplay.execute_confirmed requires_confirmation=true and confirm_write=true.",
                details={"job_id": ctx.job_id, "executed": False, "confirmation_required": True},
                warnings=[
                    "Confirmed execution is disabled until explicit confirmation is provided."
                ],
                next_steps=[
                    "Call ps.batchplay.validate first.",
                    "Retry with requires_confirmation=true and confirm_write=true on sandbox output only.",
                ],
            )
        validation = self.batchplay_validate(arguments)
        validation_payload = (
            validation["details"]
            if "details" in validation
            else validation.get("result", {}).get("structuredContent", {}).get("details", {})
        )
        validation_result = dict(validation_payload.get("validation_result") or {})
        descriptors = list(validation_payload.get("descriptors") or [])
        if not validation_result.get("ok"):
            return make_result(
                ok=False,
                bridge="photoshop",
                action="batchplay_execute_confirmed",
                message="Validation blocked execute_confirmed.",
                details={
                    "job_id": ctx.job_id,
                    "executed": False,
                    "validation_result": validation_result,
                },
                warnings=["Descriptor validation must pass before confirmed execution."],
                next_steps=["Remove denied actions and keep the operation within sandbox copies."],
            )

        proxy = _node_proxy_probe()
        warnings: list[str] = []
        errors: list[str] = []
        preview_files: list[str] = []
        layers_snapshot: list[dict[str, Any]] = []
        history_state: str | None = None
        executed = False
        bridge_kind = "not_available"
        host_info: dict[str, Any] = {}
        uxp_status: dict[str, Any] = {}

        if not ctx.dry_run and proxy["uxp_client_connected"]:
            try:
                preview_path = preview_path_for(ctx.output_root, ctx.job_id)
                response = node_proxy_rpc(
                    "ps.batchplay.execute_confirmed",
                    {
                        "job_id": ctx.job_id,
                        "descriptors": arguments.get("descriptors")
                        or ([arguments["descriptor"]] if arguments.get("descriptor") else []),
                        "output_path": preview_path.as_posix(),
                        "confirm_write": True,
                    },
                )
                if "result" in response:
                    payload = response["result"]
                    executed = bool(payload.get("executed"))
                    bridge_kind = "node_proxy_uxp"
                    preview = str(payload.get("preview_path") or "").strip()
                    if preview:
                        preview_files.append(
                            Path(preview).relative_to(self.repo_root).as_posix()
                            if Path(preview).is_absolute()
                            else preview
                        )
                    layers_snapshot = [dict(item) for item in payload.get("layers_snapshot") or []]
                    history_state = payload.get("history_state")
                    host_info = dict(payload.get("photoshop_host") or {})
                    uxp_status = {"connected": True, "method": "ps.batchplay.execute_confirmed"}
                else:
                    errors.append("Node Proxy did not return an execution result.")
            except Exception as exc:
                errors.append(f"Node Proxy execute_confirmed failed: {type(exc).__name__}")
        elif not ctx.dry_run:
            errors.append("Photoshop / UXP / Node Proxy is not available on this workstation.")
        else:
            bridge_kind = "dry_run"
            warnings.append("Dry-run confirmed execution returned a plan only.")

        manifest = _make_manifest(
            ctx,
            input_summary={"descriptor_count": validation_result.get("descriptor_count", 0)},
            output_files=preview_files,
            preview_files=preview_files,
            source_files=["<active_document>"],
            photoshop_available=proxy["uxp_client_connected"],
            bridge_kind=bridge_kind,
            node_proxy_status=proxy["status"],
            uxp_status=uxp_status,
            photoshop_host=host_info,
            layers_snapshot=layers_snapshot,
            history_state=history_state,
            descriptor_summary=descriptors,
            validation_result=validation_result,
            status="ok" if executed or ctx.dry_run else "not_available",
            warnings=warnings,
            errors=errors,
        )
        return make_result(
            ok=ctx.dry_run or (executed and not errors),
            bridge="photoshop",
            action="batchplay_execute_confirmed",
            message="Confirmed BatchPlay execution completed."
            if executed
            else (
                "Confirmed BatchPlay dry-run staged."
                if ctx.dry_run
                else "Confirmed BatchPlay execution unavailable."
            ),
            details={
                "job_id": ctx.job_id,
                "bridge_kind": bridge_kind,
                "descriptor_id": descriptors[0]["descriptor_id"] if descriptors else None,
                "executed": executed,
                "dry_run": ctx.dry_run,
                "confirmation_required": True,
                "history_state": history_state,
                "preview_path": preview_files[0] if preview_files else None,
                "layers_snapshot": layers_snapshot,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
                "evidence_manifest": manifest,
                "validation_result": validation_result,
            },
            warnings=warnings,
            next_steps=[
                "Review preview_path and layers_snapshot before a second corrective pass.",
                "Do not run outside sandbox copies.",
            ],
        )

    def _planned_write(
        self, tool_name: str, arguments: dict[str, Any], *, action: str, summary: dict[str, Any]
    ) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, tool_name)
        if not ctx.dry_run and not ctx.requires_confirmation:
            return make_result(
                ok=False,
                bridge="photoshop",
                action=action,
                message=f"{tool_name} refused because requires_confirmation must be true when dry_run is false.",
                details={
                    "job_id": ctx.job_id,
                    "risk_level": ctx.risk_level,
                    "output_dir": ctx.output_dir,
                },
                warnings=["Photoshop write-like operations stay dry-run by default."],
                next_steps=[
                    "Repeat with dry_run=true for planning.",
                    "Use batchplay execute_confirmed only after validation and confirmation.",
                ],
            )
        warnings = ["Sandbox-safe plan only."]
        manifest = _make_manifest(
            ctx,
            input_summary=summary,
            output_files=[],
            preview_files=[],
            source_files=["<active_document>"],
            photoshop_available=False,
            bridge_kind="fallback" if ctx.bridge_kind != "mock" else "mock",
            node_proxy_status=_node_proxy_probe()["status"],
            uxp_status={},
            photoshop_host={},
            layers_snapshot=[],
            history_state=None,
            descriptor_summary=[],
            validation_result={},
            status="ok",
            warnings=warnings,
            errors=[],
        )
        return make_result(
            ok=True,
            bridge="photoshop",
            action=action,
            message=f"{tool_name} planned safely.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": manifest["bridge_kind"],
                "plan_only": True,
                "evidence_manifest": manifest,
                "evidence_path": _write_manifest_if_requested(ctx, manifest),
                **summary,
            },
            warnings=warnings,
            next_steps=["Review the EvidenceManifest before enabling any confirmed write path."],
        )

    def selection_subject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.selection.subject",
            arguments,
            action="selection_subject",
            summary={"source_layer_id": arguments.get("source_layer_id")},
        )

    def layer_rename(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.rename",
            arguments,
            action="layer_rename",
            summary={
                "layer_id": arguments.get("layer_id"),
                "layer_name": arguments.get("layer_name"),
            },
        )

    def layer_move(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.move",
            arguments,
            action="layer_move",
            summary={
                "layer_id": arguments.get("layer_id"),
                "target_index": arguments.get("target_index"),
            },
        )

    def layer_visibility(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.visibility",
            arguments,
            action="layer_visibility",
            summary={"layer_id": arguments.get("layer_id"), "visible": arguments.get("visible")},
        )

    def disabled_write(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, tool_name)
        return make_result(
            ok=False,
            bridge="photoshop",
            action=tool_name.rsplit(".", 1)[-1],
            message=f"{tool_name} is intentionally disabled.",
            details={
                "job_id": ctx.job_id,
                "risk_level": ctx.risk_level,
                "bridge_kind": ctx.bridge_kind,
                "status": "disabled",
            },
            warnings=[
                "Confirmed-write and destructive Photoshop operations stay disabled by default unless they route through the typed node_proxy_uxp path."
            ],
            next_steps=[
                "Use ps.batchplay.validate now.",
                "Use ps.batchplay.execute_confirmed only for allowed sandbox-only descriptors.",
            ],
        )

    def get_preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.get_preview")
        max_side = int(arguments.get("max_side", 1024))
        include_base64 = bool(arguments.get("include_base64", True))
        preview_path = preview_path_for(ctx.output_root, ctx.job_id)
        manifest_path = manifest_path_for(
            ctx.evidence_dir, _safe_name("ps.preview.export"), ctx.job_id
        )
        preview_available = False
        real_output_verified = False
        artifact: dict[str, Any] | None = None
        warnings: list[str] = []
        if preview_path.is_file() and manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                real_output_verified = bool(
                    manifest.get("validation_result", {}).get("real_output_verified")
                ) and not any(
                    bool(item.get("placeholder"))
                    for item in manifest.get("output_artifacts", [])
                    if isinstance(item, dict)
                )
                if real_output_verified:
                    raw_artifact = build_output_artifact(
                        preview_path,
                        repo_root=self.repo_root,
                        document_name=None,
                    )
                    artifact = {
                        key: raw_artifact.get(key)
                        for key in (
                            "relative_path",
                            "format",
                            "bytes",
                            "sha256",
                            "width",
                            "height",
                        )
                    }
                    preview_available = True
            except (OSError, ValueError) as exc:
                warnings.append(f"Preview evidence could not be verified: {type(exc).__name__}")

        base64_data: str | None = None
        if preview_available and include_base64:
            data = preview_path.read_bytes()
            if len(data) <= 8 * 1024 * 1024:
                base64_data = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            else:
                warnings.append("Verified preview exceeds the 8 MiB base64 response limit.")
        details = {
            "job_id": ctx.job_id,
            "max_side": max_side,
            "include_base64": include_base64,
            "preview_available": preview_available,
            "real_output_verified": real_output_verified,
            "artifact": artifact,
            "base64": base64_data,
            "current_document_match_verified": False,
            "fabricated_preview": False,
        }
        return make_result(
            ok=preview_available,
            bridge="photoshop",
            action="get_preview",
            message=(
                "Verified sandbox preview returned."
                if preview_available
                else "No verified real Photoshop preview is available for this job."
            ),
            details=details,
            warnings=warnings,
            next_steps=[
                "Run ps.preview.export with the same job_id and explicit sandbox write confirmation.",
                "Call ps.get_preview again only after real_output_verified=true evidence exists.",
            ],
        )

    def get_state(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.get_state")
        include_layers = bool(arguments.get("include_layers", True))
        lightweight = bool(arguments.get("lightweight", True))
        info = self.document_info({**arguments, "job_id": ctx.job_id})
        info_details = dict(info.get("details") or {})
        layers_result = (
            self.layers_list({**arguments, "job_id": ctx.job_id}) if include_layers else None
        )
        layer_details = dict((layers_result or {}).get("details") or {})
        bridge_kind = str(info_details.get("bridge_kind") or "not_available")
        live_state_verified = bool(info.get("ok")) and bridge_kind in {"com", "node_proxy_uxp"}
        layers_verified = not include_layers or (
            bool((layers_result or {}).get("ok"))
            and str(layer_details.get("bridge_kind") or "") in {"com", "node_proxy_uxp"}
        )
        ok = live_state_verified and layers_verified
        document = dict(info_details.get("document") or {}) if live_state_verified else {}
        layer_rows = list(layer_details.get("layers") or []) if layers_verified else []
        active_layer_id = str(document.get("active_layer_id") or "")
        active_layer = next(
            (item for item in layer_rows if str(item.get("id") or "") == active_layer_id), None
        )
        state = {
            "job_id": ctx.job_id,
            "document": document,
            "layer_count": len(layer_rows) if include_layers and layers_verified else None,
            "active_layer": active_layer,
            "lightweight": lightweight,
            "bridge_kind": bridge_kind,
            "live_state_verified": live_state_verified,
            "layers_verified": layers_verified,
            "history_available": False,
            "simulated_state_returned": False,
        }
        warnings = [str(item) for item in info.get("warnings") or []]
        warnings.extend(str(item) for item in (layers_result or {}).get("warnings") or [])
        return make_result(
            ok=ok,
            bridge="photoshop",
            action="get_state",
            message=(
                "Verified live Photoshop state returned."
                if ok
                else "Live Photoshop state is unavailable; no mock state was returned."
            ),
            details=state,
            warnings=warnings,
            next_steps=[
                "Start an authorized Photoshop session and connect UXP, or open a document for COM readback.",
                "Retry ps.get_state and require live_state_verified=true before accepting evidence.",
            ],
        )
