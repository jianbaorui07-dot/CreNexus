"""Validate or publish one in-app Codex progress update."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any

from starbridge_mcp.adapters.autocad.live_session import (
    AutoCadVisibleSession,
    normalize_live_update,
)

PORTS = {"photoshop": 8971, "illustrator": 8972}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--bridge", choices=("photoshop", "illustrator", "autocad"), required=True)
    value.add_argument("--session-id", default="codex-live")
    value.add_argument(
        "--phase",
        choices=("queued", "running", "completed", "failed", "cancelled", "needs_user"),
        default="running",
    )
    value.add_argument("--mode", choices=("structured", "computer_use"), default="structured")
    value.add_argument("--step-id", default="work")
    value.add_argument("--step-label", default="执行任务")
    value.add_argument("--step-index", type=int, default=1)
    value.add_argument("--step-total", type=int, default=1)
    value.add_argument("--message", default="Codex 正在工作")
    value.add_argument("--progress", type=int, default=50)
    value.add_argument("--publish", action="store_true", help="Send to the active local application bridge")
    value.add_argument("--soft-exit", action="store_true", help="Return success after printing an error payload")
    return value


def build_update(arguments: argparse.Namespace) -> dict[str, Any]:
    return normalize_live_update(
        {
            "type": "codex_session",
            "protocol_version": 1,
            "session_id": arguments.session_id,
            "bridge": arguments.bridge,
            "mode": arguments.mode,
            "phase": arguments.phase,
            "step": {
                "id": arguments.step_id,
                "label": arguments.step_label,
                "index": arguments.step_index,
                "total": arguments.step_total,
            },
            "message": arguments.message,
            "progress": arguments.progress,
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        expected_bridge=arguments.bridge,
    )


def publish_http(update: dict[str, Any]) -> dict[str, Any]:
    port = PORTS[update["bridge"]]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/session",
        data=json.dumps(update, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        update = build_update(arguments)
        if not arguments.publish:
            result: dict[str, Any] = {"ok": True, "published": False, "update": update}
        elif update["bridge"] == "autocad":
            result = AutoCadVisibleSession.connect_active().publish(update)
        else:
            result = publish_http(update)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 0 if arguments.soft_exit else 1


if __name__ == "__main__":
    sys.exit(main())
