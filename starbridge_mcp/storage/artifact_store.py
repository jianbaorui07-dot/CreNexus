from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

from starbridge_mcp.domain.errors import DomainValidationError
from starbridge_mcp.domain.models import Artifact, validate_basename, validate_id
from starbridge_mcp.storage.asset_store import file_sha256


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def job_directory(self, project_id: str, job_id: str) -> Path:
        validate_id(project_id, "projectId")
        validate_id(job_id, "jobId")
        directory = self.root / project_id / job_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def allocate_path(self, project_id: str, job_id: str, basename: str) -> Path:
        validate_basename(basename)
        target = self.job_directory(project_id, job_id) / basename
        if target.exists():
            raise FileExistsError(f"artifact already exists: {basename}")
        return target

    def register(self, project_id: str, job_id: str, path: Path, *, kind: str) -> Artifact:
        validate_id(kind, "kind")
        allowed = self.job_directory(project_id, job_id).resolve()
        resolved = path.resolve(strict=True)
        try:
            relative_to_job = resolved.relative_to(allowed)
        except ValueError as exc:
            raise DomainValidationError(
                "artifact must stay inside the job artifact directory"
            ) from exc
        if not resolved.is_file():
            raise DomainValidationError("artifact path must identify one file")
        relative_path = resolved.relative_to(self.root.parent).as_posix()
        return Artifact(
            artifact_id=f"artifact-{uuid4().hex[:16]}",
            kind=kind,
            basename=relative_to_job.name,
            relative_path=relative_path,
            sha256=file_sha256(resolved),
            media_type=mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
            size_bytes=resolved.stat().st_size,
        )
