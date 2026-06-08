from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .schemas import ADAPTER_NAME, ADAPTER_VERSION, EvidenceManifest


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wn13dQAAAAASUVORK5CYII="
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_job_id() -> str:
    return uuid4().hex[:12]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_placeholder_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_PNG_1X1)


def manifest_path_for(base_dir: Path, tool_name: str, job_id: str) -> Path:
    slug = tool_name.replace(".", "_")
    return base_dir / f"{slug}_{job_id}_manifest.json"


def preview_path_for(base_dir: Path, job_id: str) -> Path:
    return base_dir / f"ps_preview_{job_id}.png"


def build_manifest(
    *,
    job_id: str,
    tool_name: str,
    risk_level: str,
    requires_confirmation: bool,
    dry_run: bool,
    input_summary: dict,
    output_files: list[str],
    preview_files: list[str],
    source_files: list[str],
    photoshop_available: bool,
    bridge_kind: str,
    status: str,
    warnings: list[str],
    errors: list[str],
) -> EvidenceManifest:
    return EvidenceManifest(
        job_id=job_id,
        created_at=utc_now_iso(),
        adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION,
        tool_name=tool_name,
        risk_level=risk_level,
        requires_confirmation=requires_confirmation,
        dry_run=dry_run,
        input_summary=input_summary,
        output_files=output_files,
        preview_files=preview_files,
        source_files=source_files,
        photoshop_available=photoshop_available,
        bridge_kind=bridge_kind,
        status=status,
        warnings=warnings,
        errors=errors,
    )
