from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from starbridge_mcp.core.security import sanitize


VALID_JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled", "needs_user")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "examples" / "output" / "evidence"
DEFAULT_MANIFEST_FILENAME = "manifest.latest.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_path_string(value: str) -> str:
    return str(sanitize(value))


def ensure_status(value: str) -> str:
    if value not in VALID_JOB_STATUSES:
        raise ValueError(f"status must be one of {', '.join(VALID_JOB_STATUSES)}")
    return value


def evidence_root() -> Path:
    DEFAULT_EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_EVIDENCE_ROOT


def ensure_evidence_path(path: str | Path | None = None) -> Path:
    candidate = Path(path) if path is not None else evidence_root() / DEFAULT_MANIFEST_FILENAME
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    resolved = candidate.resolve()
    root = evidence_root().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence path must stay inside examples/output/evidence") from exc
    if resolved.suffix.lower() != ".json":
        raise ValueError("evidence manifest path must end with .json")
    return resolved


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


@dataclass(frozen=True)
class ValidationResult:
    name: str
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "name": self.name,
                "ok": self.ok,
                "message": self.message,
                "details": self.details,
                "warnings": self.warnings,
            }
        )


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    path: str
    label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "kind": self.kind,
                "path": self.path,
                "label": self.label,
                "details": self.details,
            }
        )


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    status: str
    message: str
    manifest_path: str
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "ok": self.ok,
                "status": self.status,
                "message": self.message,
                "manifest_path": self.manifest_path,
                "warnings": self.warnings,
                "next_steps": self.next_steps,
            }
        )


@dataclass
class EvidenceManifest:
    bridge: str
    action: str
    status: str = "queued"
    dry_run: bool = True
    confirm_write: bool = False
    manifest_id: str = field(default_factory=lambda: f"manifest_{uuid4().hex[:12]}")
    plan_id: str | None = None
    job_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_files: list[EvidenceItem] = field(default_factory=list)
    screenshots: list[EvidenceItem] = field(default_factory=list)
    validation: list[ValidationResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safety_decision: dict[str, Any] = field(default_factory=dict)
    redacted_paths: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.status = ensure_status(self.status)

    def add_output_file(self, path: str, *, label: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.output_files.append(EvidenceItem(kind="file", path=sanitize_path_string(path), label=label, details=details or {}))
        self.redacted_paths.append(sanitize_path_string(path))
        self.updated_at = utc_now_iso()

    def add_screenshot(self, path: str, *, label: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.screenshots.append(EvidenceItem(kind="screenshot", path=sanitize_path_string(path), label=label, details=details or {}))
        self.redacted_paths.append(sanitize_path_string(path))
        self.updated_at = utc_now_iso()

    def add_validation(self, result: ValidationResult) -> None:
        self.validation.append(result)
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "manifest_id": self.manifest_id,
                "bridge": self.bridge,
                "action": self.action,
                "plan_id": self.plan_id,
                "job_id": self.job_id,
                "status": self.status,
                "dry_run": self.dry_run,
                "confirm_write": self.confirm_write,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "input_summary": self.input_summary,
                "output_files": [item.to_dict() for item in self.output_files],
                "screenshots": [item.to_dict() for item in self.screenshots],
                "validation": [item.to_dict() for item in self.validation],
                "warnings": self.warnings,
                "safety_decision": self.safety_decision,
                "redacted_paths": self.redacted_paths,
                "notes": self.notes,
            }
        )


def create_manifest(
    *,
    bridge: str = "starbridge",
    action: str = "evidence_init",
    status: str = "queued",
    dry_run: bool = True,
    confirm_write: bool = False,
    plan_id: str | None = None,
    job_id: str | None = None,
    input_summary: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> EvidenceManifest:
    manifest = EvidenceManifest(
        bridge=bridge,
        action=action,
        status=status,
        dry_run=dry_run,
        confirm_write=confirm_write,
        plan_id=plan_id,
        job_id=job_id,
        input_summary=input_summary or {},
        notes=notes or [],
    )
    manifest.redacted_paths.append(sanitize_path_string(str(ensure_evidence_path())))
    return manifest


def validate_manifest_payload(payload: dict[str, Any]) -> list[str]:
    required = {
        "manifest_id",
        "bridge",
        "action",
        "status",
        "dry_run",
        "confirm_write",
        "created_at",
        "updated_at",
        "input_summary",
        "output_files",
        "screenshots",
        "validation",
        "warnings",
        "safety_decision",
        "redacted_paths",
        "notes",
    }
    failures = sorted(required - set(payload))
    if failures:
        return [f"missing fields: {', '.join(failures)}"]
    try:
        ensure_status(str(payload["status"]))
    except ValueError as exc:
        return [str(exc)]
    if not isinstance(payload["dry_run"], bool):
        return ["dry_run must be bool"]
    if not isinstance(payload["confirm_write"], bool):
        return ["confirm_write must be bool"]
    for key in ("input_summary", "safety_decision"):
        if not isinstance(payload[key], dict):
            return [f"{key} must be dict"]
    for key in ("output_files", "screenshots", "validation", "warnings", "redacted_paths", "notes"):
        if not isinstance(payload[key], list):
            return [f"{key} must be list"]
    return []


def manifest_validation_result(payload: dict[str, Any]) -> ValidationResult:
    failures = validate_manifest_payload(payload)
    return ValidationResult(
        name="manifest_schema",
        ok=not failures,
        message="manifest is valid" if not failures else "; ".join(failures),
        details={"status": payload.get("status"), "manifest_id": payload.get("manifest_id")},
        warnings=[] if not failures else failures,
    )


def save_manifest(manifest: EvidenceManifest, path: str | Path | None = None) -> Path:
    target = ensure_evidence_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    target = ensure_evidence_path(path)
    if not target.exists():
        raise FileNotFoundError(f"missing evidence manifest: {repo_relative(target)}")
    return json.loads(target.read_text(encoding="utf-8"))

