from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CreativeAdapter,
    ProbeResult,
    ValidationReport,
)
from starbridge_mcp.adapters.photoshop.node_proxy_client import bridge_status, rpc
from starbridge_mcp.domain.models import JobError, validate_relative_path
from starbridge_mcp.storage.artifact_store import ArtifactStore
from starbridge_mcp.storage.asset_store import file_sha256
from starbridge_mcp.storage.atomic_json import atomic_write_json, read_json

ProxyStatusReader = Callable[[], dict[str, Any]]
ProxyRpcRunner = Callable[..., dict[str, Any]]

_OPERATIONS = frozenset(
    {
        "validate-source",
        "probe-session",
        "inspect-session",
        "execute-production",
        "verify-output",
    }
)
_OUTPUT_SPECS = {
    "png": ("photoshop-preview.png", "photoshop-preview"),
    "jpeg": ("photoshop-preview.jpg", "photoshop-preview"),
    "psd": ("photoshop-copy.psd", "photoshop-document"),
    "subject": ("photoshop-subject.png", "photoshop-subject"),
}
_SAFE_VERSION = re.compile(r"^[0-9A-Za-z._ -]{1,32}$")


class PhotoshopWorkflowAdapter(CreativeAdapter):
    """Fixed Photoshop production recipe routed through the local UXP proxy.

    The adapter never accepts arbitrary BatchPlay descriptors. Paths are derived from
    managed Project and Artifact roots, while the proxy performs an independent path
    check before forwarding the fixed recipe to UXP.
    """

    adapter_id = "photoshop-production"

    def __init__(
        self,
        *,
        status_reader: ProxyStatusReader = bridge_status,
        rpc_runner: ProxyRpcRunner = rpc,
    ) -> None:
        self.status_reader = status_reader
        self.rpc_runner = rpc_runner

    @staticmethod
    def _operation(context: AdapterContext) -> str:
        return str(context.step.input_data.get("operation") or "validate-source")

    @staticmethod
    def _state_path(context: AdapterContext) -> Path:
        return context.app_paths.jobs / context.job_id / "photoshop-runtime.json"

    @staticmethod
    def _managed_source(context: AdapterContext) -> Path:
        relative = validate_relative_path(
            str(context.step.input_data.get("sourceAssetRelativePath") or "")
        )
        candidate = (context.app_paths.root / relative).resolve(strict=True)
        projects_root = context.app_paths.projects.resolve(strict=True)
        try:
            candidate.relative_to(projects_root)
        except ValueError as exc:
            raise ValueError("Photoshop source must stay inside the managed project root") from exc
        if not candidate.is_file() or candidate.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("Photoshop source must be one managed PNG or JPEG file")
        expected_hash = str(context.step.input_data.get("sourceAssetSha256") or "")
        if expected_hash and file_sha256(candidate) != expected_hash:
            raise ValueError("Photoshop source hash no longer matches the approved plan")
        return candidate

    @staticmethod
    def _safe_host(raw: dict[str, Any]) -> dict[str, str]:
        version = str(raw.get("version") or "unknown")
        return {
            "app": "Photoshop",
            "version": version if _SAFE_VERSION.fullmatch(version) else "unknown",
        }

    @staticmethod
    def _result_payload(response: dict[str, Any]) -> dict[str, Any] | None:
        payload = response.get("result")
        return dict(payload) if isinstance(payload, dict) else None

    def probe(self, context: AdapterContext) -> ProbeResult:
        return ProbeResult(
            available=True,
            connection_state="adapter_available",
            message="Photoshop 固定工作流适配器可用；真实会话将在只读步骤中探测。",
        )

    def plan(self, context: AdapterContext) -> dict[str, Any]:
        operation = self._operation(context)
        return {
            "operation": operation,
            "writes": operation == "execute-production",
            "safeRootRef": "starbridge-app-data/artifacts",
            "fixedRecipe": True,
            "arbitraryBatchPlay": False,
            "sourceOverwrite": False,
        }

    def validate(self, context: AdapterContext) -> ValidationReport:
        operation = self._operation(context)
        if operation not in _OPERATIONS:
            return ValidationReport(
                ok=False,
                error=JobError(
                    code="invalid_photoshop_operation", message="Photoshop 工作流步骤无效。"
                ),
            )
        try:
            self._managed_source(context)
        except (OSError, ValueError):
            return ValidationReport(
                ok=False,
                error=JobError(
                    code="photoshop_source_invalid",
                    message="Photoshop 源素材缺失、已变化或不在项目安全目录。",
                    next_steps=("重新导入一张 PNG 或 JPEG 后建立新任务。",),
                ),
            )
        if operation == "verify-output" and not self._state_path(context).is_file():
            return ValidationReport(
                ok=False,
                error=JobError(
                    code="photoshop_runtime_missing", message="没有可验证的 Photoshop 执行记录。"
                ),
            )
        return ValidationReport(ok=True)

    def _validate_source(self, context: AdapterContext) -> AdapterResult:
        source = self._managed_source(context)
        return AdapterResult(
            status="completed",
            output={
                "sourceHashVerified": True,
                "managedProjectSource": True,
                "mediaType": "image/png" if source.suffix.lower() == ".png" else "image/jpeg",
            },
        )

    def _probe_session(self) -> AdapterResult:
        status = self.status_reader()
        connected = bool(
            status.get("ok")
            and status.get("node_proxy_running")
            and status.get("uxp_client_connected")
            and status.get("photoshop_host_seen")
        )
        if not connected:
            return AdapterResult(
                status="needs_user",
                output={
                    "message": "尚未连接 Photoshop UXP。请启动本机代理、打开已授权 Photoshop 并连接 StarBridge 插件后继续。",
                    "nodeProxyRunning": bool(status.get("node_proxy_running")),
                    "uxpClientConnected": bool(status.get("uxp_client_connected")),
                },
                warnings=("未执行任何 Photoshop 写入。",),
            )
        return AdapterResult(
            status="completed",
            output={
                "connectionVerified": True,
                "host": self._safe_host(dict(status.get("photoshop_host") or {})),
            },
        )

    def _inspect_session(self, context: AdapterContext) -> AdapterResult:
        response = self.rpc_runner("ps.document.info", {"job_id": context.job_id}, timeout=8)
        payload = self._result_payload(response)
        document = dict((payload or {}).get("document") or {})
        if not payload or not payload.get("ok") or not document:
            return AdapterResult(
                status="needs_user",
                output={"message": "Photoshop 中没有可用的活动文档。请打开目标文档后继续。"},
                warnings=("活动文档只读取脱敏尺寸和图层数量。",),
            )
        summary = {
            "width": max(0, int(document.get("width") or 0)),
            "height": max(0, int(document.get("height") or 0)),
            "layerCount": max(0, int(document.get("layer_count") or 0)),
            "resolution": max(0, int(document.get("resolution") or 0)),
            "host": self._safe_host(dict(payload.get("photoshop_host") or {})),
        }
        atomic_write_json(
            self._state_path(context),
            {
                "schemaVersion": 1,
                "session": summary,
                "outputs": [],
                "sourcePathPersisted": False,
                "documentNamePersisted": False,
                "layerNamesPersisted": False,
            },
        )
        return AdapterResult(status="completed", output={"session": summary})

    @staticmethod
    def _requested_formats(context: AdapterContext) -> tuple[str, ...]:
        values = context.step.input_data.get("outputFormats") or ["png", "jpeg", "psd"]
        return tuple(str(item) for item in values)

    def _execute_production(self, context: AdapterContext) -> AdapterResult:
        source = self._managed_source(context)
        store = ArtifactStore(context.app_paths.artifacts)
        formats = self._requested_formats(context)
        requested = list(formats)
        if bool(context.step.input_data.get("exportSubject")):
            requested.append("subject")
        output_paths: dict[str, Path] = {}
        for output_format in requested:
            basename, _kind = _OUTPUT_SPECS[output_format]
            output_paths[output_format] = store.allocate_path(
                context.project_id, context.job_id, basename
            )
        params = {
            "job_id": context.job_id,
            "confirm_write": True,
            "source_path": str(source),
            "source_sha256": str(context.step.input_data.get("sourceAssetSha256") or ""),
            "outputs": {key: str(value) for key, value in output_paths.items()},
            "canvas": dict(context.step.input_data.get("canvas") or {}),
            "adjustment": dict(context.step.input_data.get("adjustment") or {}),
            "export_subject": bool(context.step.input_data.get("exportSubject")),
        }
        response = self.rpc_runner("ps.production.execute_confirmed", params, timeout=60)
        payload = self._result_payload(response)
        if not payload or not payload.get("executed") or payload.get("success") is False:
            errors = list((payload or {}).get("errors") or ())
            code = str(errors[0].get("code") if errors and isinstance(errors[0], dict) else "")
            return AdapterResult(
                status="cancelled" if code == "user_cancelled" else "failed",
                error=(
                    None
                    if code == "user_cancelled"
                    else JobError(
                        code="photoshop_execution_failed",
                        message="Photoshop 受控副本没有完成，原始文档未被覆盖。",
                        retryable=False,
                        next_steps=("检查 Photoshop 模态状态和插件连接后建立新任务。",),
                    )
                ),
                warnings=("代理会清理应用拥有的临时输出；不会删除源文件。",),
            )
        artifacts = []
        for output_format, path in output_paths.items():
            if not path.is_file():
                return AdapterResult(
                    status="failed",
                    error=JobError(
                        code="photoshop_output_missing",
                        message="Photoshop 报告完成，但预期交付文件不存在。",
                    ),
                )
            artifacts.append(
                store.register(
                    context.project_id,
                    context.job_id,
                    path,
                    kind=_OUTPUT_SPECS[output_format][1],
                )
            )
        state = read_json(self._state_path(context))
        state["outputs"] = [
            {
                "artifactId": artifact.artifact_id,
                "basename": artifact.basename,
                "sha256": artifact.sha256,
                "sizeBytes": artifact.size_bytes,
            }
            for artifact in artifacts
        ]
        state["sandboxCopy"] = bool(payload.get("sandbox_copy"))
        state["nativeReopenValidated"] = bool(payload.get("native_reopen_validated"))
        state["rollbackSupported"] = bool(payload.get("rollback_supported"))
        atomic_write_json(self._state_path(context), state)
        return AdapterResult(
            status="completed",
            output={
                "sandboxCopy": bool(payload.get("sandbox_copy")),
                "sourceOverwritten": False,
                "artifactCount": len(artifacts),
                "nativeReopenValidated": bool(payload.get("native_reopen_validated")),
                "rollbackSupported": bool(payload.get("rollback_supported")),
            },
            artifacts=tuple(artifacts),
            warnings=tuple(str(item) for item in payload.get("warnings") or ()),
        )

    def _verify_output(self, context: AdapterContext) -> AdapterResult:
        state = read_json(self._state_path(context))
        rows = list(state.get("outputs") or ())
        requires_native_reopen = any(
            str(row.get("basename") or "").lower().endswith(".psd")
            for row in rows
            if isinstance(row, dict)
        )
        if requires_native_reopen and state.get("nativeReopenValidated") is not True:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="photoshop_native_reopen_unverified",
                    message="Photoshop PSD delivery was not verified by a native reopen.",
                ),
            )
        artifact_dir = ArtifactStore(context.app_paths.artifacts).job_directory(
            context.project_id, context.job_id
        )
        verified = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            basename = str(row.get("basename") or "")
            candidate = artifact_dir / basename
            if not candidate.is_file() or file_sha256(candidate) != row.get("sha256"):
                return AdapterResult(
                    status="failed",
                    error=JobError(
                        code="photoshop_output_hash_mismatch",
                        message="Photoshop 交付文件与执行证据不一致。",
                    ),
                )
            verified += 1
        if verified < 1:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="photoshop_output_empty", message="没有可验证的 Photoshop 输出。"
                ),
            )
        return AdapterResult(
            status="completed",
            output={
                "verifiedArtifactCount": verified,
                "hashesVerified": True,
                "nativeReopenValidated": bool(state.get("nativeReopenValidated")),
                "sourcePathPersisted": False,
                "documentNamePersisted": False,
                "layerNamesPersisted": False,
            },
        )

    def execute(self, context: AdapterContext) -> AdapterResult:
        if context.cancellation.cancelled:
            return AdapterResult(status="cancelled")
        operation = self._operation(context)
        if operation == "validate-source":
            return self._validate_source(context)
        if operation == "probe-session":
            return self._probe_session()
        if operation == "inspect-session":
            return self._inspect_session(context)
        if operation == "execute-production":
            return self._execute_production(context)
        if operation == "verify-output":
            return self._verify_output(context)
        raise ValueError("unsupported Photoshop workflow operation")

    def collect_evidence(self, context: AdapterContext, result: AdapterResult) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "stepId": context.step.step_id,
            "status": result.status,
            "artifactIds": [artifact.artifact_id for artifact in result.artifacts],
            "artifactHashes": [artifact.sha256 for artifact in result.artifacts],
            "sourcePathPersisted": False,
            "documentNamePersisted": False,
            "layerNamesPersisted": False,
            "arbitraryBatchPlayAccepted": False,
        }

    def rollback(self, context: AdapterContext, result: AdapterResult) -> bool:
        # The UXP modal handler owns rollback of the duplicate document; final files are
        # promoted only after the handler reports success.
        return bool(result.output.get("rollbackSupported", True))
