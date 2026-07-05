from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from starbridge_mcp.core.security import sanitize
from starbridge_mcp.mcp_server import SERVER_INFO, handle_request

JsonObject = dict[str, Any]
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIC_ROOT = REPO_ROOT / "examples" / "starbridge_frontend" / "dist"


@dataclass(frozen=True)
class BackendResponse:
    status: int
    body: JsonObject | bytes
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json; charset=utf-8"


class StarBridgeBackend:
    """Small REST facade over the existing StarBridge MCP handlers."""

    def __init__(self, static_root: Path | None = None) -> None:
        self._next_id = 1
        self.static_root = static_root or DEFAULT_STATIC_ROOT

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
        value = StarBridgeBackend._one(query, key)
        if value is None:
            return default
        return value.lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _json_body(raw_body: bytes) -> JsonObject:
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
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

    def route(self, method: str, target: str, raw_body: bytes = b"") -> BackendResponse:
        parsed = urlparse(target)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        method = method.upper()

        try:
            body = self._json_body(raw_body)
        except ValueError as exc:
            return BackendResponse(400, {"ok": False, "error": str(exc)})

        if method == "OPTIONS":
            return BackendResponse(204, {"ok": True})

        if method == "GET" and path == "/api/health":
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "service": "starbridge-backend",
                    "server": SERVER_INFO,
                },
            )

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

        if method == "GET" and path == "/api/bootstrap":
            capabilities = self._tool("starbridge.tools", {"safe_only": True})
            recipes = self._tool("starbridge.recipe_list", {"bridge": "all"})
            safe_roots = self._tool("starbridge.safe_roots", {"bridge": "all"})
            resources = self._mcp("resources/list")
            responses = [capabilities, recipes, safe_roots, resources]
            if any(response.status != 200 for response in responses):
                return BackendResponse(
                    500,
                    {
                        "ok": False,
                        "error": "bootstrap failed",
                        "responses": [response.body for response in responses],
                    },
                )
            return BackendResponse(
                200,
                {
                    "ok": True,
                    "data": {
                        "server": SERVER_INFO,
                        "capabilities": capabilities.body["data"],
                        "recipes": recipes.body["data"],
                        "safe_roots": safe_roots.body["data"],
                        "resources": resources.body["data"],
                    },
                },
            )

        if path.startswith("/api/recipes/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "recipes":
                recipe_id, action = parts[2], parts[3]
                arguments = dict(body)
                arguments["recipe_id"] = recipe_id
                if action == "plan" and method in {"GET", "POST"}:
                    return self._tool("starbridge.recipe_plan", arguments)
                if action == "evidence" and method in {"GET", "POST"}:
                    return self._tool("starbridge.recipe_evidence", arguments)

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
    handler: BaseHTTPRequestHandler, response: BackendResponse, *, write_body: bool = True
) -> None:
    body = (
        b""
        if response.status == 204
        else response.body
        if isinstance(response.body, bytes)
        else json.dumps(sanitize(response.body), ensure_ascii=False, indent=2).encode("utf-8")
    )
    handler.send_response(response.status)
    handler.send_header("Content-Type", response.content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    for name, value in response.headers.items():
        handler.send_header(name, value)
    handler.end_headers()
    if write_body and response.status != 204:
        handler.wfile.write(body)


def make_handler(backend: StarBridgeBackend) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802
            _send(self, backend.route("OPTIONS", self.path))

        def do_GET(self) -> None:  # noqa: N802
            _send(self, backend.route("GET", self.path))

        def do_HEAD(self) -> None:  # noqa: N802
            _send(self, backend.route("GET", self.path), write_body=False)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            _send(self, backend.route("POST", self.path, self.rfile.read(length)))

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    backend = StarBridgeBackend()
    server = ThreadingHTTPServer((host, port), make_handler(backend))
    print(f"StarBridge backend listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StarBridge local HTTP backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
