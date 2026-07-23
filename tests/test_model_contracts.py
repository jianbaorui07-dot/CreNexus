from __future__ import annotations

import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from model_contracts import (
    CONTRACT_VERSION,
    SCHEMA_NAMES,
    ModelContractValidationError,
    ensure_plan_response,
    load_schema,
    validate_plan_response,
)
from model_contracts.provider_interface import BaseModelProvider

SHA256 = "0" * 64


def privacy() -> dict[str, bool]:
    return {
        "absolutePathsIncluded": False,
        "customerFileNamesIncluded": False,
        "rawAssetContentIncluded": False,
    }


def constraints() -> dict[str, object]:
    return {
        "executionMode": "local",
        "localOnly": True,
        "cloudProcessingApproved": False,
        "materialTransfer": "metadata_only",
        "embeddedRasterAllowed": False,
        "outputFormats": ["svg", "ai"],
        "requireConfirmationForWrites": True,
        "maxSteps": 8,
        "safeRootRefs": ["starbridge-app-data"],
    }


def available_adapters() -> list[dict[str, object]]:
    return [
        {
            "adapterId": "vision",
            "connectionState": "available",
            "actions": [
                {
                    "action": "analyze_structure",
                    "sideEffect": "read",
                    "requiresConfirmation": False,
                }
            ],
        },
        {
            "adapterId": "vectorization",
            "connectionState": "available",
            "actions": [
                {
                    "action": "semantic_vectorize",
                    "sideEffect": "write",
                    "requiresConfirmation": True,
                }
            ],
        },
        {
            "adapterId": "illustrator",
            "connectionState": "not_running",
            "actions": [
                {
                    "action": "save_as_ai",
                    "sideEffect": "write",
                    "requiresConfirmation": True,
                }
            ],
        },
    ]


def plan_request() -> dict[str, object]:
    return {
        "schema": CONTRACT_VERSION,
        "requestId": "request-001",
        "projectId": "project-001",
        "instruction": "把已导入的图片转换成可编辑矢量文件。",
        "locale": "zh-CN",
        "inputAssets": [
            {
                "assetId": "asset-001",
                "mediaType": "image/png",
                "role": "source",
                "sha256": SHA256,
            }
        ],
        "availableAdapters": available_adapters(),
        "constraints": constraints(),
        "privacy": privacy(),
    }


def response_safety() -> dict[str, bool]:
    return {
        "confirmationGateBypass": False,
        "directExecution": False,
        "directFileAccess": False,
        "shellCommandsIncluded": False,
    }


def plan_response() -> dict[str, object]:
    return {
        "schema": CONTRACT_VERSION,
        "requestId": "request-001",
        "modelId": "koryao-c1-planner",
        "modelVersion": "0.1.0",
        "providerId": "rule-based",
        "workflowId": "vector-delivery-v2",
        "confidence": 0.91,
        "requiresConfirmation": True,
        "summary": "先分析结构，再生成受控矢量结果。",
        "steps": [
            {
                "stepId": "analyze-input",
                "adapterId": "vision",
                "action": "analyze_structure",
                "dependsOn": [],
                "inputRefs": ["asset-001"],
                "parameters": [],
                "requiresConfirmation": False,
            },
            {
                "stepId": "generate-vector",
                "adapterId": "vectorization",
                "action": "semantic_vectorize",
                "dependsOn": ["analyze-input"],
                "inputRefs": ["asset-001"],
                "parameters": [{"name": "mode", "value": "semantic"}],
                "requiresConfirmation": True,
                "safeRootRef": "starbridge-app-data",
            },
        ],
        "qualityTargets": [
            {"metric": "editable", "operator": "eq", "value": True},
            {"metric": "embeddedRaster", "operator": "eq", "value": False},
        ],
        "safety": response_safety(),
    }


class ModelContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {name: load_schema(name) for name in SCHEMA_NAMES}
        cls.registry = Registry().with_resources(
            (
                schema["$id"],
                Resource.from_contents(schema),
            )
            for schema in cls.schemas.values()
        )

    def validate(self, name: str, payload: dict[str, object]) -> None:
        validator = Draft202012Validator(self.schemas[name], registry=self.registry)
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual([], errors, "\n".join(error.message for error in errors))

    def assert_invalid(self, name: str, payload: dict[str, object]) -> None:
        validator = Draft202012Validator(self.schemas[name], registry=self.registry)
        self.assertTrue(list(validator.iter_errors(payload)))

    def test_all_contract_schemas_are_valid_draft_2020_12(self) -> None:
        for name, schema in self.schemas.items():
            with self.subTest(name=name):
                Draft202012Validator.check_schema(schema)

    def test_plan_request_and_response_examples_validate(self) -> None:
        self.validate("plan_request.schema.json", plan_request())
        self.validate("plan_response.schema.json", plan_response())

    def test_plan_schema_rejects_commands_and_raw_asset_content(self) -> None:
        response = plan_response()
        response["steps"][0]["command"] = "run something"
        self.assert_invalid("plan_response.schema.json", response)

        request = plan_request()
        request["inputAssets"][0]["content"] = "raw bytes"
        self.assert_invalid("plan_request.schema.json", request)

    def test_local_request_cannot_claim_cloud_approval(self) -> None:
        request = plan_request()
        request["constraints"]["cloudProcessingApproved"] = True
        self.assert_invalid("plan_request.schema.json", request)

    def test_evaluate_contracts_validate(self) -> None:
        request = {
            "schema": CONTRACT_VERSION,
            "requestId": "evaluate-001",
            "projectId": "project-001",
            "jobId": "job-001",
            "workflowId": "vector-delivery-v2",
            "attempt": 1,
            "qualityTargets": [{"metric": "editable", "operator": "eq", "value": True}],
            "evidence": [
                {
                    "metric": "editable",
                    "value": True,
                    "target": True,
                    "passed": True,
                }
            ],
            "resultAssets": [
                {
                    "assetId": "artifact-001",
                    "mediaType": "image/svg+xml",
                    "role": "result",
                    "sha256": SHA256,
                }
            ],
            "privacy": privacy(),
        }
        response = {
            "schema": CONTRACT_VERSION,
            "requestId": "evaluate-001",
            "modelId": "koryao-c1-planner",
            "modelVersion": "0.1.0",
            "providerId": "rule-based",
            "verdict": "pass",
            "confidence": 0.98,
            "summary": "结构化质量目标已通过。",
            "findings": [],
            "failedTargets": [],
            "repairRecommended": False,
            "safety": response_safety(),
        }
        self.validate("evaluate_request.schema.json", request)
        self.validate("evaluate_response.schema.json", response)

    def test_repair_contracts_validate(self) -> None:
        request = {
            "schema": CONTRACT_VERSION,
            "requestId": "repair-001",
            "projectId": "project-001",
            "jobId": "job-001",
            "workflowId": "vector-delivery-v2",
            "failedStepId": "generate-vector",
            "repairAttempt": 1,
            "error": {
                "code": "quality_gate_failed",
                "message": "可编辑性质量门未通过。",
                "retryable": True,
            },
            "evaluation": {
                "verdict": "fail",
                "failedTargets": ["editable"],
                "findingCodes": ["insufficient_editability"],
            },
            "availableAdapters": available_adapters(),
            "constraints": constraints(),
            "privacy": privacy(),
        }
        response = {
            "schema": CONTRACT_VERSION,
            "requestId": "repair-001",
            "modelId": "koryao-c1-planner",
            "modelVersion": "0.1.0",
            "providerId": "rule-based",
            "workflowId": "vector-delivery-v2-repair-1",
            "decision": "retry",
            "confidence": 0.8,
            "summary": "使用同一白名单动作调整受控参数后重试。",
            "replacementSteps": [
                {
                    "stepId": "retry-vector",
                    "adapterId": "vectorization",
                    "action": "semantic_vectorize",
                    "dependsOn": [],
                    "inputRefs": ["asset-001"],
                    "parameters": [{"name": "mode", "value": "semantic"}],
                    "requiresConfirmation": True,
                    "safeRootRef": "starbridge-app-data",
                }
            ],
            "requiresConfirmation": True,
            "safety": response_safety(),
        }
        self.validate("repair_request.schema.json", request)
        self.validate("repair_response.schema.json", response)

    def test_model_status_is_loopback_only_and_redacted(self) -> None:
        status = {
            "schema": CONTRACT_VERSION,
            "serviceId": "koryao-model-runtime",
            "serviceVersion": "0.1.0",
            "status": "healthy",
            "runtimeMode": "local",
            "supportedContracts": [CONTRACT_VERSION],
            "network": {
                "bindAddress": "127.0.0.1",
                "externalNetworkAccess": False,
            },
            "privacy": {
                "acceptsRawAssets": False,
                "logsAbsolutePaths": False,
                "logsFullInstructions": False,
            },
            "models": [
                {
                    "modelId": "koryao-c1-planner",
                    "version": "0.1.0",
                    "providerId": "rule-based",
                    "status": "experimental",
                    "capabilities": ["plan", "evaluate", "repair"],
                }
            ],
        }
        self.validate("model_status.schema.json", status)


class ModelContractCrossValidationTests(unittest.TestCase):
    def test_valid_plan_passes_cross_document_checks(self) -> None:
        self.assertEqual([], validate_plan_response(plan_request(), plan_response()))
        ensure_plan_response(plan_request(), plan_response())

    def test_unknown_adapter_action_is_rejected(self) -> None:
        response = plan_response()
        response["steps"][0]["action"] = "read_private_disk"
        errors = validate_plan_response(plan_request(), response)
        self.assertTrue(any("outside the request allowlist" in error for error in errors))

    def test_confirmation_gate_cannot_be_removed(self) -> None:
        response = plan_response()
        response["steps"][1]["requiresConfirmation"] = False
        response["requiresConfirmation"] = False
        errors = validate_plan_response(plan_request(), response)
        self.assertTrue(any("confirmation gate" in error for error in errors))
        self.assertTrue(any("must require confirmation" in error for error in errors))

    def test_commands_paths_and_uris_are_rejected_even_as_parameter_values(self) -> None:
        for value in (
            "powershell -Command do-work",
            "/private/asset.png",
            "https://example.invalid/payload",
            "../escape",
        ):
            with self.subTest(value=value):
                response = plan_response()
                response["steps"][1]["parameters"] = [{"name": "unsafe", "value": value}]
                errors = validate_plan_response(plan_request(), response)
                self.assertTrue(
                    any("command, URI, or filesystem path" in error for error in errors)
                )

    def test_dependency_cycles_and_request_mismatch_are_rejected(self) -> None:
        response = plan_response()
        response["requestId"] = "other-request"
        response["steps"][0]["dependsOn"] = ["generate-vector"]
        errors = validate_plan_response(plan_request(), response)
        self.assertTrue(any("requestId" in error for error in errors))
        self.assertTrue(any("acyclic" in error for error in errors))

    def test_ensure_raises_a_structured_validation_error(self) -> None:
        response = plan_response()
        response["safety"]["directExecution"] = True
        with self.assertRaises(ModelContractValidationError) as raised:
            ensure_plan_response(plan_request(), response)
        self.assertTrue(raised.exception.errors)

    def test_provider_interface_cannot_be_instantiated(self) -> None:
        with self.assertRaises(TypeError):
            BaseModelProvider()


if __name__ == "__main__":
    unittest.main()
