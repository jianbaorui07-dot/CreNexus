from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from starbridge_mcp.core.security import sanitize

DEFAULT_PROXY_URL = os.environ.get("STARBRIDGE_PHOTOSHOP_NODE_PROXY_URL", "http://127.0.0.1:8971")


def _request(
    method: str, path: str, payload: dict[str, Any] | None = None, *, timeout: int = 3
) -> dict[str, Any]:
    url = DEFAULT_PROXY_URL.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return sanitize(json.loads(body)) if body else {}


def health(*, timeout: int = 3) -> dict[str, Any]:
    try:
        payload = _request("GET", "/health", timeout=timeout)
        payload.setdefault("ok", True)
        return payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "node_proxy_running": False,
            "uxp_client_connected": False,
            "photoshop_host_seen": False,
            "message": f"node_proxy_unavailable: {type(exc).__name__}",
        }


def bridge_status(*, timeout: int = 3) -> dict[str, Any]:
    try:
        payload = _request("GET", "/bridge/status", timeout=timeout)
        payload.setdefault("ok", True)
        return payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "node_proxy_running": False,
            "uxp_client_connected": False,
            "photoshop_host_seen": False,
            "message": f"node_proxy_unavailable: {type(exc).__name__}",
        }


def rpc(method: str, params: dict[str, Any] | None = None, *, timeout: int = 8) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": "starbridge", "method": method, "params": params or {}}
    return _request("POST", "/rpc", payload, timeout=timeout)
