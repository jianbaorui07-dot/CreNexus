from __future__ import annotations

import hashlib
import os
import secrets
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from examples.comfy_bridge.probe import probe as probe_comfyui
from examples.comfy_bridge.workflow_agent import agent_run, generation_result
from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CreativeAdapter,
    ProbeResult,
    ValidationReport,
)
from starbridge_mcp.domain.models import JobError, validate_basename
from starbridge_mcp.storage.artifact_store import ArtifactStore
from starbridge_mcp.storage.atomic_json import atomic_write_json, read_json

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUTS = 16
SUPPORTED_OUTPUT_EXTENSIONS = {
    "gif": frozenset({".gif"}),
    "jpeg": frozenset({".jpg", ".jpeg"}),
    "png": frozenset({".png"}),
    "webp": frozenset({".webp"}),
}


class RuntimeInputVault:
    """Bounded process-memory storage for prompts and model names; never serialized."""

    def __init__(self, *, lifetime_seconds: int = 1800, max_records: int = 32) -> None:
        self.lifetime_seconds = lifetime_seconds
        self.max_records = max_records
        self._records: dict[str, tuple[float, dict[str, Any]]] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [
            reference
            for reference, (created_at, _) in self._records.items()
            if now - created_at >= self.lifetime_seconds
        ]
        for reference in expired:
            self._records.pop(reference, None)
        while len(self._records) >= self.max_records:
            oldest = min(self._records, key=lambda item: self._records[item][0])
            self._records.pop(oldest, None)

    def put(self, inputs: dict[str, Any]) -> str:
        self._prune()
        reference = f"runtime-{secrets.token_urlsafe(18)}"
        self._records[reference] = (time.monotonic(), dict(inputs))
        return reference

    def get(self, reference: str) -> dict[str, Any] | None:
        self._prune()
        record = self._records.get(reference)
        return dict(record[1]) if record else None

    def discard(self, reference: str) -> None:
        self._records.pop(reference, None)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def validate_loopback_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("ComfyUI URL must be a plain loopback HTTP origin")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("ComfyUI URL must use a loopback host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("ComfyUI URL port is invalid") from exc
    if port is None or not 1 <= port <= 65535:
        raise ValueError("ComfyUI URL must include a valid port")
    if parsed.path not in {"", "/"}:
        raise ValueError("ComfyUI URL must not contain a path")
    return f"http://{parsed.netloc}"


def _validate_generated_image_payload(basename: str, payload: bytes) -> str:
    validate_basename(basename, "output filename")
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError("ComfyUI output is empty or exceeds the safe limit")

    detected_format: str | None = None
    if payload.startswith(b"\x89PNG\r\n\x1a\n") and payload.endswith(
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    ):
        detected_format = "png"
    elif payload.startswith(b"\xff\xd8\xff") and payload.endswith(b"\xff\xd9"):
        detected_format = "jpeg"
    elif payload.startswith((b"GIF87a", b"GIF89a")) and payload.endswith(b";"):
        detected_format = "gif"
    elif (
        len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
        and int.from_bytes(payload[4:8], "little") == len(payload) - 8
    ):
        detected_format = "webp"

    suffix = Path(basename).suffix.lower()
    if detected_format is None or suffix not in SUPPORTED_OUTPUT_EXTENSIONS[detected_format]:
        raise ValueError("ComfyUI output is not a supported image matching its extension")
    return detected_format


def _fetch_output(base_url: str, image: dict[str, Any], timeout: int) -> bytes:
    filename = str(image.get("filename") or "")
    validate_basename(filename, "output filename")
    subfolder = str(image.get("subfolder") or "")
    if subfolder:
        validate_basename(subfolder, "output subfolder")
    output_type = str(image.get("type") or "output")
    if output_type not in {"output", "temp"}:
        raise ValueError("ComfyUI output type is invalid")
    query = urllib.parse.urlencode(
        {"filename": filename, "subfolder": subfolder, "type": output_type}
    )
    request = urllib.request.Request(
        f"{base_url}/view?{query}", headers={"Accept": "image/*"}, method="GET"
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        payload = response.read(MAX_OUTPUT_BYTES + 1)
    if not payload or len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError("ComfyUI output is empty or exceeds the safe limit")
    return payload


class ComfyUiAdapter(CreativeAdapter):
    adapter_id = "comfyui"

    def __init__(
        self,
        vault: RuntimeInputVault,
        *,
        probe_runner: Callable[[str, int], dict[str, Any]] = probe_comfyui,
        agent_runner: Callable[[dict[str, Any]], dict[str, Any]] = agent_run,
        result_reader: Callable[[dict[str, Any]], dict[str, Any]] = generation_result,
        output_fetcher: Callable[[str, dict[str, Any], int], bytes] = _fetch_output,
    ) -> None:
        self.vault = vault
        self.probe_runner = probe_runner
        self.agent_runner = agent_runner
        self.result_reader = result_reader
        self.output_fetcher = output_fetcher

    @staticmethod
    def _operation(context: AdapterContext) -> str:
        return str(context.step.input_data.get("operation") or "validate-workflow")

    @staticmethod
    def _runtime_ref(context: AdapterContext) -> str:
        return str(context.step.input_data.get("runtimeInputRef") or "")

    @staticmethod
    def _state_path(context: AdapterContext) -> Path:
        return context.app_paths.jobs / context.job_id / "comfyui-runtime.json"

    def _runtime_inputs(self, context: AdapterContext) -> dict[str, Any] | None:
        return self.vault.get(self._runtime_ref(context))

    @staticmethod
    def _base_url(inputs: dict[str, Any] | None = None) -> str:
        value = (
            (inputs or {}).get("comfyUrl")
            or os.environ.get("STARBRIDGE_COMFYUI_URL")
            or DEFAULT_COMFYUI_URL
        )
        return validate_loopback_url(str(value))

    @staticmethod
    def _safe_arguments(inputs: dict[str, Any], context: AdapterContext) -> dict[str, Any]:
        return {
            "workflow_type": "txt2img",
            "prompt": inputs["prompt"],
            "negative_prompt": inputs.get("negativePrompt") or "",
            "checkpoint": inputs["checkpointName"],
            "width": inputs["width"],
            "height": inputs["height"],
            "seed": inputs.get("seed"),
            "steps": inputs["steps"],
            "cfg": inputs["cfg"],
            "sampler": inputs["sampler"],
            "scheduler": inputs["scheduler"],
            "filename_prefix": f"starbridge_{context.job_id[-10:]}",
            "comfy_url": ComfyUiAdapter._base_url(inputs),
            "timeout": min(30, int(inputs.get("timeout") or 8)),
            "wait_seconds": min(5, int(inputs.get("waitSeconds") or 0)),
        }

    def probe(self, context: AdapterContext) -> ProbeResult:
        return ProbeResult(
            available=True,
            connection_state="adapter_available",
            message="ComfyUI 本机适配器可用；连接状态将在只读步骤中探测。",
        )

    def plan(self, context: AdapterContext) -> dict[str, Any]:
        operation = self._operation(context)
        return {
            "operation": operation,
            "writes": operation in {"submit-generation", "collect-results"},
            "safeRootRef": "starbridge-app-data/artifacts",
            "promptPersisted": False,
        }

    def validate(self, context: AdapterContext) -> ValidationReport:
        operation = self._operation(context)
        if operation not in {
            "validate-workflow",
            "probe-service",
            "submit-generation",
            "collect-results",
        }:
            return ValidationReport(
                ok=False,
                error=JobError(code="invalid_comfyui_operation", message="ComfyUI 步骤无效。"),
            )
        if operation in {"validate-workflow", "probe-service", "submit-generation"}:
            inputs = self._runtime_inputs(context)
            if inputs is None:
                return ValidationReport(
                    ok=False,
                    error=JobError(
                        code="runtime_input_expired",
                        message="敏感运行输入已过期，未写入磁盘。",
                        next_steps=("重新建立 ComfyUI 任务并再次确认。",),
                    ),
                )
            try:
                self._base_url(inputs)
            except ValueError:
                return ValidationReport(
                    ok=False,
                    error=JobError(
                        code="comfyui_loopback_required",
                        message="ComfyUI 只允许连接本机回环 HTTP 地址。",
                    ),
                )
        elif not self._state_path(context).is_file():
            return ValidationReport(
                ok=False,
                error=JobError(
                    code="comfyui_submission_missing", message="没有可恢复的 ComfyUI 提交记录。"
                ),
            )
        return ValidationReport(ok=True)

    def _validate_workflow(self, context: AdapterContext) -> AdapterResult:
        inputs = self._runtime_inputs(context)
        assert inputs is not None
        arguments = self._safe_arguments(inputs, context)
        arguments["confirm_run"] = False
        result = self.agent_runner(arguments)
        validation = result.get("validation") or {}
        if not result.get("ok") or not validation.get("ok"):
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="comfyui_workflow_invalid",
                    message="ComfyUI workflow dry-run 校验未通过。",
                    next_steps=("检查尺寸、采样设置和本机模型名称后重新建立任务。",),
                ),
            )
        atomic_write_json(
            self._state_path(context),
            {
                "schemaVersion": 1,
                "workflowHash": result.get("workflow_hash"),
                "validationOk": True,
                "submitted": False,
                "promptPersisted": False,
                "modelNamePersisted": False,
            },
        )
        return AdapterResult(
            status="completed",
            output={
                "workflowHash": result.get("workflow_hash"),
                "validationOk": True,
                "promptPersisted": False,
            },
            warnings=tuple(str(item) for item in result.get("warnings") or ()),
        )

    def _probe_service(self, context: AdapterContext) -> AdapterResult:
        inputs = self._runtime_inputs(context)
        assert inputs is not None
        report = self.probe_runner(self._base_url(inputs), min(15, int(inputs.get("timeout") or 8)))
        if not report.get("ok"):
            return AdapterResult(
                status="failed",
                retryable=True,
                error=JobError(
                    code="comfyui_unavailable",
                    message="本机 ComfyUI 未就绪；没有提交生成任务。",
                    retryable=True,
                    next_steps=("启动本机 ComfyUI 并确认基础节点可用后重新建立任务。",),
                ),
            )
        detected = report.get("detected") or {}
        return AdapterResult(
            status="completed",
            output={
                "connectionState": "available",
                "systemStats": detected.get("system_stats") is True,
                "objectInfo": detected.get("object_info") is True,
                "basicNodeCount": len(detected.get("basic_nodes_checked") or ()),
            },
        )

    def _submit(self, context: AdapterContext) -> AdapterResult:
        inputs = self._runtime_inputs(context)
        assert inputs is not None
        arguments = self._safe_arguments(inputs, context)
        arguments["confirm_run"] = True
        try:
            result = self.agent_runner(arguments)
        finally:
            self.vault.discard(self._runtime_ref(context))
        prompt_id = result.get("prompt_id")
        prompt_id_hash = (
            hashlib.sha256(str(prompt_id).encode("utf-8")).hexdigest() if prompt_id else None
        )
        job_status = result.get("job_status") or {}
        state = str(job_status.get("state") or "unavailable")
        submitted = result.get("submitted") is True and isinstance(prompt_id, str)
        if not submitted:
            return AdapterResult(
                status="failed",
                retryable=True,
                error=JobError(
                    code="comfyui_submit_failed",
                    message="ComfyUI 没有接受生成任务。",
                    retryable=True,
                    next_steps=("检查本机服务和模型名称后重新建立任务。",),
                ),
                warnings=tuple(str(item) for item in result.get("warnings") or ()),
            )
        state_payload = read_json(self._state_path(context))
        atomic_write_json(
            self._state_path(context),
            {
                **state_payload,
                "submitted": True,
                "promptId": prompt_id,
                "promptIdHash": prompt_id_hash,
                "lastKnownState": state,
            },
        )
        if state in {"failed", "cancelled", "status_unavailable"}:
            return AdapterResult(
                status="failed",
                retryable=state == "status_unavailable",
                error=JobError(
                    code=f"comfyui_{state}",
                    message="ComfyUI 已接受任务，但没有得到成功完成证据。",
                    retryable=state == "status_unavailable",
                    next_steps=("在本机 ComfyUI 检查任务状态；不要自动重复提交。",),
                ),
            )
        return AdapterResult(
            status="completed",
            output={"submitted": True, "state": state, "promptIdHash": prompt_id_hash},
            warnings=tuple(str(item) for item in result.get("warnings") or ()),
        )

    @staticmethod
    def _write_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _collect_results(self, context: AdapterContext) -> AdapterResult:
        state_payload = read_json(self._state_path(context))
        prompt_id = state_payload.get("promptId")
        if not isinstance(prompt_id, str):
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="comfyui_prompt_id_missing", message="ComfyUI 提交标识不可用。"
                ),
            )
        base_url = self._base_url()
        result = self.result_reader(
            {"prompt_id": prompt_id, "comfy_url": base_url, "timeout": 5, "wait_seconds": 0}
        )
        state = str(result.get("state") or "unavailable")
        if state == "queued_or_running":
            return AdapterResult(
                status="needs_user",
                output={
                    "message": "ComfyUI 任务仍在运行；稍后只读刷新同一任务，不会重复提交。",
                    "state": "queued_or_running",
                    "submittedAgain": False,
                },
            )
        if not result.get("result_ready"):
            return AdapterResult(
                status="failed",
                error=JobError(
                    code=f"comfyui_result_{state}",
                    message="ComfyUI 没有返回可登记的成功图片产物。",
                    next_steps=("在本机 ComfyUI 检查输出节点和执行状态。",),
                ),
            )
        manifest = result.get("output_manifest") or {}
        images = manifest.get("images") or []
        if not isinstance(images, list) or not 1 <= len(images) <= MAX_OUTPUTS:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="comfyui_output_count_invalid", message="ComfyUI 输出数量不在安全范围内。"
                ),
            )
        store = ArtifactStore(context.app_paths.artifacts)
        artifacts = []
        written_targets: list[Path] = []
        for index, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            try:
                basename = str(image.get("filename") or "")
                validate_basename(basename)
                target_name = basename if index == 0 else f"{index + 1}-{basename}"
                payload = self.output_fetcher(base_url, image, 15)
                _validate_generated_image_payload(basename, payload)
                target = store.allocate_path(context.project_id, context.job_id, target_name)
                self._write_bytes(target, payload)
                written_targets.append(target)
                artifacts.append(
                    store.register(
                        context.project_id, context.job_id, target, kind="generated_image"
                    )
                )
            except (OSError, ValueError):
                rollback_ok = True
                for written_target in reversed(written_targets):
                    try:
                        written_target.unlink(missing_ok=True)
                    except OSError:
                        rollback_ok = False
                return AdapterResult(
                    status="failed",
                    error=JobError(
                        code=(
                            "comfyui_output_fetch_failed"
                            if rollback_ok
                            else "comfyui_output_rollback_failed"
                        ),
                        message=(
                            "生成已经完成，但图片没有安全复制到项目产物目录。"
                            if rollback_ok
                            else "生成产物登记失败，且本批次文件未能全部清理。"
                        ),
                        next_steps=(
                            (
                                "保留本机 ComfyUI 输出，并检查回环 /view 接口后重试新任务。"
                                if rollback_ok
                                else "检查当前任务的隔离产物目录并手动清理残留文件。"
                            ),
                        ),
                    ),
                )
        if not artifacts:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="comfyui_outputs_missing", message="没有登记任何真实生成文件。"
                ),
            )
        atomic_write_json(
            self._state_path(context),
            {
                "schemaVersion": 1,
                "submitted": True,
                "promptIdHash": state_payload.get("promptIdHash"),
                "lastKnownState": "completed",
                "outputCount": len(artifacts),
                "artifactHashes": [artifact.sha256 for artifact in artifacts],
                "promptPersisted": False,
                "modelNamePersisted": False,
            },
        )
        return AdapterResult(
            status="completed",
            output={"state": "completed", "outputCount": len(artifacts)},
            artifacts=tuple(artifacts),
        )

    def execute(self, context: AdapterContext) -> AdapterResult:
        if context.cancellation.cancelled:
            return AdapterResult(status="cancelled")
        operation = self._operation(context)
        if operation == "validate-workflow":
            return self._validate_workflow(context)
        if operation == "probe-service":
            return self._probe_service(context)
        if operation == "submit-generation":
            return self._submit(context)
        return self._collect_results(context)

    def collect_evidence(self, context: AdapterContext, result: AdapterResult) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "stepId": context.step.step_id,
            "status": result.status,
            "artifactIds": [artifact.artifact_id for artifact in result.artifacts],
            "artifactHashes": [artifact.sha256 for artifact in result.artifacts],
            "outputCount": len(result.artifacts),
            "promptPersisted": False,
            "modelNamePersisted": False,
            "workflowPayloadPersisted": False,
            "warnings": list(result.warnings),
        }
