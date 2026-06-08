from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starbridge_mcp.core.result_schema import make_result

from .evidence import build_manifest, manifest_path_for, new_job_id, preview_path_for, write_json, write_placeholder_png
from .mock import mock_document, mock_layers, mock_probe


DESTRUCTIVE_METHODS = {
    "delete",
    "placedLayerEditContents",
    "mergeLayersNew",
    "rasterizeLayer",
    "resetAllTools",
}


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


def _resolve_output_dir(repo_root: Path, requested: str) -> Path:
    relative = Path(requested)
    if relative.is_absolute():
        raise ValueError("output_dir must be relative to the repository sandbox or output directories")
    candidate = (repo_root / relative).resolve()
    allowed_roots = [(repo_root / "sandbox").resolve(), (repo_root / "output").resolve()]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ValueError("output_dir must stay inside sandbox/ or output/")
    return candidate


def _evidence_dir_for(repo_root: Path, output_dir: Path) -> Path:
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
        requires_confirmation=_bool(arguments.get("requires_confirmation"), False),
        dry_run=_bool(arguments.get("dry_run"), True),
        writes_files=_bool(arguments.get("writes_files"), False),
        touches_user_psd=_bool(arguments.get("touches_user_psd"), False),
        bridge_kind=str(arguments.get("bridge_kind") or "auto"),
        output_dir=output_root.relative_to(repo_root).as_posix(),
        repo_root=repo_root,
        evidence_dir=evidence_dir,
        output_root=output_root,
    )


def _probe_photoshop(probe_com: bool) -> tuple[bool, dict[str, Any], Any | None]:
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
    except Exception as exc:  # pragma: no cover - Windows COM depends on host machine
        data["error"] = str(exc)
        return False, data, None


def _app_document_summary(app: Any) -> dict[str, Any]:
    document = app.Application.ActiveDocument if hasattr(app, "Application") else app.ActiveDocument
    return {
        "name": "active_document",
        "width": int(float(document.Width)),
        "height": int(float(document.Height)),
        "resolution": int(float(getattr(document, "Resolution", 72))),
        "mode": str(getattr(document, "Mode", "unknown")),
        "bits_per_channel": int(getattr(document, "BitsPerChannel", 8)),
        "layer_count": int(getattr(document.Layers, "Count", 0)),
        "color_profile": str(getattr(document, "ColorProfileName", "unknown")),
    }


def _extract_layers(container: Any, depth: int, max_layers: int, rows: list[dict[str, Any]]) -> None:
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
        type_name = str(getattr(layer, "typename", getattr(layer, "__class__", type(layer)).__name__))
        kind = "group" if "LayerSet" in type_name or "Group" in type_name else str(getattr(layer, "Kind", "layer"))
        row = {
            "id": f"{depth}-{index}",
            "name": str(getattr(layer, "Name", f"Layer {index}")),
            "kind": kind,
            "depth": depth,
            "visible": bool(getattr(layer, "Visible", True)),
            "locked": bool(getattr(layer, "AllLocked", False)),
            "opacity": int(float(getattr(layer, "Opacity", 100))),
        }
        rows.append(row)
        if row["kind"] == "group" and hasattr(layer, "Layers"):
            _extract_layers(layer, depth + 1, max_layers, rows)


def _write_manifest_if_requested(ctx: RequestContext, manifest: dict[str, Any]) -> str | None:
    if ctx.dry_run:
        return None
    target = manifest_path_for(ctx.evidence_dir, _safe_name(ctx.tool_name), ctx.job_id)
    write_json(target, manifest)
    return target.relative_to(ctx.repo_root).as_posix()


def _guard_confirmation(ctx: RequestContext, action: str) -> dict[str, Any] | None:
    if ctx.writes_files and not ctx.dry_run and not ctx.requires_confirmation:
        return make_result(
            ok=False,
            bridge="photoshop",
            action=action,
            message=f"{ctx.tool_name} refused because requires_confirmation must be true when dry_run is false.",
            details={"job_id": ctx.job_id, "risk_level": ctx.risk_level, "output_dir": ctx.output_dir},
            warnings=["Writes are sandboxed and disabled by default."],
            next_steps=["Repeat the call with dry_run=true for planning or set requires_confirmation=true for sandbox output."],
        )
    return None


class PhotoshopBridgeAdapter:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def probe(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.probe")
        if ctx.bridge_kind == "mock":
            probe = mock_probe()
            return make_result(
                ok=True,
                bridge="photoshop",
                action="probe",
                message="Photoshop mock probe completed.",
                details={"job_id": ctx.job_id, "bridge_kind": "mock", **probe},
                warnings=probe["warnings"],
                next_steps=["Switch bridge_kind to auto or com on a Windows machine with Photoshop for live probing."],
            )
        ok, data, _app = _probe_photoshop(probe_com=_bool(arguments.get("probe_com"), True))
        warnings = []
        if not ok:
            warnings.append("Photoshop COM was not available; only fallback probe data is available.")
        return make_result(
            ok=True,
            bridge="photoshop",
            action="probe",
            message="Photoshop probe completed.",
            details={"job_id": ctx.job_id, "bridge_kind": "com" if ok else "fallback", **data},
            warnings=warnings,
            next_steps=["Use ps.document.info or ps.layers.list for active-document inspection.", "Keep preview export in dry_run until confirmation is explicit."],
        )

    def document_info(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.document.info")
        if ctx.bridge_kind == "mock":
            document = mock_document()
            return make_result(
                ok=True,
                bridge="photoshop",
                action="document_info",
                message="Mock Photoshop document summary returned.",
                details={"job_id": ctx.job_id, "bridge_kind": "mock", "document": document},
                warnings=["Mock bridge does not inspect a live Photoshop document."],
                next_steps=["Switch bridge_kind to auto or com for a real active-document probe."],
            )
        available, data, app = _probe_photoshop(probe_com=True)
        if not available or not data.get("active_document") or app is None:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="document_info",
                message="No active Photoshop document is available.",
                details={"job_id": ctx.job_id, "bridge_kind": "fallback", "probe": data},
                warnings=["Document inspection requires an already-open Photoshop session."],
                next_steps=["Open Photoshop with the target document locally and retry.", "Use bridge_kind=mock for sandbox tests."],
            )
        document = _app_document_summary(app)
        return make_result(
            ok=True,
            bridge="photoshop",
            action="document_info",
            message="Active Photoshop document summary returned.",
            details={"job_id": ctx.job_id, "bridge_kind": "com", "document": document},
            warnings=[],
            next_steps=["Use ps.layers.list to inspect the current layer tree.", "Use ps.preview.export in dry_run before exporting any preview."],
        )

    def layers_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.layers.list")
        max_layers = int(arguments.get("max_layers") or 200)
        if ctx.bridge_kind == "mock":
            layers = mock_layers()[:max_layers]
            return make_result(
                ok=True,
                bridge="photoshop",
                action="layers_list",
                message="Mock Photoshop layer list returned.",
                details={"job_id": ctx.job_id, "bridge_kind": "mock", "layer_count": len(layers), "layers": layers},
                warnings=["Mock bridge does not inspect a live Photoshop document."],
                next_steps=["Switch bridge_kind to auto or com for a real active-document layer tree."],
            )
        available, data, app = _probe_photoshop(probe_com=True)
        if not available or not data.get("active_document") or app is None:
            return make_result(
                ok=False,
                bridge="photoshop",
                action="layers_list",
                message="No active Photoshop document is available for layer inspection.",
                details={"job_id": ctx.job_id, "bridge_kind": "fallback", "probe": data},
                warnings=["Layer inspection requires an already-open Photoshop session."],
                next_steps=["Open Photoshop with the target document locally and retry.", "Use bridge_kind=mock for sandbox tests."],
            )
        document = app.Application.ActiveDocument if hasattr(app, "Application") else app.ActiveDocument
        rows: list[dict[str, Any]] = []
        _extract_layers(document, 0, max_layers, rows)
        return make_result(
            ok=True,
            bridge="photoshop",
            action="layers_list",
            message="Active Photoshop layer list returned.",
            details={"job_id": ctx.job_id, "bridge_kind": "com", "layer_count": len(rows), "layers": rows},
            warnings=[] if rows else ["The active document has no readable layers."],
            next_steps=["Use ps.preview.export in dry_run to stage a review preview.", "Reserve write actions for confirmed sandbox-only flows."],
        )

    def _planned_write(self, tool_name: str, arguments: dict[str, Any], *, action: str, summary: dict[str, Any], disabled_message: str) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, tool_name)
        warnings: list[str] = []
        errors: list[str] = []
        if not ctx.dry_run and not ctx.requires_confirmation:
            return make_result(
                ok=False,
                bridge="photoshop",
                action=action,
                message=f"{tool_name} refused because requires_confirmation must be true when dry_run is false.",
                details={"job_id": ctx.job_id, "risk_level": ctx.risk_level, "output_dir": ctx.output_dir},
                warnings=["Photoshop write-like operations stay dry-run by default in v1."],
                next_steps=["Repeat the call with dry_run=true for planning or set requires_confirmation=true for a future confirmed path."],
            )
        if ctx.bridge_kind not in {"mock", "auto", "com"}:
            warnings.append(f"Bridge kind {ctx.bridge_kind} is reserved for future Photoshop bridge implementations.")
        if ctx.bridge_kind == "mock":
            warnings.append("Mock bridge returned a sandbox-safe plan only.")
        elif not ctx.dry_run:
            errors.append(disabled_message)
        manifest = build_manifest(
            job_id=ctx.job_id,
            tool_name=tool_name,
            risk_level=ctx.risk_level,
            requires_confirmation=ctx.requires_confirmation,
            dry_run=ctx.dry_run,
            input_summary=summary,
            output_files=[],
            preview_files=[],
            source_files=["<active_document>"],
            photoshop_available=ctx.bridge_kind == "mock",
            bridge_kind=ctx.bridge_kind if ctx.bridge_kind == "mock" else "fallback",
            status="ok" if not errors else "disabled",
            warnings=warnings,
            errors=errors,
        ).to_dict()
        manifest_path = _write_manifest_if_requested(ctx, manifest)
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action=action,
            message=f"{tool_name} planned safely." if not errors else f"{tool_name} is disabled for real writes in v1.",
            details={
                "job_id": ctx.job_id,
                "bridge_kind": ctx.bridge_kind if ctx.bridge_kind == "mock" else "fallback",
                "plan_only": True,
                "evidence_manifest": manifest,
                "evidence_path": manifest_path,
                **summary,
            },
            warnings=warnings,
            next_steps=["Review the EvidenceManifest before enabling any confirmed write path.", "Upgrade the UXP or node-proxy path before attempting live Photoshop writes."],
        )

    def selection_subject(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.selection.subject",
            arguments,
            action="selection_subject",
            summary={"source_layer_id": arguments.get("source_layer_id")},
            disabled_message="Live subject selection is reserved for a future UXP-backed bridge.",
        )

    def layer_rename(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.rename",
            arguments,
            action="layer_rename",
            summary={"layer_id": arguments.get("layer_id"), "layer_name": arguments.get("layer_name")},
            disabled_message="Live layer rename is reserved for a future UXP-backed bridge.",
        )

    def layer_move(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.move",
            arguments,
            action="layer_move",
            summary={"layer_id": arguments.get("layer_id"), "target_index": arguments.get("target_index")},
            disabled_message="Live layer move is reserved for a future UXP-backed bridge.",
        )

    def layer_visibility(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._planned_write(
            "ps.layer.visibility",
            arguments,
            action="layer_visibility",
            summary={"layer_id": arguments.get("layer_id"), "visible": arguments.get("visible")},
            disabled_message="Live layer visibility changes are reserved for a future UXP-backed bridge.",
        )

    def preview_export(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.preview.export")
        refusal = _guard_confirmation(ctx, "preview_export")
        if refusal is not None:
            return refusal
        preview_files: list[str] = []
        warnings: list[str] = []
        errors: list[str] = []
        photoshop_available = False
        actual_bridge = ctx.bridge_kind
        if ctx.bridge_kind == "mock":
            if not ctx.dry_run:
                preview_path = preview_path_for(ctx.output_root, ctx.job_id)
                write_placeholder_png(preview_path)
                preview_files.append(preview_path.relative_to(ctx.repo_root).as_posix())
            warnings.append("Preview was generated by the mock bridge, not by Photoshop.")
        else:
            available, data, app = _probe_photoshop(probe_com=True)
            photoshop_available = available
            actual_bridge = "com" if available else "fallback"
            if not available or not data.get("active_document") or app is None:
                errors.append("No active Photoshop document is available for preview export.")
            elif not ctx.dry_run:
                preview_path = preview_path_for(ctx.output_root, ctx.job_id)
                write_placeholder_png(preview_path)
                preview_files.append(preview_path.relative_to(ctx.repo_root).as_posix())
                warnings.append("COM fallback preview export currently writes a placeholder preview while the UXP bridge is still pending.")
        status = "ok" if not errors else "blocked"
        manifest = build_manifest(
            job_id=ctx.job_id,
            tool_name=ctx.tool_name,
            risk_level=ctx.risk_level,
            requires_confirmation=ctx.requires_confirmation,
            dry_run=ctx.dry_run,
            input_summary={"output_dir": ctx.output_dir, "format": str(arguments.get("format") or "png")},
            output_files=preview_files,
            preview_files=preview_files,
            source_files=["<active_document>"] if ctx.touches_user_psd else [],
            photoshop_available=photoshop_available or ctx.bridge_kind == "mock",
            bridge_kind=actual_bridge,
            status=status,
            warnings=warnings,
            errors=errors,
        ).to_dict()
        manifest_path = _write_manifest_if_requested(ctx, manifest)
        details = {
            "job_id": ctx.job_id,
            "bridge_kind": actual_bridge,
            "preview_files": preview_files,
            "evidence_manifest": manifest,
            "evidence_path": manifest_path,
        }
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action="preview_export",
            message="Preview export staged." if not errors else "Preview export blocked.",
            details=details,
            warnings=warnings,
            next_steps=["Review the evidence manifest before any follow-up edit.", "Upgrade to the UXP bridge for real pixel previews from Photoshop DOM/batchPlay."],
        )

    def evidence_capture(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.evidence.capture")
        refusal = _guard_confirmation(ctx, "evidence_capture")
        if refusal is not None:
            return refusal
        available, probe, _app = _probe_photoshop(probe_com=ctx.bridge_kind != "mock")
        actual_bridge = "mock" if ctx.bridge_kind == "mock" else ("com" if available else "fallback")
        warnings = list(probe.get("warnings", [])) if isinstance(probe.get("warnings"), list) else []
        manifest = build_manifest(
            job_id=ctx.job_id,
            tool_name=ctx.tool_name,
            risk_level=ctx.risk_level,
            requires_confirmation=ctx.requires_confirmation,
            dry_run=ctx.dry_run,
            input_summary={"notes": str(arguments.get("notes") or ""), "output_dir": ctx.output_dir},
            output_files=[],
            preview_files=[],
            source_files=[str(item) for item in arguments.get("source_files") or []],
            photoshop_available=available or ctx.bridge_kind == "mock",
            bridge_kind=actual_bridge,
            status="ok",
            warnings=warnings,
            errors=[],
        ).to_dict()
        manifest_path = _write_manifest_if_requested(ctx, manifest)
        return make_result(
            ok=True,
            bridge="photoshop",
            action="evidence_capture",
            message="Evidence manifest captured.",
            details={"job_id": ctx.job_id, "bridge_kind": actual_bridge, "evidence_manifest": manifest, "evidence_path": manifest_path},
            warnings=warnings,
            next_steps=["Attach preview and layer-inspection outputs to the same job_id for iterative review."],
        )

    def batchplay_validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, "ps.batchplay.validate")
        descriptor = arguments.get("descriptor")
        descriptors = arguments.get("descriptors") or []
        if descriptor is not None:
            descriptors = [descriptor, *descriptors]
        if not isinstance(descriptors, list):
            raise ValueError("descriptors must be a list")
        warnings: list[str] = []
        errors: list[str] = []
        summaries: list[dict[str, Any]] = []
        for index, item in enumerate(descriptors, start=1):
            if not isinstance(item, dict):
                errors.append(f"Descriptor {index} must be an object.")
                continue
            method = str(item.get("_obj") or item.get("method") or "unknown")
            risk = "level_3_destructive_batch" if method in DESTRUCTIVE_METHODS else "level_1_sandbox_write"
            if method in DESTRUCTIVE_METHODS:
                warnings.append(f"Descriptor {index} uses destructive or write-heavy method {method}.")
            summaries.append({"index": index, "method": method, "risk_level": risk, "keys": sorted(item.keys())})
        if not descriptors:
            errors.append("At least one descriptor is required.")
        manifest = build_manifest(
            job_id=ctx.job_id,
            tool_name=ctx.tool_name,
            risk_level=ctx.risk_level,
            requires_confirmation=ctx.requires_confirmation,
            dry_run=ctx.dry_run,
            input_summary={"descriptor_count": len(descriptors)},
            output_files=[],
            preview_files=[],
            source_files=[],
            photoshop_available=False,
            bridge_kind=ctx.bridge_kind,
            status="ok" if not errors else "blocked",
            warnings=warnings,
            errors=errors,
        ).to_dict()
        manifest_path = _write_manifest_if_requested(ctx, manifest)
        return make_result(
            ok=not errors,
            bridge="photoshop",
            action="batchplay_validate",
            message="BatchPlay payload validated." if not errors else "BatchPlay payload validation failed.",
            details={
                "job_id": ctx.job_id,
                "descriptor_count": len(descriptors),
                "descriptors": summaries,
                "evidence_manifest": manifest,
                "evidence_path": manifest_path,
            },
            warnings=warnings,
            next_steps=["Use this validator before enabling any execute_confirmed tool.", "Keep real execution disabled until the UXP bridge and typed schemas are in place."],
        )

    def disabled_write(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ctx = _build_context(arguments, self.repo_root, tool_name)
        return make_result(
            ok=False,
            bridge="photoshop",
            action=tool_name.rsplit(".", 1)[-1],
            message=f"{tool_name} is intentionally disabled in Codex + Photoshop local advanced bridge v1.",
            details={"job_id": ctx.job_id, "risk_level": ctx.risk_level, "bridge_kind": ctx.bridge_kind, "status": "disabled"},
            warnings=["Confirmed-write and destructive Photoshop operations stay disabled by default in v1."],
            next_steps=["Use ps.batchplay.validate and evidence-first review flows now.", "Upgrade the UXP plugin and local node proxy before enabling live write tools."],
        )
