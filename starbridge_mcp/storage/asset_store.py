from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from pathlib import Path
from uuid import uuid4

from starbridge_mcp.domain.errors import ConfirmationRequiredError, DomainValidationError
from starbridge_mcp.domain.models import SourceAsset, validate_id

MAX_SOURCE_ASSET_BYTES = 512 * 1024 * 1024


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AssetStore:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve(strict=False)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def import_source(
        self,
        project_id: str,
        source_path: str | Path,
        *,
        confirm_import: bool,
    ) -> SourceAsset:
        validate_id(project_id, "projectId")
        if not confirm_import:
            raise ConfirmationRequiredError("source import requires explicit confirmation")
        source = Path(source_path)
        if not source.is_file():
            raise DomainValidationError("sourcePath must identify one readable file")
        size_bytes = source.stat().st_size
        if size_bytes > MAX_SOURCE_ASSET_BYTES:
            raise DomainValidationError("source asset exceeds the 512 MiB safety limit")

        asset_id = f"asset-{uuid4().hex[:16]}"
        suffix = source.suffix.lower()
        managed_name = f"{asset_id}{suffix}"
        source_directory = self.projects_root / project_id / "source"
        source_directory.mkdir(parents=True, exist_ok=True)
        target = source_directory / managed_name
        temporary = source_directory / f".{managed_name}.{uuid4().hex}.tmp"
        try:
            with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

        return SourceAsset(
            asset_id=asset_id,
            basename=source.name,
            relative_path=f"projects/{project_id}/source/{managed_name}",
            sha256=file_sha256(target),
            media_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            size_bytes=size_bytes,
        )
