from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from tempfile import TemporaryDirectory
from typing import Any

from starbridge_mcp.backend import KORYAOBackend


class FakeModelRuntime:
    def __init__(self) -> None:
        self.requests: list[tuple[str, Mapping[str, Any]]] = []

    def status(self) -> dict[str, Any]:
        return {
            "schema": "koryao-model-contract/v1",
            "serviceId": "koryao-model-runtime",
            "serviceVersion": "0.1.0",
            "status": "healthy",
            "runtimeMode": "local",
            "supportedContracts": ["koryao-model-contract/v1"],
            "network": {"bindAddress": "127.0.0.1", "externalNetworkAccess": False},
            "privacy": {
                "acceptsRawAssets": False,
                "logsAbsolutePaths": False,
                "logsFullInstructions": False,
            },
            "models": [],
        }

    def plan(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append(("plan", request))
        return {
            "schema": "koryao-model-contract/v1",
            "requestId": request["requestId"],
            "modelId": "koryao-c1-planner",
            "modelVersion": "0.1.0",
            "providerId": "rule-based",
            "workflowId": "vector-delivery-v2",
            "confidence": 0.86,
            "requiresConfirmation": True,
            "summary": "生成可编辑矢量交付计划",
            "steps": [],
            "qualityTargets": [],
            "safety": {},
        }

    def evaluate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append(("evaluate", request))
        return {"requestId": request["requestId"]}

    def repair(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.requests.append(("repair", request))
        return {"requestId": request["requestId"]}


class BackendModelRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.runtime = FakeModelRuntime()
        self.backend = KORYAOBackend(
            app_data_dir=self.temp_dir.name,
            model_runtime_client=self.runtime,
        )

    def test_model_status_is_exposed_without_private_implementation(self) -> None:
        response = self.backend.route("GET", "/api/model/status")
        self.assertEqual(200, response.status)
        self.assertTrue(response.body["ok"])
        self.assertEqual("healthy", response.body["data"]["status"])
        self.assertFalse(response.body["data"]["network"]["externalNetworkAccess"])

    def test_model_operations_are_forwarded_as_structured_json(self) -> None:
        request = {
            "schema": "koryao-model-contract/v1",
            "requestId": "request-001",
        }
        response = self.backend.route(
            "POST",
            "/api/model/plan",
            json.dumps(request).encode("utf-8"),
        )
        self.assertEqual(200, response.status)
        self.assertEqual([("plan", request)], self.runtime.requests)
        self.assertEqual("request-001", response.body["data"]["requestId"])

    def test_unknown_model_route_is_not_forwarded(self) -> None:
        response = self.backend.route(
            "POST",
            "/api/model/execute",
            b"{}",
        )
        self.assertEqual(404, response.status)
        self.assertEqual([], self.runtime.requests)


if __name__ == "__main__":
    unittest.main()
