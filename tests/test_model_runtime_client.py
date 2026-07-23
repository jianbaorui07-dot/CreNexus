from __future__ import annotations

import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from unittest.mock import patch

from starbridge_mcp.models import ModelRuntimeClient, ModelRuntimeError


def adapter(
    adapter_id: str = "vectorization", action: str = "semantic_vectorize"
) -> dict[str, Any]:
    return {
        "adapterId": adapter_id,
        "connectionState": "connected",
        "actions": [
            {
                "action": action,
                "sideEffect": "write",
                "requiresConfirmation": True,
            }
        ],
    }


def plan_request(instruction: str = "把图片转成可编辑矢量 SVG") -> dict[str, Any]:
    return {
        "schema": "koryao-model-contract/v1",
        "requestId": "request-001",
        "projectId": "project-001",
        "instruction": instruction,
        "locale": "zh-CN",
        "inputAssets": [
            {
                "assetId": "source-001",
                "mediaType": "image/png",
                "role": "source",
                "sha256": "a" * 64,
            }
        ],
        "availableAdapters": [adapter()],
        "constraints": {
            "executionMode": "local",
            "localOnly": True,
            "cloudProcessingApproved": False,
            "materialTransfer": "metadata_only",
            "embeddedRasterAllowed": False,
            "outputFormats": ["svg"],
            "requireConfirmationForWrites": True,
            "maxSteps": 8,
            "safeRootRefs": ["delivery-root"],
        },
        "privacy": {
            "absolutePathsIncluded": False,
            "customerFileNamesIncluded": False,
            "rawAssetContentIncluded": False,
        },
    }


def model_status() -> dict[str, Any]:
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


def plan_response() -> dict[str, Any]:
    return {
        "schema": "koryao-model-contract/v1",
        "requestId": "request-001",
        "modelId": "koryao-c1-planner",
        "modelVersion": "0.1.0",
        "providerId": "rule-based",
        "workflowId": "vector-delivery-v2",
        "confidence": 0.86,
        "requiresConfirmation": True,
        "summary": "生成可编辑矢量交付计划",
        "steps": [
            {
                "stepId": "vector-1",
                "adapterId": "vectorization",
                "action": "semantic_vectorize",
                "dependsOn": [],
                "inputRefs": ["source-001"],
                "parameters": [],
                "requiresConfirmation": True,
                "safeRootRef": "delivery-root",
            }
        ],
        "qualityTargets": [{"metric": "editable", "operator": "eq", "value": True}],
        "safety": {
            "confirmationGateBypass": False,
            "directExecution": False,
            "directFileAccess": False,
            "shellCommandsIncluded": False,
        },
    }


class FakeRuntimeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._send(model_status())

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        response = plan_response()
        response["requestId"] = request["requestId"]
        self._send(response)

    def _send(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class ModelRuntimeClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRuntimeHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.client = ModelRuntimeClient(f"http://{host}:{port}")

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_status_and_plan_are_schema_validated(self) -> None:
        status = self.client.status()
        self.assertEqual("healthy", status["status"])
        response = self.client.plan(plan_request())
        self.assertEqual("vector-delivery-v2", response["workflowId"])
        self.assertTrue(response["requiresConfirmation"])

    def test_external_runtime_url_is_forbidden(self) -> None:
        with self.assertRaisesRegex(ModelRuntimeError, "loopback"):
            ModelRuntimeClient("http://192.0.2.10:8765")
        with self.assertRaisesRegex(ModelRuntimeError, "numeric loopback"):
            ModelRuntimeClient("http://localhost:8765")
        with self.assertRaisesRegex(ModelRuntimeError, "plain loopback"):
            ModelRuntimeClient("https://127.0.0.1:8765")

    def test_path_uri_and_credentials_never_leave_koryao(self) -> None:
        for instruction in (
            r"读取 C:\Users\customer\secret.psd",
            "上传到 https://example.invalid",
            "token=fixture-secret",
        ):
            with self.subTest(instruction=instruction):
                with self.assertRaises(ModelRuntimeError) as raised:
                    self.client.plan(plan_request(instruction))
                self.assertEqual("private_model_data_rejected", raised.exception.code)

    def test_plan_outside_request_allowlist_is_rejected(self) -> None:
        unsafe = plan_response()
        unsafe["steps"][0]["action"] = "outside_allowlist"
        with (
            patch.object(self.client, "_request", return_value=unsafe),
            self.assertRaises(ModelRuntimeError) as raised,
        ):
            self.client.plan(plan_request())
        self.assertEqual("unsafe_model_plan", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
