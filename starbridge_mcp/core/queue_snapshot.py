from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from starbridge_mcp.core.queue_snapshot_schema import MAX_PROGRESS_VALUE, SCHEMA_VERSION
from starbridge_mcp.core.security import sanitize

DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
MAX_QUEUE_BYTES = 1_048_576
MAX_QUEUE_ITEMS = 1_000

QueueFetcher = Callable[[str, int], dict[str, Any]]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _validate_loopback_url(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError("comfy_url must be a plain loopback HTTP URL")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("comfy_url must be a plain loopback HTTP URL") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise ValueError("comfy_url must be a plain loopback HTTP URL")
    return value.rstrip("/")


def _read_queue(base_url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/queue",
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_QUEUE_BYTES + 1)
    if len(raw) > MAX_QUEUE_BYTES:
        raise ValueError("queue payload exceeds the safe response limit")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("queue payload must be an object")
    return payload


def _logical_job_id(raw_job_id: Any) -> str:
    if not isinstance(raw_job_id, str) or not raw_job_id or len(raw_job_id) > 512:
        raise ValueError("queue item has an invalid job id")
    digest = hashlib.sha256(raw_job_id.encode("utf-8")).hexdigest()[:12]
    return f"job_{digest}"


def _job_summaries(items: Any, status: str) -> list[dict[str, Any]]:
    if not isinstance(items, list) or len(items) > MAX_QUEUE_ITEMS:
        raise ValueError("queue payload contains an invalid item list")
    summaries: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise ValueError("queue payload contains a malformed item")
        summaries.append(
            {
                "logical_job_id": _logical_job_id(item[1]),
                "status": status,
                "position": index if status == "running" else index + 1,
            }
        )
    return summaries


def _progress_summary(progress: Any) -> dict[str, Any]:
    empty = {
        "available": False,
        "source": "not_available",
        "current": None,
        "total": None,
        "percent": None,
        "monotonic": False,
    }
    if progress is None:
        return empty
    if not isinstance(progress, dict) or set(progress) - {"current", "total", "previous"}:
        raise ValueError("progress must contain only numeric current, total, and previous fields")
    if "current" not in progress or "total" not in progress:
        raise ValueError("progress requires current and total")

    current = progress["current"]
    total = progress["total"]
    previous = progress.get("previous", 0)
    if type(current) is not int or type(total) is not int or type(previous) is not int:
        raise ValueError("progress values must be integers")
    if (
        current < 0
        or total < 1
        or previous < 0
        or current > MAX_PROGRESS_VALUE
        or total > MAX_PROGRESS_VALUE
        or previous > MAX_PROGRESS_VALUE
        or current > total
        or previous > current
    ):
        raise ValueError("progress must be bounded and monotonic")
    return {
        "available": True,
        "source": "caller_supplied",
        "current": current,
        "total": total,
        "percent": round(current * 100 / total, 2),
        "monotonic": True,
    }


def normalize_queue_payload(payload: Any, *, max_items: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("queue payload must be an object")
    running = _job_summaries(payload.get("queue_running"), "running")
    pending = _job_summaries(payload.get("queue_pending"), "pending")
    running_count = len(running)
    pending_count = len(pending)
    depth = running_count + pending_count

    returned_running = running[:max_items]
    remaining_slots = max(0, max_items - len(returned_running))
    returned_pending = pending[:remaining_slots]
    return {
        "running_count": running_count,
        "pending_count": pending_count,
        "depth": depth,
        "busy": depth > 0,
        "backlog": depth > 1,
        "safe_to_enqueue": depth == 0,
        "truncated": len(returned_running) + len(returned_pending) < depth,
        "running_jobs": returned_running,
        "pending_jobs": returned_pending,
    }


def _empty_queue() -> dict[str, Any]:
    return {
        "running_count": 0,
        "pending_count": 0,
        "depth": 0,
        "busy": False,
        "backlog": False,
        "safe_to_enqueue": False,
        "truncated": False,
        "running_jobs": [],
        "pending_jobs": [],
    }


def _snapshot_id(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"queue_{hashlib.sha256(canonical).hexdigest()[:12]}"


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    payload["snapshot_id"] = _snapshot_id(payload)
    return sanitize(payload)


def _safety(*, network_access: bool) -> dict[str, Any]:
    return {
        "network_access": network_access,
        "loopback_only": True,
        "redirects_followed": False,
        "workflow_payloads_returned": False,
        "prompt_ids_returned": False,
        "history_read": False,
        "queue_mutation": False,
        "local_file_reads": False,
        "local_file_writes": False,
        "desktop_software_started": False,
    }


def queue_snapshot_contract() -> dict[str, Any]:
    return {
        "tool": "comfyui.queue_snapshot",
        "schema_version": SCHEMA_VERSION,
        "endpoint": "/queue",
        "default_probe": False,
        "live_scope": "loopback_http_only",
        "workflow_payloads_returned": False,
        "history_read": False,
        "queue_mutation": False,
        "progress_source": "caller_supplied_numeric_event_only",
    }


def build_queue_snapshot(
    *,
    probe: bool = False,
    comfy_url: str = DEFAULT_COMFY_URL,
    timeout: int = 5,
    max_items: int = 25,
    progress: dict[str, int] | None = None,
    fetcher: QueueFetcher | None = None,
) -> dict[str, Any]:
    if type(probe) is not bool:
        raise ValueError("probe must be boolean")
    if type(timeout) is not int or not 1 <= timeout <= 15:
        raise ValueError("timeout must be an integer between 1 and 15")
    if type(max_items) is not int or not 1 <= max_items <= 100:
        raise ValueError("max_items must be an integer between 1 and 100")
    base_url = _validate_loopback_url(comfy_url)
    safe_progress = _progress_summary(progress)

    common: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "bridge": "comfyui",
        "action": "queue_snapshot",
        "endpoint": "/queue",
        "progress": safe_progress,
    }
    if not probe:
        return _finalize(
            {
                "ok": True,
                **common,
                "mode": "planned",
                "connected": False,
                "decision": "planned",
                "queue": _empty_queue(),
                "error_code": None,
                "warnings": ["live_queue_not_probed"],
                "redactions_applied": False,
                "safety": _safety(network_access=False),
                "next_steps": [
                    "Call again with probe=true to read the loopback queue before any guarded submit."
                ],
            }
        )

    try:
        queue = (fetcher or _read_queue)(base_url, timeout)
        summary = normalize_queue_payload(queue, max_items=max_items)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _finalize(
            {
                "ok": False,
                **common,
                "mode": "live",
                "connected": False,
                "decision": "unavailable",
                "queue": _empty_queue(),
                "error_code": "queue_payload_invalid",
                "warnings": ["queue_payload_rejected"],
                "redactions_applied": False,
                "safety": _safety(network_access=True),
                "next_steps": [
                    "Check the local ComfyUI version and retry the read-only queue probe."
                ],
            }
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        return _finalize(
            {
                "ok": False,
                **common,
                "mode": "live",
                "connected": False,
                "decision": "unavailable",
                "queue": _empty_queue(),
                "error_code": "queue_endpoint_unavailable",
                "warnings": ["loopback_queue_unavailable"],
                "redactions_applied": False,
                "safety": _safety(network_access=True),
                "next_steps": [
                    "Start local ComfyUI and retry without changing the safety boundary."
                ],
            }
        )

    decision = "idle" if summary["depth"] == 0 else "busy"
    if summary["backlog"]:
        decision = "backlog"
    next_steps = ["Queue is idle; guarded submission still requires explicit confirmation."]
    if decision == "busy":
        next_steps = ["Wait for the running job to finish before considering another submit."]
    elif decision == "backlog":
        next_steps = [
            "Do not enqueue another job until the running and pending backlog is reviewed."
        ]

    return _finalize(
        {
            "ok": True,
            **common,
            "mode": "live",
            "connected": True,
            "decision": decision,
            "queue": summary,
            "error_code": None,
            "warnings": [],
            "redactions_applied": summary["depth"] > 0,
            "safety": _safety(network_access=True),
            "next_steps": next_steps,
        }
    )
