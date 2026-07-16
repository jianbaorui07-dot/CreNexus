from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .security import sanitize

APP_DATA_ENV = "STARBRIDGE_APP_DATA_DIR"


@dataclass(frozen=True)
class AppDataPaths:
    root: Path
    data: Path
    history: Path
    logs: Path
    cache: Path
    diagnostics: Path

    @property
    def history_file(self) -> Path:
        return self.history / "history.json"

    @property
    def runtime_log(self) -> Path:
        return self.logs / "backend.jsonl"

    def ensure(self) -> AppDataPaths:
        for path in (
            self.root,
            self.data,
            self.history,
            self.logs,
            self.cache,
            self.diagnostics,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _default_root() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "StarBridge"
        return Path.home() / "AppData" / "Local" / "StarBridge"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "StarBridge"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "StarBridge"
    return Path.home() / ".local" / "share" / "StarBridge"


def resolve_app_data_paths(
    override: str | Path | None = None, *, create: bool = True
) -> AppDataPaths:
    configured = override if override is not None else os.environ.get(APP_DATA_ENV)
    root = Path(configured).expanduser() if configured else _default_root()
    root = root.resolve(strict=False)
    paths = AppDataPaths(
        root=root,
        data=root / "data",
        history=root / "history",
        logs=root / "logs",
        cache=root / "cache",
        diagnostics=root / "diagnostics",
    )
    return paths.ensure() if create else paths


def append_runtime_log(
    paths: AppDataPaths, event: str, details: dict[str, Any] | None = None
) -> None:
    payload = sanitize(
        {
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": event,
            "details": details or {},
        }
    )
    paths.logs.mkdir(parents=True, exist_ok=True)
    with paths.runtime_log.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_crash_diagnostic(paths: AppDataPaths, *, error_type: str, summary: str) -> Path:
    payload = sanitize(
        {
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": "backend_crash",
            "error_type": error_type,
            "summary": summary,
            "contains_traceback": False,
        }
    )
    paths.diagnostics.mkdir(parents=True, exist_ok=True)
    target = paths.diagnostics / f"backend-crash-{uuid4().hex[:12]}.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
