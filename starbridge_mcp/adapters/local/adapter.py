from __future__ import annotations

from typing import Any

from starbridge_mcp.adapters.base import (
    AdapterContext,
    AdapterResult,
    CreativeAdapter,
    ProbeResult,
    ValidationReport,
)


class _AlwaysLocalAdapter(CreativeAdapter):
    def probe(self, context: AdapterContext) -> ProbeResult:
        return ProbeResult(True, "available", "StarBridge 本地能力可用。")

    def plan(self, context: AdapterContext) -> dict[str, Any]:
        return {
            "stepId": context.step.step_id,
            "writes": False,
            "safeRootRef": "starbridge-app-data",
        }

    def validate(self, context: AdapterContext) -> ValidationReport:
        return ValidationReport(ok=True)


class UserReviewAdapter(_AlwaysLocalAdapter):
    adapter_id = "user-review"

    def execute(self, context: AdapterContext) -> AdapterResult:
        return AdapterResult(
            status="completed",
            output={"reviewConfirmed": True, "stepId": context.step.step_id},
        )


class LocalDeliveryAdapter(_AlwaysLocalAdapter):
    adapter_id = "local-delivery"

    def execute(self, context: AdapterContext) -> AdapterResult:
        artifact_directory = (
            context.app_paths.artifacts / context.project_id / context.job_id
        ).resolve()
        return AdapterResult(
            status="completed",
            output={
                "deliveryReady": artifact_directory.is_dir(),
                "formatsAreDerivedFromArtifacts": True,
            },
        )
