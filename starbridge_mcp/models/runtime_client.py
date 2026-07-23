from __future__ import annotations

import http.client
import ipaddress
import json
import os
import re
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from model_contracts import ModelContractValidationError, ensure_plan_response, load_schema

JsonObject = dict[str, Any]
DEFAULT_MODEL_RUNTIME_URL = "http://127.0.0.1:8765"
MODEL_RUNTIME_URL_ENV = "KORYAO_MODEL_RUNTIME_URL"
MAX_RESPONSE_BYTES = 512 * 1024
_SCHEMAS = (
    "common.schema.json",
    "plan_request.schema.json",
    "plan_response.schema.json",
    "evaluate_request.schema.json",
    "evaluate_response.schema.json",
    "repair_request.schema.json",
    "repair_response.schema.json",
    "model_status.schema.json",
)
_ABSOLUTE_PATH = re.compile(r"(?:^|[\s'\"(])(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|mnt)/)")
_URI = re.compile(r"(?:^|[\s'\"(])[A-Za-z][A-Za-z0-9+.-]*://")
_CREDENTIAL = re.compile(
    r"(?i)(?:bearer\s+[A-Za-z0-9._-]{12,}|"
    r"(?:token|cookie|password|secret|api[_-]?key|account|username|email)\s*[:=])"
)
_FORBIDDEN_KEYS = frozenset(
    {
        "absolutePath",
        "command",
        "cookie",
        "customerFileName",
        "executable",
        "fileContent",
        "fileName",
        "filePath",
        "password",
        "path",
        "prompt",
        "rawAsset",
        "script",
        "secret",
        "shell",
        "token",
        "url",
    }
)


class ModelRuntimeError(RuntimeError):
    """A model runtime request failed without exposing private payload data."""

    def __init__(self, code: str, message: str, *, status: int) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


class ModelRuntimeClientProtocol(Protocol):
    def status(self) -> JsonObject: ...

    def plan(self, request: Mapping[str, Any]) -> JsonObject: ...

    def evaluate(self, request: Mapping[str, Any]) -> JsonObject: ...

    def repair(self, request: Mapping[str, Any]) -> JsonObject: ...


def _schema_registry() -> Registry:
    resources = []
    for name in _SCHEMAS:
        schema = load_schema(name)
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


_REGISTRY = _schema_registry()


def _validate_schema(payload: Mapping[str, Any], schema_name: str, *, response: bool) -> None:
    schema = load_schema(schema_name)
    errors = sorted(
        Draft202012Validator(schema, registry=_REGISTRY).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) or "$"
    raise ModelRuntimeError(
        "invalid_model_response" if response else "invalid_model_request",
        f"{schema_name} validation failed at {location}",
        status=502 if response else 422,
    )


def _scan_request(value: Any, location: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_KEYS:
                raise ModelRuntimeError(
                    "forbidden_model_field",
                    f"{location}.{key_text} is not permitted in a model request",
                    status=422,
                )
            _scan_request(child, f"{location}.{key_text}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_request(child, f"{location}[{index}]")
        return
    if isinstance(value, str) and (
        _ABSOLUTE_PATH.search(value) or _URI.search(value) or _CREDENTIAL.search(value)
    ):
        raise ModelRuntimeError(
            "private_model_data_rejected",
            f"{location} contains a path, URI, credential, or account identifier",
            status=422,
        )


class ModelRuntimeClient:
    """HTTP client that can only reach a fixed loopback model runtime."""

    def __init__(self, base_url: str = DEFAULT_MODEL_RUNTIME_URL, *, timeout: float = 2.0) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or parsed.hostname is None
        ):
            raise ModelRuntimeError(
                "invalid_model_runtime_url",
                "model runtime URL must be a plain loopback HTTP origin",
                status=500,
            )
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError as exc:
            raise ModelRuntimeError(
                "invalid_model_runtime_url",
                "model runtime hostname must be a numeric loopback address",
                status=500,
            ) from exc
        if not address.is_loopback:
            raise ModelRuntimeError(
                "external_model_runtime_forbidden",
                "model runtime must use a loopback address",
                status=500,
            )
        if timeout <= 0 or timeout > 10:
            raise ValueError("model runtime timeout must be between 0 and 10 seconds")
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.timeout = timeout

    @classmethod
    def from_environment(cls) -> ModelRuntimeClient:
        return cls(os.environ.get(MODEL_RUNTIME_URL_ENV, DEFAULT_MODEL_RUNTIME_URL))

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None) -> JsonObject:
        encoded = None
        headers = {"Accept": "application/json", "Connection": "close"}
        if payload is not None:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            declared_length = response.getheader("Content-Length")
            if declared_length and int(declared_length) > MAX_RESPONSE_BYTES:
                raise ModelRuntimeError(
                    "model_response_too_large",
                    "model runtime response exceeds the public contract limit",
                    status=502,
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        except ModelRuntimeError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException, ValueError) as exc:
            raise ModelRuntimeError(
                "model_runtime_offline",
                "local model runtime is not reachable",
                status=503,
            ) from exc
        finally:
            connection.close()
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ModelRuntimeError(
                "model_response_too_large",
                "model runtime response exceeds the public contract limit",
                status=502,
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelRuntimeError(
                "invalid_model_response",
                "model runtime returned invalid JSON",
                status=502,
            ) from exc
        if not isinstance(document, dict):
            raise ModelRuntimeError(
                "invalid_model_response",
                "model runtime response must be a JSON object",
                status=502,
            )
        if response.status >= 400:
            error = document.get("error")
            code = (
                str(error.get("code"))
                if isinstance(error, Mapping) and error.get("code")
                else "model_runtime_rejected"
            )
            message = (
                str(error.get("message"))
                if isinstance(error, Mapping) and error.get("message")
                else "local model runtime rejected the request"
            )
            status = response.status if 400 <= response.status < 500 else 503
            raise ModelRuntimeError(code, message, status=status)
        return document

    def status(self) -> JsonObject:
        response = self._request("GET", "/v1/health", None)
        _validate_schema(response, "model_status.schema.json", response=True)
        if response["network"]["externalNetworkAccess"] is not False:
            raise ModelRuntimeError(
                "unsafe_model_runtime_status",
                "model runtime does not declare external networking disabled",
                status=502,
            )
        return response

    def _operation(self, operation: str, request: Mapping[str, Any]) -> JsonObject:
        _scan_request(request)
        _validate_schema(request, f"{operation}_request.schema.json", response=False)
        response = self._request("POST", f"/v1/{operation}", request)
        _validate_schema(response, f"{operation}_response.schema.json", response=True)
        if operation == "plan":
            try:
                ensure_plan_response(request, response)
            except ModelContractValidationError as exc:
                raise ModelRuntimeError(
                    "unsafe_model_plan",
                    "model plan failed the KORYAO cross-document safety check",
                    status=502,
                ) from exc
        return response

    def plan(self, request: Mapping[str, Any]) -> JsonObject:
        return self._operation("plan", request)

    def evaluate(self, request: Mapping[str, Any]) -> JsonObject:
        return self._operation("evaluate", request)

    def repair(self, request: Mapping[str, Any]) -> JsonObject:
        return self._operation("repair", request)
