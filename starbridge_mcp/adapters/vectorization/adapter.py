from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CreativeAdapter,
    ProbeResult,
    ValidationReport,
)
from starbridge_mcp.domain.models import JobError, validate_relative_path
from starbridge_mcp.storage.artifact_store import ArtifactStore
from starbridge_mcp.vectorization.engine import (
    RunConfig,
    VectorizationError,
    load_source,
    run_vectorization,
)
from starbridge_mcp.vectorization.presets import PRESETS

OUTPUT_FILES = {
    "vector.svg": "editable_svg",
    "preview.png": "preview",
    "parameters.json": "parameters",
    "vector_report.json": "quality_report",
    "vector_report.md": "quality_report_markdown",
    "artisan_baseline.svg": "rollback_baseline",
    "svg_render.png": "render_proof",
    "adaptive_optimization.json": "optimization_report",
    "artisan_structure.json": "edit_structure",
    "artisan_edit_index.json": "edit_index",
}


class VectorizationAdapter(CreativeAdapter):
    adapter_id = "vectorization"

    @staticmethod
    def _operation(context: AdapterContext) -> str:
        return str(context.step.input_data.get("operation") or "vectorize")

    @staticmethod
    def _source_path(context: AdapterContext) -> Path:
        relative = validate_relative_path(
            str(context.step.input_data.get("sourceAssetRelativePath") or "")
        )
        source = (context.app_paths.root / relative).resolve(strict=False)
        projects_root = context.app_paths.projects.resolve()
        try:
            source.relative_to(projects_root)
        except ValueError as exc:
            raise ValueError("source asset must stay inside managed project data") from exc
        if not source.is_file():
            raise ValueError("managed source asset is missing")
        return source

    @staticmethod
    def _output_directory(context: AdapterContext, mode: str) -> Path:
        return context.app_paths.artifacts / context.project_id / context.job_id / mode

    def probe(self, context: AdapterContext) -> ProbeResult:
        return ProbeResult(
            available=True,
            connection_state="available",
            message="离线矢量引擎可用。",
            details={"requiresThirdPartySoftware": False},
        )

    def plan(self, context: AdapterContext) -> dict[str, Any]:
        operation = self._operation(context)
        return {
            "operation": operation,
            "mode": context.step.input_data.get("mode"),
            "writes": operation == "vectorize",
            "safeRootRef": "starbridge-app-data/artifacts",
        }

    def validate(self, context: AdapterContext) -> ValidationReport:
        operation = self._operation(context)
        try:
            self._source_path(context)
        except ValueError:
            return ValidationReport(
                ok=False,
                error=JobError(
                    code="managed_source_missing",
                    message="项目中的受控源素材不可用。",
                    next_steps=("重新导入一张明确选择的 PNG 或 JPEG。",),
                ),
            )
        if operation == "vectorize" and context.step.input_data.get("mode") not in PRESETS:
            return ValidationReport(
                ok=False,
                error=JobError(code="invalid_vector_mode", message="矢量模式无效。"),
            )
        if operation not in {"validate-source", "vectorize", "verify-exact", "compare-quality"}:
            return ValidationReport(
                ok=False,
                error=JobError(code="invalid_vector_operation", message="矢量步骤无效。"),
            )
        return ValidationReport(ok=True)

    def _validate_source(self, context: AdapterContext) -> AdapterResult:
        source = self._source_path(context)
        try:
            _, metadata = load_source(str(source), max_pixels=4_000_000)
        except VectorizationError as exc:
            return AdapterResult(
                status="failed",
                error=JobError(code=exc.code, message=str(exc)),
            )
        return AdapterResult(
            status="completed",
            output={
                "sourceHash": metadata["source_sha256"],
                "format": metadata["format"],
                "width": metadata["width"],
                "height": metadata["height"],
                "pixelCount": metadata["pixel_count"],
            },
        )

    def _vectorize(self, context: AdapterContext) -> AdapterResult:
        if context.cancellation.cancelled:
            return AdapterResult(status="cancelled")
        mode = str(context.step.input_data["mode"])
        source = self._source_path(context)
        output_root = context.app_paths.artifacts.resolve()
        output_directory = self._output_directory(context, mode)
        parameters = context.step.input_data.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}

        def optional_int(name: str) -> int | None:
            value = parameters.get(name)
            return int(value) if isinstance(value, int | float) else None

        def optional_float(name: str) -> float | None:
            value = parameters.get(name)
            return float(value) if isinstance(value, int | float) else None

        try:
            report = run_vectorization(
                RunConfig(
                    input_path=str(source),
                    mode=mode,
                    reference_id=f"workflow-{context.job_id[-8:]}-{mode}",
                    output_dir=str(output_directory),
                    output_root=str(output_root),
                    colors=optional_int("colors"),
                    max_dimension=optional_int("maxDimension"),
                    simplify_ratio=optional_float("simplifyRatio"),
                    min_region_area=optional_int("minRegionArea"),
                    alpha_threshold=optional_int("alphaThreshold"),
                )
            )
        except VectorizationError as exc:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code=exc.code,
                    message=str(exc),
                    next_steps=("检查输入限制和参数；不会自动回退到 Image Trace。",),
                ),
            )
        if context.cancellation.cancelled:
            return AdapterResult(status="cancelled")
        artifact_store = ArtifactStore(context.app_paths.artifacts)
        artifacts = tuple(
            artifact_store.register(
                context.project_id,
                context.job_id,
                output_directory / basename,
                kind=kind,
            )
            for basename, kind in OUTPUT_FILES.items()
            if (output_directory / basename).is_file()
        )
        return AdapterResult(
            status="completed",
            output={
                "mode": mode,
                "sourceHash": report["source"]["source_sha256"],
                "validation": report["validation"],
                "exactValidation": report.get("exact_validation"),
                "metrics": report["vector"],
            },
            artifacts=artifacts,
            warnings=tuple(str(item) for item in report.get("warnings") or ()),
        )

    def _report(self, context: AdapterContext, mode: str) -> dict[str, Any]:
        path = self._output_directory(context, mode) / "vector_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("vector report is invalid")
        return payload

    def _verify_exact(self, context: AdapterContext) -> AdapterResult:
        try:
            report = self._report(context, "exact")
            validation = report["validation"]
            exact = report["exact_validation"]
            ok = bool(
                validation["svg_verified"]
                and not validation["image_trace_used"]
                and validation["embedded_raster_count"] == 0
                and validation["external_reference_count"] == 0
                and exact["pixel_match"]
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            ok = False
        if not ok:
            return AdapterResult(
                status="failed",
                error=JobError(
                    code="exact_baseline_invalid",
                    message="精确重建基线未通过像素或 SVG 安全验证。",
                    next_steps=("停止当前工作流并检查精确重建报告。",),
                ),
            )
        return AdapterResult(
            status="completed",
            output={
                "pixelMatch": True,
                "svgVerified": True,
                "imageTraceUsed": False,
                "embeddedRasterCount": 0,
                "externalReferenceCount": 0,
            },
        )

    def _compare_quality(self, context: AdapterContext) -> AdapterResult:
        drawing_mode = str(context.step.input_data["mode"])
        try:
            exact = self._report(context, "exact")
            drawing = self._report(context, drawing_mode)
        except (OSError, ValueError, json.JSONDecodeError):
            return AdapterResult(
                status="failed",
                error=JobError(code="quality_report_missing", message="质量报告不完整。"),
            )
        vector = drawing.get("vector") or {}
        return AdapterResult(
            status="completed",
            output={
                "baselinePixelMatch": bool(
                    (exact.get("exact_validation") or {}).get("pixel_match")
                ),
                "mode": drawing_mode,
                "colors": vector.get("color_count"),
                "paths": vector.get("subpaths"),
                "anchors": vector.get("points"),
                "svgBytes": vector.get("svg_bytes"),
                "elapsedSeconds": drawing.get("elapsed_seconds"),
                "warnings": drawing.get("warnings") or [],
            },
        )

    def execute(self, context: AdapterContext) -> AdapterResult:
        operation = self._operation(context)
        if operation == "validate-source":
            return self._validate_source(context)
        if operation == "vectorize":
            return self._vectorize(context)
        if operation == "verify-exact":
            return self._verify_exact(context)
        return self._compare_quality(context)
