from __future__ import annotations

import argparse
import base64
import hmac
import io
import ipaddress
import json
import mimetypes
import os
import signal
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, RLock, Thread, Timer, current_thread
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from starbridge_mcp.core.app_data import (
    AppDataPaths,
    append_runtime_log,
    resolve_app_data_paths,
    write_crash_diagnostic,
)
from starbridge_mcp.core.desktop_connections import (
    ConnectionSetupError,
    DesktopConnectionManager,
)
from starbridge_mcp.core.security import sanitize
from starbridge_mcp.domain.errors import (
    ConfirmationRequiredError,
    DomainValidationError,
    RecordNotFoundError,
)
from starbridge_mcp.mcp_server import SERVER_INFO, handle_request
from starbridge_mcp.storage import AssetStore, EvidenceStore, JobStore, ProjectStore
from starbridge_mcp.vectorization.engine import (
    RunConfig,
    VectorizationError,
    file_sha256,
    run_vectorization,
)
from starbridge_mcp.workflows.comfyui_generation_pipeline import (
    WORKFLOW_ID as COMFYUI_GENERATION_WORKFLOW_ID,
)
from starbridge_mcp.workflows.comfyui_generation_pipeline import (
    register_comfyui_generation_workflow,
)
from starbridge_mcp.workflows.engine import WorkflowEngine
from starbridge_mcp.workflows.photoshop_production_pipeline import (
    WORKFLOW_ID as PHOTOSHOP_PRODUCTION_WORKFLOW_ID,
)
from starbridge_mcp.workflows.photoshop_production_pipeline import (
    register_photoshop_production_workflow,
)
from starbridge_mcp.workflows.registry import WorkflowRegistry
from starbridge_mcp.workflows.vector_delivery_pipeline import (
    WORKFLOW_ID as VECTOR_DELIVERY_WORKFLOW_ID,
)
from starbridge_mcp.workflows.vector_delivery_pipeline import (
    register_vector_delivery_workflow,
)

JsonObject = dict[str, Any]
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIC_ROOT = REPO_ROOT / "examples" / "starbridge_frontend" / "dist"
LEGACY_HISTORY_PATH = REPO_ROOT / "examples" / "output" / "app_history" / "history.json"
SESSION_TOKEN_ENV = "STARBRIDGE_SESSION_TOKEN"
PARENT_PID_ENV = "STARBRIDGE_PARENT_PID"
SESSION_HEADER = "X-CreNexus-Session"
READY_PREFIX = "STARBRIDGE_READY "
MAX_REQUEST_BODY_BYTES = 1024 * 1024
VECTOR_INPUT_MAX_BYTES = 128 * 1024 * 1024
VECTOR_MODES = frozenset({"artisan", "smart", "lightweight", "exact"})
DEFAULT_DEV_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)

CATALOG_BRIDGE_TIERS: dict[str, dict[str, str]] = {
    "diagramforge": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local structured drawing workflows",
    },
    "photoshop": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local creative workflows",
    },
    "comfyui": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local ComfyUI workflows",
    },
    "autocad_dxf": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local CAD workflows",
    },
    "illustrator": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local vector workflows",
    },
    "blender": {
        "tier": "Community / Open core",
        "price_signal": "MIT published capability",
        "buyer": "Local 3D workflows",
    },
}

PRODUCT_TIERS: list[JsonObject] = [
    {
        "id": "community",
        "name": "Community 免费版",
        "audience": "Creators and developers",
        "included": [
            "Local backend",
            "safe capability discovery",
            "dry-run recipe plan",
            "Evidence preview",
        ],
        "limits": ["Local-only", "No telemetry", "Explicit confirmation for writes"],
    },
    {
        "id": "pro",
        "name": "Pro 专业版（规划中）",
        "audience": "Production creators",
        "included": [
            "Batch and folder processing",
            "Project history and recoverable tasks",
            "New private workflow enhancements",
        ],
        "limits": ["Not on sale", "No private implementation in Community builds"],
    },
    {
        "id": "enterprise",
        "name": "Enterprise 企业版（规划中）",
        "audience": "Studios and organizations",
        "included": [
            "Contract-scoped deployment",
            "Professional delivery support",
            "Enterprise customization",
        ],
        "limits": ["Requires a separate contract", "Not on sale"],
    },
]

HYBRID_EXECUTION: JsonObject = {
    "architecture_version": "starbridge.local-execution.v1",
    "policy": "All CreNexus execution remains on the user's computer; no cloud execution lane is provided.",
    "lanes": [
        {
            "id": "local_desktop",
            "label": "Local desktop lane",
            "bridges": [
                "diagramforge",
                "photoshop",
                "illustrator",
                "blender",
                "autocad_dxf",
                "jianying_capcut",
            ],
            "execution_target": "local",
            "billing_unit": "none",
            "safety": "Never uploads PSD, AI, DWG, blend, video drafts, or local project files.",
        },
        {
            "id": "local_comfyui",
            "label": "Local ComfyUI lane",
            "bridges": ["comfyui"],
            "execution_target": "local",
            "billing_unit": "none",
            "safety": "ComfyUI requests stay on the user-configured local loopback endpoint.",
        },
    ],
}


@dataclass(frozen=True)
class BackendResponse:
    status: int
    body: JsonObject | bytes
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json; charset=utf-8"


class CreNexusBackend:
    """Small REST facade over the existing CreNexus MCP handlers."""

    def __init__(
        self,
        static_root: Path | None = None,
        history_path: Path | None = None,
        *,
        app_data_dir: str | Path | None = None,
        session_credential: str | None = None,
        mode: str = "development",
        cors_allowed_origins: Iterable[str] | None = None,
        max_request_body_bytes: int = MAX_REQUEST_BODY_BYTES,
    ) -> None:
        if mode not in {"development", "desktop"}:
            raise ValueError("mode must be development or desktop")
        if mode == "desktop" and not session_credential:
            raise ValueError("desktop mode requires a session token")
        if session_credential is not None and len(session_credential) < 32:
            raise ValueError("session token must contain at least 32 characters")
        if max_request_body_bytes < 1:
            raise ValueError("max_request_body_bytes must be positive")

        self._next_id = 1
        self._history_lock = RLock()
        self._vector_lock = RLock()
        self._vector_selections: dict[str, JsonObject] = {}
        self._vector_jobs: dict[str, JsonObject] = {}
        self._shutdown_callback: Callable[[], None] | None = None
        self.mode = mode
        self._session_credential = session_credential
        self.max_request_body_bytes = max_request_body_bytes
        self.app_paths: AppDataPaths = resolve_app_data_paths(app_data_dir)
        self.project_store = ProjectStore(self.app_paths.projects)
        self.job_store = JobStore(self.app_paths.jobs)
        self.asset_store = AssetStore(self.app_paths.projects)
        self.evidence_store = EvidenceStore(self.app_paths.evidence)
        self.workflow_registry = WorkflowRegistry()
        register_vector_delivery_workflow(self.workflow_registry)
        register_comfyui_generation_workflow(self.workflow_registry)
        register_photoshop_production_workflow(self.workflow_registry)
        self.workflow_engine = WorkflowEngine(
            registry=self.workflow_registry,
            project_store=self.project_store,
            job_store=self.job_store,
            evidence_store=self.evidence_store,
            app_paths=self.app_paths,
        )
        self.connections = DesktopConnectionManager(self.app_paths)
        self.static_root = static_root or DEFAULT_STATIC_ROOT
        self.history_path = history_path or self.app_paths.history_file
        if cors_allowed_origins is None:
            cors_allowed_origins = () if mode == "desktop" else DEFAULT_DEV_ORIGINS
        self.cors_allowed_origins = frozenset(origin.rstrip("/") for origin in cors_allowed_origins)

    @property
    def auth_required(self) -> bool:
        return self._session_credential is not None

    def protect(self, value: Any) -> Any:
        protected = sanitize(value)
        if not self._session_credential:
            return protected

        def redact_secret(item: Any) -> Any:
            if isinstance(item, str):
                return item.replace(self._session_credential or "", "<REDACTED_SECRET>")
            if isinstance(item, dict):
                return {key: redact_secret(child) for key, child in item.items()}
            if isinstance(item, list):
                return [redact_secret(child) for child in item]
            if isinstance(item, tuple):
                return tuple(redact_secret(child) for child in item)
            return item

        return redact_secret(protected)

    @staticmethod
    def _error(
        status: int, code: str, message: str, *, next_steps: list[str] | None = None
    ) -> BackendResponse:
        error: JsonObject = {"code": code, "message": message}
        if next_steps:
            error["next_steps"] = next_steps
        return BackendResponse(status, {"ok": False, "error": error})

    def origin_allowed(self, origin: str | None) -> bool:
        return origin is None or origin.rstrip("/") in self.cors_allowed_origins

    def _authorization_error(
        self, path: str, headers: Mapping[str, str] | None
    ) -> BackendResponse | None:
        if not self.auth_required or path == "/api/health":
            return None
        provided = headers.get(SESSION_HEADER) if headers is not None else None
        if not provided:
            return self._error(
                401,
                "authentication_required",
                "CreNexus 本地服务需要当前桌面会话授权。",
                next_steps=["请从 CreNexus Desktop 重新连接本地服务。"],
            )
        if not hmac.compare_digest(provided, self._session_credential or ""):
            return self._error(
                403,
                "authentication_failed",
                "当前桌面会话授权无效或已过期。",
                next_steps=["请重新启动 CreNexus 本地服务。"],
            )
        return None

    def register_shutdown(self, callback: Callable[[], None]) -> None:
        self._shutdown_callback = callback

    def request_shutdown(self) -> None:
        if self._shutdown_callback is not None:
            timer = Timer(0.05, self._shutdown_callback)
            timer.daemon = True
            timer.start()

    def record_runtime_event(self, event: str, details: JsonObject | None = None) -> None:
        append_runtime_log(self.app_paths, event, self.protect(details or {}))

    def record_crash(self, error: BaseException) -> None:
        summary = str(self.protect(str(error)))
        write_crash_diagnostic(
            self.app_paths,
            error_type=type(error).__name__,
            summary=summary,
        )

    def _request_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    def _mcp(self, method: str, params: JsonObject | None = None) -> BackendResponse:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": self._request_id(),
                "method": method,
                "params": params or {},
            }
        )
        if response is None:
            return BackendResponse(204, {"ok": True})
        if "error" in response:
            code = int(response["error"].get("code") or -32603)
            status = 404 if code == -32601 else 400
            return BackendResponse(status, sanitize({"ok": False, "error": response["error"]}))
        return BackendResponse(200, sanitize({"ok": True, "data": response.get("result", {})}))

    def _tool(self, name: str, arguments: JsonObject | None = None) -> BackendResponse:
        response = self._mcp("tools/call", {"name": name, "arguments": arguments or {}})
        if response.status != 200:
            return response
        result = response.body.get("data", {})
        if not isinstance(result, dict):
            return BackendResponse(500, {"ok": False, "error": "invalid tool result"})
        payload = result.get("structuredContent", result)
        is_error = bool(result.get("isError", False))
        status = 400 if is_error else 200
        return BackendResponse(status, sanitize({"ok": not is_error, "data": payload}))

    @staticmethod
    def _one(query: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
        values = query.get(key)
        return values[0] if values else default

    @staticmethod
    def _bool(query: dict[str, list[str]], key: str, default: bool = False) -> bool:
        value = CreNexusBackend._one(query, key)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _json_body(raw_body: bytes) -> JsonObject:
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _static(self, path: str) -> BackendResponse:
        static_root = self.static_root.resolve()
        if not static_root.exists():
            return BackendResponse(
                404,
                {
                    "ok": False,
                    "error": "frontend build not found",
                    "next_steps": [
                        "Run `npm.cmd --prefix examples\\starbridge_frontend run build`."
                    ],
                },
            )

        relative = unquote(path.lstrip("/")) or "index.html"
        target = (static_root / relative).resolve()
        if target == static_root or target.is_dir():
            target = target / "index.html"
        if static_root not in (target, *target.parents):
            return BackendResponse(403, {"ok": False, "error": "static path escapes frontend root"})
        if not target.exists():
            target = static_root / "index.html"
        if not target.exists():
            return BackendResponse(404, {"ok": False, "error": "frontend index.html not found"})

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or target.suffix in {".js", ".css", ".svg"}:
            content_type = f"{content_type}; charset=utf-8"
        return BackendResponse(200, target.read_bytes(), content_type=content_type)

    def _load_history(self) -> list[JsonObject]:
        with self._history_lock:
            if not self.history_path.exists():
                return []
            try:
                payload = json.loads(self.history_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            if not isinstance(payload, list):
                return []
            return [item for item in payload if isinstance(item, dict)]

    def _save_history(self, events: list[JsonObject]) -> None:
        with self._history_lock:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.history_path.with_suffix(self.history_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self.protect(events[-100:]), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.history_path)

    @staticmethod
    def _image_preview_data_url(path: Path) -> tuple[str, int, int]:
        try:
            with Image.open(path) as opened:
                if opened.format not in {"PNG", "JPEG"}:
                    raise ValueError("unsupported_image")
                oriented = ImageOps.exif_transpose(opened).convert("RGBA")
                width, height = oriented.size
                oriented.thumbnail((720, 540), Image.Resampling.LANCZOS)
                payload = io.BytesIO()
                oriented.save(payload, format="PNG", optimize=False, compress_level=9)
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise VectorizationError(
                "unsupported_input", "请选择可读取的 PNG 或 JPEG 图片。"
            ) from exc
        encoded = base64.b64encode(payload.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}", width, height

    def _create_vector_selection(self, body: JsonObject) -> BackendResponse:
        value = body.get("input_path")
        if not isinstance(value, str) or not value.strip():
            return self._error(
                400,
                "input_required",
                "请选择一张 PNG 或 JPEG 图片。",
                next_steps=["点击“选择图片”并只选择本次要处理的一张图片。"],
            )
        path = Path(value)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not path.is_file():
            return self._error(
                400,
                "unsupported_input",
                "所选文件不是可读取的 PNG 或 JPEG 图片。",
                next_steps=["重新选择 PNG 或 JPEG 图片。"],
            )
        try:
            if path.stat().st_size > VECTOR_INPUT_MAX_BYTES:
                return self._error(
                    413,
                    "input_too_large",
                    "图片文件超过 128 MB，未载入。",
                    next_steps=["缩小图片文件后重新选择。"],
                )
            preview, width, height = self._image_preview_data_url(path)
            digest = file_sha256(path)
        except (OSError, VectorizationError) as error:
            code = error.code if isinstance(error, VectorizationError) else "input_unreadable"
            message = str(error) if isinstance(error, VectorizationError) else "图片当前无法读取。"
            return self._error(
                400,
                code,
                message,
                next_steps=["确认图片未被移动或锁定，然后重新选择。"],
            )

        selection_id = f"selection-{uuid4().hex[:16]}"
        selection: JsonObject = {
            "selection_id": selection_id,
            "path": path.resolve(),
            "file_name": path.name,
            "source_sha256": digest,
            "preview_data_url": preview,
            "width": width,
            "height": height,
            "created_at": time.time(),
        }
        with self._vector_lock:
            self._vector_selections[selection_id] = selection
            if len(self._vector_selections) > 12:
                oldest = min(
                    self._vector_selections,
                    key=lambda key: float(self._vector_selections[key]["created_at"]),
                )
                self._vector_selections.pop(oldest, None)
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "selectionId": selection_id,
                    "fileName": path.name,
                    "width": width,
                    "height": height,
                    "sourceHash": digest[:12],
                    "previewDataUrl": preview,
                },
            },
        )

    @staticmethod
    def _vector_job_public(job: JsonObject) -> JsonObject:
        response: JsonObject = {
            "jobId": job["job_id"],
            "projectId": "legacy-vectorization",
            "workflowId": "legacy-vectorization-v1",
            "status": job["status"],
            "progress": job["progress"],
            "stage": job["stage"],
            "currentStep": job["stage"],
            "mode": job["mode"],
            "createdAt": job["created_at"],
            "artifacts": [],
            "warnings": [],
            "evidenceId": None,
        }
        for key in ("completed_at", "result", "error"):
            if job.get(key) is not None:
                public_key = {
                    "completed_at": "completedAt",
                    "result": "result",
                    "error": "error",
                }[key]
                response[public_key] = job[key]
        if isinstance(job.get("result"), dict):
            response["warnings"] = list(job["result"].get("warnings") or [])
        return response

    def _record_vector_event(self, job: JsonObject, result: JsonObject) -> None:
        event = {
            "event_id": f"evt_{uuid4().hex[:12]}",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "vectorization",
            "action": "local_vectorization",
            "ok": True,
            "status": "completed",
            "mode": job["mode"],
            "source_hash": result["sourceHash"],
            "summary": f"{result['modeLabel']}已在本机完成。",
            "metrics": result["metrics"],
            "output_available": True,
        }
        events = self._load_history()
        events.append(event)
        self._save_history(events)

    def _run_vector_job(
        self,
        job_id: str,
        selection: JsonObject,
        parameters: JsonObject,
    ) -> None:
        with self._vector_lock:
            job = self._vector_jobs[job_id]
            job.update(status="running", progress=18, stage="正在本机处理图片")

        mode = str(job["mode"])
        reference_id = f"desktop-{str(selection['source_sha256'])[:10]}-{job_id[-6:]}"
        output_root = (self.app_paths.data / "vectorization").resolve()
        output_dir = output_root / reference_id / mode

        def optional_int(key: str) -> int | None:
            value = parameters.get(key)
            return int(value) if isinstance(value, int | float) else None

        def optional_float(key: str) -> float | None:
            value = parameters.get(key)
            return float(value) if isinstance(value, int | float) else None

        try:
            report = run_vectorization(
                RunConfig(
                    input_path=str(selection["path"]),
                    mode=mode,
                    reference_id=reference_id,
                    output_dir=str(output_dir),
                    output_root=str(output_root),
                    colors=optional_int("colors"),
                    max_dimension=optional_int("maxDimension"),
                    simplify_ratio=optional_float("simplifyRatio"),
                    min_region_area=optional_int("minRegionArea"),
                    alpha_threshold=optional_int("alphaThreshold"),
                )
            )
            result_preview, _, _ = self._image_preview_data_url(output_dir / "preview.png")
            vector = report["vector"]
            result: JsonObject = {
                "modeLabel": report["mode"]["label_zh"],
                "sourceHash": str(selection["source_sha256"])[:12],
                "sourcePreviewDataUrl": selection["preview_data_url"],
                "resultPreviewDataUrl": result_preview,
                "metrics": {
                    "colors": vector["color_count"],
                    "subpaths": vector["subpaths"],
                    "points": vector["points"],
                    "svgBytes": vector["svg_bytes"],
                    "elapsedSeconds": report["elapsed_seconds"],
                    "pixelMatch": (
                        report["exact_validation"]["pixel_match"]
                        if report.get("exact_validation")
                        else None
                    ),
                    "anchorReductionRatio": vector.get("anchor_reduction_ratio"),
                },
                "warnings": report["warnings"],
                "outputAvailable": True,
            }
            with self._vector_lock:
                job = self._vector_jobs[job_id]
                job.update(
                    status="completed",
                    progress=100,
                    stage="处理完成",
                    completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    result=result,
                    output_dir=output_dir,
                )
            self._record_vector_event(job, result)
        except (OSError, VectorizationError, ValueError) as error:
            code = error.code if isinstance(error, VectorizationError) else "vectorization_failed"
            message = str(error) if isinstance(error, VectorizationError) else "图片处理未完成。"
            with self._vector_lock:
                self._vector_jobs[job_id].update(
                    status="failed",
                    progress=100,
                    stage="需要处理",
                    completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    error={
                        "code": code,
                        "message": message,
                        "nextSteps": ["检查图片和参数后重新运行；原图没有被修改。"],
                    },
                )

    def _start_vector_job(self, body: JsonObject) -> BackendResponse:
        if self.mode == "desktop" and not self.connections.drawing_enabled():
            return self._error(
                409,
                "codex_association_required",
                "当前 CreNexus Desktop 会话尚未与 Codex 关联，制图任务未启动。",
                next_steps=["打开软件联动中的连接中心，完成本次 Codex 配对后重试。"],
            )
        required = ("confirm_run", "confirm_write", "confirm_export")
        if any(body.get(key) is not True for key in required):
            return self._error(
                400,
                "confirmation_required",
                "开始本机处理前需要确认执行、写入和导出。",
                next_steps=["检查参数和输出说明，再勾选本次执行确认。"],
            )
        selection_id = body.get("selection_id")
        mode = body.get("mode")
        parameters = body.get("parameters") or {}
        if not isinstance(selection_id, str):
            return self._error(400, "selection_required", "请先选择一张图片。")
        if mode not in VECTOR_MODES:
            return self._error(400, "invalid_mode", "请选择可用的 Community 矢量模式。")
        if not isinstance(parameters, dict):
            return self._error(400, "invalid_parameters", "处理参数格式无效。")
        with self._vector_lock:
            selection = self._vector_selections.get(selection_id)
        if selection is None:
            return self._error(
                404,
                "selection_expired",
                "所选图片会话已失效。",
                next_steps=["重新选择图片后再运行。"],
            )
        job_id = f"vector-{uuid4().hex[:16]}"
        job: JsonObject = {
            "job_id": job_id,
            "status": "queued",
            "progress": 6,
            "stage": "已确认，正在准备",
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "completed_at": None,
            "result": None,
            "error": None,
            "output_dir": None,
        }
        with self._vector_lock:
            self._vector_jobs[job_id] = job
        worker = Thread(
            target=self._run_vector_job,
            args=(job_id, selection, parameters),
            daemon=True,
            name=f"starbridge-{job_id}",
        )
        worker.start()
        return BackendResponse(202, {"ok": True, "data": self._vector_job_public(job)})

    def _vector_job_status(self, job_id: str) -> BackendResponse:
        with self._vector_lock:
            job = self._vector_jobs.get(job_id)
            if job is None:
                return self._error(404, "job_not_found", "没有找到这项本机任务。")
            public = self._vector_job_public(dict(job))
        return BackendResponse(200, {"ok": True, "data": public})

    def _open_vector_output(self, job_id: str) -> BackendResponse:
        with self._vector_lock:
            job = self._vector_jobs.get(job_id)
            output_dir = job.get("output_dir") if job else None
        if not isinstance(output_dir, Path) or not output_dir.is_dir():
            return self._error(
                409,
                "output_not_ready",
                "输出文件夹尚未准备好。",
                next_steps=["等待任务完成后再打开输出文件夹。"],
            )
        allowed_root = (self.app_paths.data / "vectorization").resolve()
        resolved = output_dir.resolve()
        if allowed_root not in resolved.parents:
            return self._error(403, "output_outside_safe_root", "输出目录不在安全范围内。")
        try:
            if os.name != "nt":
                raise OSError("unsupported_platform")
            os.startfile(resolved)  # type: ignore[attr-defined]
        except OSError:
            return self._error(
                500,
                "output_open_failed",
                "无法打开输出文件夹。",
                next_steps=["稍后重试，或在设置与诊断中检查应用数据目录。"],
            )
        return BackendResponse(200, {"ok": True, "data": {"opened": True}})

    def _vector_history(self) -> BackendResponse:
        stored = [
            event
            for event in reversed(self._load_history())
            if event.get("kind") == "vectorization"
        ][:20]
        events = [
            {
                "eventId": event.get("event_id"),
                "createdAt": event.get("created_at"),
                "mode": event.get("mode"),
                "summary": event.get("summary"),
                "sourceHash": event.get("source_hash"),
                "metrics": event.get("metrics", {}),
                "outputAvailable": event.get("output_available") is True,
            }
            for event in stored
        ]
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "eventCount": len(events),
                    "events": events,
                },
            },
        )

    def _workflow_catalog(self) -> BackendResponse:
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "workflows": [
                        {
                            "workflowId": VECTOR_DELIVERY_WORKFLOW_ID,
                            "name": "图片 → 精确重建 → 绘制型矢量 → 交付",
                            "capabilityStatus": "experimental",
                            "recommended": True,
                            "ordinaryCustomerRoute": True,
                            "requiresConfirmation": True,
                            "drawingModes": ["artisan", "smart", "lightweight"],
                            "imageTraceFallback": False,
                        },
                        {
                            "workflowId": COMFYUI_GENERATION_WORKFLOW_ID,
                            "name": "提示词 → 校验 → 本机 ComfyUI → 结果证据",
                            "capabilityStatus": "experimental",
                            "recommended": False,
                            "ordinaryCustomerRoute": True,
                            "requiresConfirmation": True,
                            "drawingModes": [],
                            "imageTraceFallback": False,
                        },
                        {
                            "workflowId": PHOTOSHOP_PRODUCTION_WORKFLOW_ID,
                            "name": "项目图片 → Photoshop 受控副本 → PNG / JPEG / PSD",
                            "capabilityStatus": "experimental",
                            "recommended": False,
                            "ordinaryCustomerRoute": True,
                            "requiresConfirmation": True,
                            "drawingModes": [],
                            "imageTraceFallback": False,
                        },
                    ]
                },
            },
        )

    def _create_project(self, body: JsonObject) -> BackendResponse:
        project_name = body.get("projectName") or body.get("project_name")
        workflow_id = body.get("workflowId") or body.get("workflow_id")
        description = body.get("description") or ""
        if not isinstance(project_name, str) or not project_name.strip():
            return self._error(400, "project_name_required", "请输入项目名称。")
        if workflow_id not in self.workflow_registry.workflow_ids():
            return self._error(400, "workflow_not_available", "请选择当前可用的创意工作流。")
        if not isinstance(description, str):
            return self._error(400, "invalid_description", "项目描述格式无效。")
        try:
            project = self.project_store.create(
                project_name.strip(), str(workflow_id), description.strip()
            )
        except DomainValidationError as exc:
            return self._error(400, "invalid_project", str(exc))
        return BackendResponse(201, {"ok": True, "data": project.to_dict()})

    def _list_projects(self) -> BackendResponse:
        projects = [project.to_dict() for project in self.project_store.list()]
        return BackendResponse(
            200, {"ok": True, "data": {"projectCount": len(projects), "projects": projects}}
        )

    def _get_project(self, project_id: str) -> BackendResponse:
        try:
            project = self.project_store.get(project_id)
        except (DomainValidationError, RecordNotFoundError):
            return self._error(404, "project_not_found", "没有找到这个项目。")
        return BackendResponse(200, {"ok": True, "data": project.to_dict()})

    def _import_project_asset(self, project_id: str, body: JsonObject) -> BackendResponse:
        if body.get("confirmImport") is not True and body.get("confirm_import") is not True:
            return self._error(
                400,
                "confirmation_required",
                "把素材复制到 CreNexus 项目目录前需要明确确认。",
            )
        source_path = body.get("inputPath") or body.get("input_path")
        if not isinstance(source_path, str) or not source_path.strip():
            return self._error(400, "input_required", "请选择一个要导入的文件。")
        try:
            project = self.project_store.get(project_id)
            asset = self.asset_store.import_source(project_id, source_path, confirm_import=True)
            updated = self.project_store.save(
                replace(project, source_assets=(*project.source_assets, asset))
            )
        except RecordNotFoundError:
            return self._error(404, "project_not_found", "没有找到这个项目。")
        except (ConfirmationRequiredError, DomainValidationError, OSError) as exc:
            return self._error(400, "asset_import_failed", str(exc))
        return BackendResponse(
            201,
            {
                "ok": True,
                "data": {"asset": asset.to_dict(), "project": updated.to_dict()},
            },
        )

    def _create_creative_job(self, body: JsonObject) -> BackendResponse:
        project_id = body.get("projectId") or body.get("project_id")
        workflow_id = body.get("workflowId") or body.get("workflow_id")
        if not all(isinstance(value, str) for value in (project_id, workflow_id)):
            return self._error(
                400,
                "job_fields_required",
                "创建任务需要项目和工作流。",
            )
        try:
            project = self.project_store.get(str(project_id))
            if workflow_id == VECTOR_DELIVERY_WORKFLOW_ID:
                asset_id = body.get("sourceAssetId") or body.get("source_asset_id")
                drawing_mode = body.get("drawingMode") or body.get("drawing_mode") or "artisan"
                parameters = body.get("parameters") or {}
                if not isinstance(asset_id, str):
                    return self._error(
                        400, "source_asset_required", "图片矢量工作流需要一个已导入的源素材。"
                    )
                if not isinstance(parameters, dict):
                    return self._error(400, "invalid_parameters", "任务参数格式无效。")
                source_asset = next(
                    (asset for asset in project.source_assets if asset.asset_id == asset_id), None
                )
                if source_asset is None:
                    return self._error(404, "source_asset_not_found", "项目中没有这个源素材。")
                workflow_inputs = {
                    "sourceAssetRelativePath": source_asset.relative_path,
                    "drawingMode": drawing_mode,
                    "parameters": parameters,
                }
            elif workflow_id == COMFYUI_GENERATION_WORKFLOW_ID:
                workflow_inputs = {
                    "prompt": body.get("prompt"),
                    "negativePrompt": body.get("negativePrompt") or body.get("negative_prompt"),
                    "checkpointName": body.get("checkpointName") or body.get("checkpoint_name"),
                    "width": body.get("width"),
                    "height": body.get("height"),
                    "seed": body.get("seed"),
                    "steps": body.get("steps"),
                    "cfg": body.get("cfg"),
                    "sampler": body.get("sampler"),
                    "scheduler": body.get("scheduler"),
                    "timeout": body.get("timeout"),
                    "waitSeconds": (
                        body.get("waitSeconds")
                        if "waitSeconds" in body
                        else body.get("wait_seconds")
                    ),
                }
            elif workflow_id == PHOTOSHOP_PRODUCTION_WORKFLOW_ID:
                asset_id = body.get("sourceAssetId") or body.get("source_asset_id")
                parameters = body.get("parameters") or {}
                if not isinstance(asset_id, str):
                    return self._error(
                        400, "source_asset_required", "Photoshop 工作流需要一个已导入的源素材。"
                    )
                if not isinstance(parameters, dict):
                    return self._error(400, "invalid_parameters", "任务参数格式无效。")
                source_asset = next(
                    (asset for asset in project.source_assets if asset.asset_id == asset_id), None
                )
                if source_asset is None:
                    return self._error(404, "source_asset_not_found", "项目中没有这个源素材。")

                def photoshop_value(key: str, default: Any = None) -> Any:
                    return body.get(key) if key in body else parameters.get(key, default)

                workflow_inputs = {
                    "sourceAssetRelativePath": source_asset.relative_path,
                    "sourceAssetSha256": source_asset.sha256,
                    "outputFormats": photoshop_value("outputFormats", ["png", "jpeg", "psd"]),
                    "resizeCanvas": photoshop_value("resizeCanvas", False),
                    "canvasWidth": photoshop_value("canvasWidth", 1920),
                    "canvasHeight": photoshop_value("canvasHeight", 1080),
                    "brightness": photoshop_value("brightness", 0),
                    "contrast": photoshop_value("contrast", 0),
                    "saturation": photoshop_value("saturation", 0),
                    "exportSubject": photoshop_value("exportSubject", False),
                }
            else:
                return self._error(400, "workflow_not_available", "这个工作流当前不可用。")
            job = self.workflow_engine.create_job(
                str(project_id),
                str(workflow_id),
                workflow_inputs,
            )
        except RecordNotFoundError:
            return self._error(404, "project_not_found", "没有找到这个项目。")
        except (DomainValidationError, KeyError, ValueError) as exc:
            return self._error(400, "job_plan_invalid", str(exc))
        return BackendResponse(201, {"ok": True, "data": job.to_dict()})

    def _list_creative_jobs(self) -> BackendResponse:
        jobs = [job.to_dict() for job in self.job_store.list()]
        with self._vector_lock:
            legacy = [self._vector_job_public(dict(job)) for job in self._vector_jobs.values()]
        combined = [*jobs, *legacy]
        return BackendResponse(
            200, {"ok": True, "data": {"jobCount": len(combined), "jobs": combined}}
        )

    def _get_creative_job(self, job_id: str) -> BackendResponse:
        try:
            job = self.job_store.get(job_id)
        except (DomainValidationError, RecordNotFoundError):
            with self._vector_lock:
                legacy = self._vector_jobs.get(job_id)
            if legacy is None:
                return self._error(404, "job_not_found", "没有找到这项任务。")
            return BackendResponse(200, {"ok": True, "data": self._vector_job_public(dict(legacy))})
        return BackendResponse(200, {"ok": True, "data": job.to_dict()})

    def _run_creative_job(self, job_id: str, body: JsonObject) -> BackendResponse:
        approval_ref = body.get("approvalRef") or body.get("approval_ref")
        confirm_execute = body.get("confirmExecute") is True or body.get("confirm_execute") is True
        try:
            result = self.workflow_engine.run(
                job_id,
                approval_ref=str(approval_ref) if isinstance(approval_ref, str) else None,
                confirm_execute=confirm_execute,
            )
        except RecordNotFoundError:
            return self._error(404, "job_not_found", "没有找到这项任务。")
        except DomainValidationError as exc:
            return self._error(409, "job_state_invalid", str(exc))
        status_code = 202 if result.job.status == "needs_user" else 200
        return BackendResponse(status_code, {"ok": True, "data": result.to_dict()})

    def _cancel_creative_job(self, job_id: str, body: JsonObject) -> BackendResponse:
        if body.get("confirmCancel") is not True and body.get("confirm_cancel") is not True:
            return self._error(400, "confirmation_required", "取消任务前需要明确确认。")
        try:
            job = self.workflow_engine.cancel(job_id)
        except RecordNotFoundError:
            return self._error(404, "job_not_found", "没有找到这项任务。")
        return BackendResponse(200, {"ok": True, "data": job.to_dict()})

    def _creative_job_events(self, job_id: str) -> BackendResponse:
        try:
            self.job_store.get(job_id)
        except (DomainValidationError, RecordNotFoundError):
            return self._error(404, "job_not_found", "没有找到这项任务。")
        events = [event.to_dict() for event in self.job_store.events(job_id)]
        return BackendResponse(
            200, {"ok": True, "data": {"eventCount": len(events), "events": events}}
        )

    def _project_delivery(self, project_id: str) -> BackendResponse:
        try:
            project = self.project_store.get(project_id)
        except (DomainValidationError, RecordNotFoundError):
            return self._error(404, "project_not_found", "没有找到这个项目。")
        artifacts = [artifact.to_dict() for artifact in project.artifacts]
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "projectId": project.project_id,
                    "projectName": project.project_name,
                    "artifacts": artifacts,
                    "evidenceIds": list(project.evidence),
                    "formats": sorted(
                        {
                            Path(artifact.basename).suffix.lower().lstrip(".").upper()
                            for artifact in project.artifacts
                            if Path(artifact.basename).suffix
                        }
                    ),
                    "fabricatedOutputs": False,
                },
            },
        )

    def _record_recipe_event(
        self, *, recipe_id: str, action: str, result: JsonObject
    ) -> JsonObject:
        quality_gates = (
            result.get("plan", {}).get("quality_gates", [])
            if isinstance(result.get("plan"), dict)
            else result.get("manifest", {}).get("quality_gates", [])
            if isinstance(result.get("manifest"), dict)
            else result.get("quality_gates", [])
            if isinstance(result.get("quality_gates"), list)
            else []
        )
        event = sanitize(
            {
                "event_id": f"evt_{uuid4().hex[:12]}",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "recipe_action",
                "recipe_id": recipe_id,
                "bridge": result.get("bridge"),
                "action": action,
                "ok": bool(result.get("ok", False)),
                "status": "completed" if result.get("ok") else "failed",
                "evidence_ready": action in {"evidence", "run"} or "manifest" in result,
                "quality_gate_count": len(quality_gates),
                "execution_target": result.get("execution_target"),
                "summary": result.get("result_summary"),
            }
        )
        events = self._load_history()
        events.append(event)
        self._save_history(events)
        return event

    @staticmethod
    def _catalog_card(recipe: JsonObject) -> JsonObject:
        bridge = str(recipe.get("bridge") or "unknown")
        tier = CATALOG_BRIDGE_TIERS.get(
            bridge,
            {
                "tier": "Core",
                "price_signal": "Included workflow",
                "buyer": "Creative operators",
            },
        )
        gates = recipe.get("quality_gates", [])
        return sanitize(
            {
                "sku": f"starbridge.recipe.{recipe.get('recipe_id')}",
                "recipe_id": recipe.get("recipe_id"),
                "bridge": bridge,
                "title": str(recipe.get("recipe_id") or "recipe").replace("_", " ").title(),
                "goal": recipe.get("goal"),
                "tier": tier["tier"],
                "price_signal": tier["price_signal"],
                "buyer": tier["buyer"],
                "safe_default": bool(recipe.get("safe_default", True)),
                "writes": bool(recipe.get("writes", False)),
                "quality_gates": gates if isinstance(gates, list) else [],
                "install_state": "bundled",
            }
        )

    def _catalog(self) -> BackendResponse:
        response = self._tool("starbridge.recipe_list", {"bridge": "all"})
        if response.status != 200:
            return response
        data = response.body.get("data", {})
        recipes = data.get("recipes", []) if isinstance(data, dict) else []
        cards = [self._catalog_card(recipe) for recipe in recipes if isinstance(recipe, dict)]
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "catalog_version": "starbridge.catalog.v1",
                    "item_count": len(cards),
                    "items": cards,
                    "monetization_model": [
                        "Published recipe implementations remain Community / MIT capabilities.",
                        "Future Pro value must come from new private production workflow enhancements.",
                        "No cloud execution or metered compute billing is provided.",
                    ],
                },
            },
        )

    @staticmethod
    def _tiers() -> BackendResponse:
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": {
                    "tiers_version": "starbridge.tiers.v1",
                    "tiers": PRODUCT_TIERS,
                },
            },
        )

    @staticmethod
    def _hybrid() -> BackendResponse:
        return BackendResponse(
            200,
            {
                "ok": True,
                "data": HYBRID_EXECUTION,
            },
        )

    @staticmethod
    def _lane_for_bridge(bridge: str, execution_target: str) -> JsonObject | None:
        for lane in HYBRID_EXECUTION["lanes"]:
            if execution_target == lane["execution_target"] and bridge in lane["bridges"]:
                return lane
        return None

    def _run_recipe(self, recipe_id: str, body: JsonObject) -> BackendResponse:
        if not bool(body.get("confirm_run", False)):
            return BackendResponse(
                400,
                {
                    "ok": False,
                    "error": "confirm_run=true is required before a recipe run can be recorded",
                    "required_sequence": ["plan", "evidence", "confirm_run", "run"],
                },
            )

        plan_response = self._tool(
            "starbridge.recipe_plan", {"recipe_id": recipe_id, "dry_run": True}
        )
        if plan_response.status != 200:
            return plan_response
        plan_data = plan_response.body.get("data", {})
        if not isinstance(plan_data, dict) or not plan_data.get("ok"):
            return BackendResponse(404, {"ok": False, "error": "unknown recipe_id"})

        bridge = str(plan_data.get("bridge") or "unknown")
        requested_target = str(body.get("execution_target") or "local")
        lane = self._lane_for_bridge(bridge, requested_target)
        if lane is None:
            return BackendResponse(
                400,
                {
                    "ok": False,
                    "error": f"{bridge} does not support execution_target={requested_target}",
                    "hybrid": HYBRID_EXECUTION,
                },
            )

        plan = plan_data.get("plan", {}) if isinstance(plan_data.get("plan"), dict) else {}
        quality_gates = (
            plan.get("quality_gates", []) if isinstance(plan.get("quality_gates"), list) else []
        )
        result = sanitize(
            {
                "ok": True,
                "bridge": bridge,
                "action": "recipe_run",
                "recipe_id": recipe_id,
                "status": "completed",
                "dry_run": True,
                "confirm_run": True,
                "execution_target": requested_target,
                "execution_lane": lane["id"],
                "result_summary": "Confirmed run recorded as a safe dry-run execution request.",
                "tool_sequence": plan.get("action_plan", {}).get("tool_sequence", []),
                "quality_gates": quality_gates,
                "outputs": [
                    {
                        "label": "execution_report",
                        "materialized": False,
                        "reason": "Backend does not launch desktop software from this product UI.",
                    }
                ],
                "billing_preview": {
                    "unit": lane["billing_unit"],
                    "billable": False,
                    "metered_quantity": 0,
                },
                "next_steps": [
                    "Review the recorded event in Audit.",
                    "Use bridge-specific confirmed tools for real sandbox output.",
                ],
            }
        )
        event = self._record_recipe_event(recipe_id=recipe_id, action="run", result=result)
        return BackendResponse(200, {"ok": True, "data": result, "event": event})

    def route(
        self,
        method: str,
        target: str,
        raw_body: bytes = b"",
        *,
        headers: Mapping[str, str] | None = None,
        origin: str | None = None,
    ) -> BackendResponse:
        parsed = urlparse(target)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        method = method.upper()

        if path.startswith("/api/") and not self.origin_allowed(origin):
            return self._error(
                403,
                "origin_not_allowed",
                "该页面来源不能直接访问 CreNexus 本地服务。",
                next_steps=["请使用 CreNexus Desktop 或已配置的本地开发地址。"],
            )

        if method == "GET" and path == "/api/health":
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "service": "starbridge-backend",
                    "server": SERVER_INFO,
                    "mode": self.mode,
                    "session_required": self.auth_required,
                },
            )

        if path.startswith("/api/"):
            if authorization_error := self._authorization_error(path, headers):
                return authorization_error

        if method == "OPTIONS":
            return BackendResponse(204, {"ok": True})

        if len(raw_body) > self.max_request_body_bytes:
            return self._error(
                413,
                "request_too_large",
                "请求内容超过 CreNexus 本地服务允许的大小。",
            )

        try:
            body = self._json_body(raw_body)
        except ValueError:
            return self._error(
                400,
                "invalid_json_body",
                "请求内容必须是有效的 JSON 对象。",
            )

        if method == "POST" and path == "/api/lifecycle/shutdown":
            self.record_runtime_event("shutdown_requested")
            self.request_shutdown()
            return BackendResponse(
                202,
                {
                    "ok": True,
                    "data": {
                        "status": "stopping",
                        "message": "CreNexus 本地服务正在安全停止。",
                    },
                },
            )

        if method == "GET" and path == "/api/connections":
            return BackendResponse(200, {"ok": True, "data": self.connections.overview()})

        if method == "POST" and path == "/api/connections/codex/install":
            if self.mode != "desktop":
                return self._error(
                    409,
                    "desktop_required",
                    "只能在安装后的 CreNexus Desktop 中配置 Codex 连接器。",
                )
            try:
                installed = self.connections.install_codex_connector(
                    confirm_install=body.get("confirm_install") is True
                )
            except ConnectionSetupError as error:
                return self._error(
                    409,
                    error.code,
                    str(error),
                    next_steps=error.next_steps,
                )
            return BackendResponse(200, {"ok": True, "data": installed})

        if method == "POST" and path == "/api/connections/codex/reset":
            if body.get("confirm_reset") is not True:
                return self._error(
                    400,
                    "confirmation_required",
                    "重新关联前需要明确确认。",
                )
            reset = self.connections.reset_pairing()
            self.record_runtime_event("codex_pairing_reset")
            return BackendResponse(200, {"ok": True, "data": reset})

        if method == "POST" and path == "/api/connections/applications/pair":
            try:
                paired = self.connections.pair_application(
                    str(body.get("application_id") or ""),
                    confirm_pairing=body.get("confirm_pairing") is True,
                )
            except ConnectionSetupError as error:
                return self._error(
                    409,
                    error.code,
                    str(error),
                    next_steps=error.next_steps,
                )
            self.record_runtime_event(
                "creative_application_paired", {"application_id": paired["id"]}
            )
            return BackendResponse(200, {"ok": True, "data": paired})

        if method == "POST" and path == "/api/connections/applications/reconnect":
            try:
                reconnected = self.connections.reconnect_application(
                    str(body.get("application_id") or ""),
                    confirm_reconnect=body.get("confirm_reconnect") is True,
                )
            except ConnectionSetupError as error:
                return self._error(
                    409,
                    error.code,
                    str(error),
                    next_steps=error.next_steps,
                )
            self.record_runtime_event(
                "creative_application_reconnected",
                {"application_id": reconnected["id"]},
            )
            return BackendResponse(200, {"ok": True, "data": reconnected})

        if method == "POST" and path == "/api/connections/applications/disconnect":
            try:
                disconnected = self.connections.disconnect_application(
                    str(body.get("application_id") or ""),
                    confirm_disconnect=body.get("confirm_disconnect") is True,
                )
            except ConnectionSetupError as error:
                return self._error(
                    409,
                    error.code,
                    str(error),
                    next_steps=error.next_steps,
                )
            self.record_runtime_event(
                "creative_application_disconnected",
                {"application_id": disconnected["id"]},
            )
            return BackendResponse(200, {"ok": True, "data": disconnected})

        if method == "GET" and path == "/api/status":
            arguments: JsonObject = {
                "bridge": self._one(query, "bridge", "all"),
                "probe_executables": self._bool(query, "probe_executables", False),
            }
            if timeout := self._one(query, "timeout"):
                try:
                    arguments["timeout"] = int(timeout)
                except ValueError:
                    return BackendResponse(
                        400, {"ok": False, "error": "timeout must be an integer"}
                    )
            return self._tool("starbridge.status", arguments)

        if method == "GET" and path == "/api/capabilities":
            return self._tool(
                "starbridge.tools",
                {
                    "bridge": self._one(query, "bridge", "all"),
                    "safe_only": self._bool(query, "safe_only", False),
                },
            )

        if method == "GET" and path == "/api/tools":
            return self._mcp("tools/list")

        if method == "GET" and path == "/api/resources":
            return self._mcp("resources/list")

        if method == "GET" and path == "/api/resource":
            uri = self._one(query, "uri")
            if not uri:
                return BackendResponse(
                    400, {"ok": False, "error": "query parameter uri is required"}
                )
            return self._mcp("resources/read", {"uri": uri})

        if method == "GET" and path == "/api/recipes":
            return self._tool(
                "starbridge.recipe_list", {"bridge": self._one(query, "bridge", "all")}
            )

        if method == "GET" and path == "/api/catalog":
            return self._catalog()

        if method == "GET" and path == "/api/tiers":
            return self._tiers()

        if method == "GET" and path == "/api/hybrid":
            return self._hybrid()

        if method == "GET" and path == "/api/audit/history":
            events = list(reversed(self._load_history()))
            limit = self._one(query, "limit")
            if limit:
                try:
                    events = events[: max(0, int(limit))]
                except ValueError:
                    return BackendResponse(400, {"ok": False, "error": "limit must be an integer"})
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "data": {
                        "history_version": "starbridge.audit.v1",
                        "event_count": len(events),
                        "events": events,
                    },
                },
            )

        if method == "DELETE" and path == "/api/audit/history":
            self._save_history([])
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "data": {
                        "history_version": "starbridge.audit.v1",
                        "event_count": 0,
                        "events": [],
                    },
                },
            )

        if method == "GET" and path == "/api/bootstrap":
            capabilities = self._tool("starbridge.tools", {"safe_only": True})
            recipes = self._tool("starbridge.recipe_list", {"bridge": "all"})
            catalog = self._catalog()
            tiers = self._tiers()
            hybrid = self._hybrid()
            safe_roots = self._tool("starbridge.safe_roots", {"bridge": "all"})
            resources = self._mcp("resources/list")
            responses = [capabilities, recipes, catalog, tiers, hybrid, safe_roots, resources]
            if any(response.status != 200 for response in responses):
                return BackendResponse(
                    500,
                    {
                        "ok": False,
                        "error": "bootstrap failed",
                        "responses": [response.body for response in responses],
                    },
                )
            history = self._load_history()
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "data": {
                        "server": SERVER_INFO,
                        "capabilities": capabilities.body["data"],
                        "recipes": recipes.body["data"],
                        "catalog": catalog.body["data"],
                        "tiers": tiers.body["data"],
                        "hybrid": hybrid.body["data"],
                        "history": {
                            "history_version": "starbridge.audit.v1",
                            "event_count": len(history),
                            "events": list(reversed(history)),
                        },
                        "safe_roots": safe_roots.body["data"],
                        "resources": resources.body["data"],
                    },
                },
            )

        if method == "GET" and path == "/api/workflows":
            return self._workflow_catalog()

        if path == "/api/projects":
            if method == "GET":
                return self._list_projects()
            if method == "POST":
                return self._create_project(body)

        if path.startswith("/api/projects/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 3 and parts[:2] == ["api", "projects"] and method == "GET":
                return self._get_project(parts[2])
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                if parts[3] == "assets" and method == "POST":
                    return self._import_project_asset(parts[2], body)
                if parts[3] == "delivery" and method == "GET":
                    return self._project_delivery(parts[2])

        if path == "/api/jobs":
            if method == "GET":
                return self._list_creative_jobs()
            if method == "POST":
                return self._create_creative_job(body)

        if path.startswith("/api/jobs/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 3 and parts[:2] == ["api", "jobs"] and method == "GET":
                return self._get_creative_job(parts[2])
            if len(parts) == 4 and parts[:2] == ["api", "jobs"]:
                if parts[3] == "run" and method == "POST":
                    return self._run_creative_job(parts[2], body)
                if parts[3] == "cancel" and method == "POST":
                    return self._cancel_creative_job(parts[2], body)
                if parts[3] == "events" and method == "GET":
                    return self._creative_job_events(parts[2])

        if method == "POST" and path == "/api/vectorization/selections":
            return self._create_vector_selection(body)

        if method == "POST" and path == "/api/vectorization/jobs":
            return self._start_vector_job(body)

        if method == "GET" and path == "/api/vectorization/history":
            return self._vector_history()

        if path.startswith("/api/vectorization/jobs/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 4 and parts[:3] == ["api", "vectorization", "jobs"]:
                if method == "GET":
                    return self._vector_job_status(parts[3])
            if (
                len(parts) == 5
                and parts[:3] == ["api", "vectorization", "jobs"]
                and parts[4] == "open-output"
                and method == "POST"
            ):
                return self._open_vector_output(parts[3])

        if path.startswith("/api/recipes/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "recipes":
                recipe_id, action = parts[2], parts[3]
                arguments = dict(body)
                arguments["recipe_id"] = recipe_id
                if action == "plan" and method in {"GET", "POST"}:
                    response = self._tool("starbridge.recipe_plan", arguments)
                    if response.status == 200 and isinstance(response.body.get("data"), dict):
                        event = self._record_recipe_event(
                            recipe_id=recipe_id, action="plan", result=response.body["data"]
                        )
                        response.body["event"] = event
                    return response
                if action == "evidence" and method in {"GET", "POST"}:
                    response = self._tool("starbridge.recipe_evidence", arguments)
                    if response.status == 200 and isinstance(response.body.get("data"), dict):
                        event = self._record_recipe_event(
                            recipe_id=recipe_id, action="evidence", result=response.body["data"]
                        )
                        response.body["event"] = event
                    return response
                if action == "run" and method == "POST":
                    return self._run_recipe(recipe_id, body)

        if method == "POST" and path == "/api/tools/call":
            name = body.get("name")
            arguments = body.get("arguments") or {}
            if not isinstance(name, str):
                return BackendResponse(400, {"ok": False, "error": "body.name must be a string"})
            if not isinstance(arguments, dict):
                return BackendResponse(
                    400, {"ok": False, "error": "body.arguments must be an object"}
                )
            return self._tool(name, arguments)

        if method == "GET" and not path.startswith("/api/"):
            return self._static(path)

        return BackendResponse(404, {"ok": False, "error": f"unknown route: {method} {path}"})


def _send(
    handler: BaseHTTPRequestHandler,
    response: BackendResponse,
    backend: CreNexusBackend,
    *,
    write_body: bool = True,
) -> None:
    body = (
        b""
        if response.status == 204
        else response.body
        if isinstance(response.body, bytes)
        else json.dumps(backend.protect(response.body), ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
    )
    handler.send_response(response.status)
    handler.send_header("Content-Type", response.content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    origin = handler.headers.get("Origin")
    if origin:
        safe_origin = origin.replace("\r", "").replace("\n", "").rstrip("/")
        if safe_origin and backend.origin_allowed(safe_origin):
            handler.send_header("Access-Control-Allow-Origin", safe_origin)
            handler.send_header("Vary", "Origin")
            handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            handler.send_header("Access-Control-Allow-Headers", f"Content-Type, {SESSION_HEADER}")
    for name, value in response.headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    if write_body and response.status != 204:
        handler.wfile.write(body)


def make_handler(backend: CreNexusBackend) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _route(self, method: str, raw_body: bytes = b"", *, write_body: bool = True) -> None:
            try:
                response = backend.route(
                    method,
                    self.path,
                    raw_body,
                    headers=self.headers,
                    origin=self.headers.get("Origin"),
                )
            except Exception as exc:  # pragma: no cover - defensive process boundary
                backend.record_crash(exc)
                response = backend._error(
                    500,
                    "request_failed",
                    "CreNexus 本地服务无法完成该请求。",
                    next_steps=["请查看诊断并重新启动本地服务。"],
                )
            _send(self, response, backend, write_body=write_body)

        def _read_body(self) -> tuple[bytes, BackendResponse | None]:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return b"", None
            try:
                length = int(raw_length)
            except ValueError:
                self.close_connection = True
                return b"", backend._error(
                    400,
                    "invalid_content_length",
                    "请求的 Content-Length 无效。",
                )
            if length < 0:
                self.close_connection = True
                return b"", backend._error(
                    400,
                    "invalid_content_length",
                    "请求的 Content-Length 不能为负数。",
                )
            if length > backend.max_request_body_bytes:
                self.close_connection = True
                return b"", backend._error(
                    413,
                    "request_too_large",
                    "请求内容超过 CreNexus 本地服务允许的大小。",
                )
            if length:
                media_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip()
                if media_type.lower() != "application/json":
                    self.close_connection = True
                    return b"", backend._error(
                        415,
                        "unsupported_content_type",
                        "带请求内容的 API 调用只接受 application/json。",
                    )
            body = self.rfile.read(length)
            if len(body) != length:
                self.close_connection = True
                return b"", backend._error(
                    400,
                    "incomplete_request_body",
                    "请求内容未完整传输。",
                )
            return body, None

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._route("OPTIONS")

        def do_GET(self) -> None:  # noqa: N802
            self._route("GET")

        def do_HEAD(self) -> None:  # noqa: N802
            self._route("GET", write_body=False)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path.startswith("/api/"):
                if authorization_error := backend._authorization_error(path, self.headers):
                    _send(self, authorization_error, backend)
                    return
            body, error = self._read_body()
            if error is not None:
                _send(self, error, backend)
                return
            self._route("POST", body)

        def do_DELETE(self) -> None:  # noqa: N802
            self._route("DELETE")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def _require_loopback(host: str) -> None:
    if host.lower() == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("CreNexus backend host must be a loopback address") from exc
    if not address.is_loopback:
        raise ValueError("CreNexus backend may only bind to a loopback address")


class _LocalThreadingHttpServer(ThreadingHTTPServer):
    daemon_threads = True


class CreNexusHttpServer:
    def __init__(
        self,
        backend: CreNexusBackend,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        _require_loopback(host)
        self.backend = backend
        self._server = _LocalThreadingHttpServer((host, port), make_handler(backend))
        self._thread: Thread | None = None
        self._started = Event()
        self._stopped = Event()
        self._stop_lock = RLock()
        self.backend.register_shutdown(self.stop)

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _serve(self) -> None:
        try:
            self._server.serve_forever(poll_interval=0.1)
        except BaseException as exc:  # pragma: no cover - process boundary
            self.backend.record_crash(exc)

    def start(self) -> None:
        if self._started.is_set():
            return
        self._thread = Thread(target=self._serve, name="starbridge-http", daemon=False)
        self._thread.start()
        self._started.set()
        self.backend.record_runtime_event(
            "server_started",
            {"host": "loopback", "port": self.port, "pid": os.getpid(), "mode": self.backend.mode},
        )

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stopped.is_set():
                return
            if self._started.is_set() and self.running:
                self._server.shutdown()
            self._server.server_close()
            if self._thread is not None and self._thread is not current_thread():
                self._thread.join(timeout=5)
            self.backend.record_runtime_event("server_stopped", {"pid": os.getpid()})
            self._stopped.set()

    def ready_payload(self) -> JsonObject:
        return {
            "event": "ready",
            "host": "127.0.0.1",
            "port": self.port,
            "pid": os.getpid(),
            "mode": self.backend.mode,
            "session_required": self.backend.auth_required,
        }


# Preserve the public class names used by older local integrations while the
# visible product brand moves to CreNexus.
StarBridgeBackend = CreNexusBackend
StarBridgeHttpServer = CreNexusHttpServer


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ParentProcessMonitor:
    def __init__(
        self,
        parent_pid: int,
        on_parent_exit: Callable[[], None],
        *,
        poll_interval: float = 1.0,
    ) -> None:
        self.parent_pid = parent_pid
        self.on_parent_exit = on_parent_exit
        self.poll_interval = poll_interval
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="starbridge-parent-monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval):
            if not process_is_running(self.parent_pid):
                self.on_parent_exit()
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not current_thread():
            self._thread.join(timeout=max(1.0, self.poll_interval * 2))


def serve(
    *,
    backend: CreNexusBackend | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    parent_pid: int | None = None,
) -> int:
    active_backend = backend or CreNexusBackend()
    server = CreNexusHttpServer(active_backend, host=host, port=port)
    stop_requested = Event()
    monitor = ParentProcessMonitor(parent_pid, server.stop) if parent_pid is not None else None

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    previous_handlers: dict[int, Any] = {}
    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal_value = getattr(signal, signal_name)
            previous_handlers[signal_value] = signal.getsignal(signal_value)
            signal.signal(signal_value, request_stop)

    try:
        server.start()
        if monitor is not None:
            monitor.start()
        print(
            READY_PREFIX + json.dumps(server.ready_payload(), separators=(",", ":")),
            flush=True,
        )
        while server.running and not stop_requested.wait(0.2):
            pass
    finally:
        if monitor is not None:
            monitor.stop()
        server.stop()
        for signal_value, handler in previous_handlers.items():
            signal.signal(signal_value, handler)
    return server.port


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CreNexus local HTTP backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--app-data-dir")
    parser.add_argument("--history-path")
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--cors-origin", action="append", default=None)
    parser.add_argument("--max-request-body-bytes", type=int, default=MAX_REQUEST_BODY_BYTES)
    parser.add_argument("--session-token-env", default=SESSION_TOKEN_ENV)
    args = parser.parse_args()
    mode = "desktop" if args.desktop else "development"
    credential = os.environ.get(args.session_token_env) if args.desktop else None
    if args.desktop and not credential:
        parser.error(f"desktop mode requires a session token in {args.session_token_env}")
    if args.desktop and args.cors_origin:
        parser.error("desktop mode uses the Tauri proxy and does not accept browser CORS origins")

    parent_pid = args.parent_pid
    if parent_pid is None and os.environ.get(PARENT_PID_ENV):
        try:
            parent_pid = int(os.environ[PARENT_PID_ENV])
        except ValueError:
            parser.error(f"{PARENT_PID_ENV} must be an integer")
    if args.desktop and parent_pid is None:
        parser.error("desktop mode requires --parent-pid or STARBRIDGE_PARENT_PID")

    port = args.port if args.port is not None else (0 if args.desktop else 8765)
    history_path = Path(args.history_path) if args.history_path else None
    backend = CreNexusBackend(
        history_path=history_path,
        app_data_dir=args.app_data_dir,
        session_credential=credential,
        mode=mode,
        cors_allowed_origins=args.cors_origin,
        max_request_body_bytes=args.max_request_body_bytes,
    )
    try:
        serve(backend=backend, host=args.host, port=port, parent_pid=parent_pid)
    except Exception as exc:
        backend.record_crash(exc)
        print(
            "STARBRIDGE_ERROR "
            + json.dumps(
                {
                    "event": "startup_failed",
                    "error_type": type(exc).__name__,
                    "message": "CreNexus local backend could not start.",
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
