from __future__ import annotations

from pathlib import Path
from typing import Any

from starbridge_mcp.core.security import sanitize
from starbridge_mcp.domain.models import validate_id
from starbridge_mcp.storage.atomic_json import atomic_write_json, read_json


class EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def manifest_file(self, evidence_id: str) -> Path:
        validate_id(evidence_id, "evidenceId")
        return self.root / evidence_id / "manifest.json"

    def save(self, evidence_id: str, payload: dict[str, Any]) -> Path:
        target = self.manifest_file(evidence_id)
        atomic_write_json(target, sanitize(payload))
        return target

    def get(self, evidence_id: str) -> dict[str, Any]:
        return read_json(self.manifest_file(evidence_id))
