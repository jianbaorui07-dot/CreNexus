from __future__ import annotations

import json
import sys
from typing import Any

from starbridge_mcp import server


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") if isinstance(request.get("params"), dict) else {}

    if method == "ping":
        return _jsonrpc_result(request_id, {"ok": True, "service": "starbridge_mcp"})
    if method == "tools/list":
        result = {"tools": server.tool_specs(safe_only=True)}
    elif method == "tools/call":
        name = str(params.get("name", ""))
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        result = server.call_tool(name, arguments)
    elif method in {"initialize", "starbridge/status"}:
        result = server.status()
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unsupported method: {method}"},
        }

    return _jsonrpc_result(request_id, result)


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        return
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        else:
            response = handle_request(request)
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("Please use Python 3.10 or newer.")
    main()
