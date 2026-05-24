"""Minimal public-safe ComfyUI bridge prototype.

The bridge uses only ComfyUI's local HTTP API and defaults to dry-run behavior
for workflow queueing. It does not install models, download custom nodes, or
touch generated output files.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BRIDGE = "comfyui"
DEFAULT_URL = "http://127.0.0.1:8188"
URL_ENV = "STARBRIDGE_COMFYUI_URL"
ALLOW_QUEUE_ENV = "STARBRIDGE_COMFYUI_ALLOW_QUEUE"


def _response(
    *,
    ok: bool,
    action: str,
    message: str,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "bridge": BRIDGE,
        "action": action,
        "message": message,
        "details": details or {},
        "warnings": warnings or [],
        "next_steps": next_steps or [],
    }


def _base_url() -> str:
    return os.environ.get(URL_ENV, DEFAULT_URL).strip().rstrip("/")


def _url(path: str) -> str:
    return urllib.parse.urljoin(_base_url() + "/", path.lstrip("/"))


def _read_json(path: str, timeout: float = 2.0) -> tuple[bool, Any, str | None]:
    request = urllib.request.Request(_url(path), headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, None, str(exc)

    try:
        return True, json.loads(raw), None
    except json.JSONDecodeError as exc:
        return False, None, f"Invalid JSON response: {exc}"


def _post_json(path: str, payload: dict[str, Any], timeout: float = 10.0) -> tuple[bool, Any, str | None]:
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _url(path),
        data=encoded,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, None, str(exc)

    try:
        return True, json.loads(raw), None
    except json.JSONDecodeError:
        return True, {"raw": raw}, None


def _allow_real_queue() -> bool:
    return os.environ.get(ALLOW_QUEUE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def status() -> dict[str, Any]:
    """Check whether a ComfyUI API endpoint is configured and reachable."""
    configured = URL_ENV in os.environ and bool(os.environ.get(URL_ENV, "").strip())
    ok, data, error = _read_json("/system_stats")
    details = {
        "url": _base_url(),
        "url_env": URL_ENV,
        "url_configured": configured,
        "default_url_used": not configured,
        "endpoint": "/system_stats",
    }
    if ok:
        details["system_stats_keys"] = sorted(data.keys()) if isinstance(data, dict) else []
        return _response(
            ok=True,
            action="status",
            message="ComfyUI API is reachable.",
            details=details,
            next_steps=["Run validate_workflow before queueing any workflow."],
        )

    details["error"] = error
    return _response(
        ok=False,
        action="status",
        message="ComfyUI API is not reachable.",
        details=details,
        warnings=["ComfyUI may not be running, or the API URL may be wrong."],
        next_steps=[
            "Start ComfyUI locally.",
            f"Set {URL_ENV} if your ComfyUI API is not at {DEFAULT_URL}.",
            "Use dry_run queue checks before enabling real queue submission.",
        ],
    )


def probe() -> dict[str, Any]:
    """Read ComfyUI system stats and return a structured probe result."""
    ok, data, error = _read_json("/system_stats")
    details = {"url": _base_url(), "endpoint": "/system_stats"}
    if ok:
        details["system_stats"] = data
        return _response(ok=True, action="probe", message="ComfyUI system stats loaded.", details=details)

    details["error"] = error
    return _response(
        ok=False,
        action="probe",
        message="Failed to probe ComfyUI.",
        details=details,
        warnings=["No ComfyUI system stats could be read."],
        next_steps=["Confirm ComfyUI is running and the API port is reachable."],
    )


def list_models() -> dict[str, Any]:
    """Try to read checkpoint model names from ComfyUI object_info."""
    ok, data, error = _read_json("/object_info/CheckpointLoaderSimple")
    details: dict[str, Any] = {"url": _base_url(), "endpoint": "/object_info/CheckpointLoaderSimple", "models": []}
    if not ok:
        details["error"] = error
        return _response(
            ok=False,
            action="list_models",
            message="Could not read ComfyUI model information.",
            details=details,
            warnings=["ComfyUI is not reachable or this endpoint is not supported."],
            next_steps=["Start ComfyUI and retry.", "If the endpoint is unavailable, query object_info manually."],
        )

    try:
        node_info = data["CheckpointLoaderSimple"]
        choices = node_info["input"]["required"]["ckpt_name"][0]
        if isinstance(choices, list):
            details["models"] = choices
    except (KeyError, TypeError, IndexError):
        return _response(
            ok=False,
            action="list_models",
            message="ComfyUI responded, but checkpoint names were not found.",
            details={"url": _base_url(), "endpoint": "/object_info/CheckpointLoaderSimple", "raw_keys": sorted(data.keys()) if isinstance(data, dict) else []},
            warnings=["The response shape does not match the expected CheckpointLoaderSimple schema."],
            next_steps=["Inspect /object_info in your ComfyUI instance."],
        )

    return _response(
        ok=True,
        action="list_models",
        message=f"Found {len(details['models'])} checkpoint model(s).",
        details=details,
    )


def _load_workflow(workflow_json: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(workflow_json, str):
        try:
            parsed = json.loads(workflow_json)
        except json.JSONDecodeError as exc:
            return None, f"Invalid JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "Workflow JSON must decode to an object/dict."
        return parsed, None
    if isinstance(workflow_json, dict):
        return workflow_json, None
    return None, "Workflow must be a dict or JSON string."


def validate_workflow(workflow_json: Any) -> dict[str, Any]:
    """Validate minimal ComfyUI workflow structure without executing it."""
    workflow, error = _load_workflow(workflow_json)
    if error:
        return _response(
            ok=False,
            action="validate_workflow",
            message="Workflow validation failed.",
            details={"error": error},
            warnings=["Workflow is not valid JSON object input."],
            next_steps=["Pass a dict or a JSON string containing an object."],
        )

    if not workflow:
        return _response(
            ok=False,
            action="validate_workflow",
            message="Workflow validation failed.",
            details={"node_count": 0},
            warnings=["Workflow is empty."],
            next_steps=["Provide at least one ComfyUI node."],
        )

    nodes = workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else list(workflow.values())
    if not nodes:
        return _response(
            ok=False,
            action="validate_workflow",
            message="Workflow validation failed.",
            details={"node_count": 0},
            warnings=["No nodes were found."],
            next_steps=["Use API-format nodes or a UI-format nodes list."],
        )

    invalid_nodes: list[str] = []
    class_type_count = 0
    for key, node in enumerate(nodes):
        node_name = str(key)
        if isinstance(workflow, dict) and "nodes" not in workflow:
            node_name = str(list(workflow.keys())[key])
        if not isinstance(node, dict):
            invalid_nodes.append(node_name)
            continue
        if node.get("class_type") or node.get("type"):
            class_type_count += 1

    ok = not invalid_nodes and class_type_count > 0
    return _response(
        ok=ok,
        action="validate_workflow",
        message="Workflow structure looks usable." if ok else "Workflow validation failed.",
        details={
            "node_count": len(nodes),
            "class_type_count": class_type_count,
            "invalid_nodes": invalid_nodes,
            "format": "ui" if "nodes" in workflow else "api",
        },
        warnings=[] if ok else ["At least one node is invalid or missing class/type information."],
        next_steps=["Run queue_workflow with dry_run=True first."] if ok else ["Fix node structure before queueing."],
    )


def queue_workflow(workflow_json: Any, dry_run: bool = True) -> dict[str, Any]:
    """Queue a workflow only when explicitly allowed; dry-run is the default."""
    validation = validate_workflow(workflow_json)
    details = {"dry_run": dry_run, "url": _base_url(), "validation": validation["details"]}
    if not validation["ok"]:
        return _response(
            ok=False,
            action="queue_workflow",
            message="Workflow was not queued because validation failed.",
            details=details,
            warnings=validation["warnings"],
            next_steps=validation["next_steps"],
        )

    workflow, _ = _load_workflow(workflow_json)
    if dry_run:
        return _response(
            ok=True,
            action="queue_workflow",
            message="Dry-run only: workflow was validated but not submitted.",
            details=details,
            warnings=["No ComfyUI task was queued."],
            next_steps=[f"Set {ALLOW_QUEUE_ENV}=true and pass dry_run=False only when you intentionally want to queue."],
        )

    if not _allow_real_queue():
        return _response(
            ok=False,
            action="queue_workflow",
            message="Real queue submission is disabled.",
            details=details,
            warnings=["This safety gate prevents accidental large ComfyUI jobs."],
            next_steps=[f"Set {ALLOW_QUEUE_ENV}=true to allow real queue submission, then retry with dry_run=False."],
        )

    ok, data, error = _post_json("/prompt", {"prompt": workflow})
    if ok:
        details["queue_response"] = data
        return _response(ok=True, action="queue_workflow", message="Workflow submitted to ComfyUI.", details=details)

    details["error"] = error
    return _response(
        ok=False,
        action="queue_workflow",
        message="Failed to submit workflow to ComfyUI.",
        details=details,
        warnings=["ComfyUI rejected the request or is not reachable."],
        next_steps=["Check ComfyUI logs and retry with dry_run=True before submitting again."],
    )
