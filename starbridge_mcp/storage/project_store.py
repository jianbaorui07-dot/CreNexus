from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import RLock
from uuid import uuid4

from starbridge_mcp.domain.errors import RecordNotFoundError
from starbridge_mcp.domain.models import Project, utc_now_iso, validate_id
from starbridge_mcp.storage.atomic_json import atomic_write_json, read_json


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def project_directory(self, project_id: str) -> Path:
        validate_id(project_id, "projectId")
        return self.root / project_id

    def project_file(self, project_id: str) -> Path:
        return self.project_directory(project_id) / "project.json"

    def create(self, project_name: str, workflow_id: str, description: str = "") -> Project:
        project = Project(
            project_id=f"project-{uuid4().hex[:16]}",
            project_name=project_name,
            workflow_id=workflow_id,
            description=description,
        )
        return self.save(project, create_only=True)

    def save(self, project: Project, *, create_only: bool = False) -> Project:
        target = self.project_file(project.project_id)
        with self._lock:
            if create_only and target.exists():
                raise FileExistsError(f"project already exists: {project.project_id}")
            updated = replace(project, updated_at=utc_now_iso())
            atomic_write_json(target, updated.to_dict())
        return updated

    def get(self, project_id: str) -> Project:
        target = self.project_file(project_id)
        with self._lock:
            if not target.is_file():
                raise RecordNotFoundError(f"project not found: {project_id}")
            return Project.from_dict(read_json(target))

    def list(self) -> list[Project]:
        projects: list[Project] = []
        with self._lock:
            for target in sorted(self.root.glob("*/project.json")):
                try:
                    projects.append(Project.from_dict(read_json(target)))
                except (KeyError, TypeError, ValueError):
                    continue
        return sorted(projects, key=lambda project: project.updated_at, reverse=True)
