from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .compiler import compile_input, recipe_spec
from .model import (
    DiagramDocument,
    document_cell_hashes,
    document_sha256,
    from_drawio_xml,
    stable_id,
    to_drawio_xml,
)
from .render import render_svg
from .validation import validate_document

SAFE_ROOTS = ("sandbox", "output", "examples/output/diagramforge")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _drawio_executable() -> str | None:
    configured = os.environ.get("DRAWIO_EXE", "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and candidate.suffix.lower() in {".exe", ".cmd"}:
            return str(candidate)
        return None
    return shutil.which("drawio") or shutil.which("draw.io")


class DiagramForgeService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _safe_path(self, value: str, *, suffixes: set[str] | None = None) -> Path:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("DiagramForge paths must be repository-relative safe paths")
        candidate = (self.repo_root / path).resolve()
        allowed = [(self.repo_root / root).resolve() for root in SAFE_ROOTS]
        if not any(candidate == root or root in candidate.parents for root in allowed):
            raise ValueError(
                "DiagramForge paths must stay inside sandbox/, output/, or examples/output/diagramforge/"
            )
        if suffixes and candidate.suffix.lower() not in suffixes:
            raise ValueError(f"DiagramForge path must use one of: {sorted(suffixes)}")
        return candidate

    def probe(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        executable = _drawio_executable()
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "probe",
            "details": {
                "headless_compiler": True,
                "drawio_desktop_available": bool(executable),
                "native_drawio": True,
                "svg_preview": True,
                "pdf_export": bool(executable),
                "live_mcp_adapter": "optional_external",
                "connection_state": "headless_ready",
            },
            "warnings": []
            if executable
            else ["The Draw.io desktop app was not found; PDF export is unavailable."],
        }

    def capabilities(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "capabilities",
            "details": {
                "inputs": ["natural_language", "outline", "mermaid", "csv", "spec", "drawio_xml"],
                "elements": ["node", "container", "group", "connector", "label", "layer", "page"],
                "outputs": ["drawio", "drawio.svg", "manifest", "pdf_with_drawio_desktop"],
                "recipes": ["research-framework-v1", "system-architecture-v1"],
                "stable_ids": True,
                "incremental_patch": True,
                "transactional_writes": True,
                "one_level_rollback_redo": True,
                "batch_resume": True,
                "layout_engines": ["diagramforge-semantic-v1"],
                "optional_upstream_adapters": ["@drawio/mcp", "drawio-mcp-server"],
            },
        }

    def plan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        document = compile_input(
            input_format=str(arguments.get("input_format") or "spec"),
            content=str(arguments.get("content") or ""),
            spec=arguments.get("spec") if isinstance(arguments.get("spec"), dict) else None,
            recipe_id=str(arguments.get("recipe_id") or "") or None,
            parameters=arguments.get("parameters")
            if isinstance(arguments.get("parameters"), dict)
            else None,
        )
        report = validate_document(document)
        return {
            "ok": report.ok,
            "bridge": "diagramforge",
            "action": "plan",
            "details": {
                "document": document.to_dict(),
                "document_sha256": document_sha256(document),
                "validation": report.to_dict(),
                "writes_files": False,
            },
        }

    def create(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not bool(arguments.get("confirm_write")):
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "create",
                "error": {
                    "code": "confirmation_required",
                    "suggested_next_action": "call drawio.plan first",
                },
            }
        document = compile_input(
            input_format=str(arguments.get("input_format") or "spec"),
            content=str(arguments.get("content") or ""),
            spec=arguments.get("spec") if isinstance(arguments.get("spec"), dict) else None,
            recipe_id=str(arguments.get("recipe_id") or "") or None,
            parameters=arguments.get("parameters")
            if isinstance(arguments.get("parameters"), dict)
            else None,
        )
        report = validate_document(document)
        if not report.ok:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "create",
                "validation": report.to_dict(),
            }
        output_base = str(
            arguments.get("output_base") or "examples/output/diagramforge/diagramforge"
        )
        drawio_path = self._safe_path(f"{output_base}.drawio", suffixes={".drawio"})
        svg_path = self._safe_path(f"{output_base}.drawio.svg", suffixes={".svg"})
        manifest_path = self._safe_path(f"{output_base}.manifest.json", suffixes={".json"})
        xml_text = to_drawio_xml(document)
        svg_text = render_svg(document)
        in_memory_reopen = from_drawio_xml(xml_text)
        roundtrip_hash_match = document_sha256(in_memory_reopen) == document_sha256(document)
        if not roundtrip_hash_match:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "create",
                "error": {"code": "native_roundtrip_mismatch"},
            }
        _atomic_write(drawio_path, xml_text)
        reopened = from_drawio_xml(drawio_path.read_text(encoding="utf-8"))
        reopen_report = validate_document(reopened)
        _atomic_write(svg_path, svg_text)
        manifest = {
            "schema_version": "diagramforge.manifest.v1",
            "document_id": document.document_id,
            "document_sha256": document_sha256(document),
            "files": [
                {
                    "role": "native",
                    "basename": drawio_path.name,
                    "sha256": _sha256_bytes(drawio_path.read_bytes()),
                },
                {
                    "role": "preview",
                    "basename": svg_path.name,
                    "sha256": _sha256_bytes(svg_path.read_bytes()),
                },
            ],
            "structure": report.metrics,
            "validated_after_reopen": reopen_report.ok,
            "roundtrip_hash_match": roundtrip_hash_match,
            "source_paths_persisted": False,
        }
        _atomic_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return {
            "ok": reopen_report.ok,
            "bridge": "diagramforge",
            "action": "create",
            "details": {
                "files": [
                    drawio_path.relative_to(self.repo_root).as_posix(),
                    svg_path.relative_to(self.repo_root).as_posix(),
                    manifest_path.relative_to(self.repo_root).as_posix(),
                ],
                "validation": report.to_dict(),
                "validated_after_reopen": reopen_report.ok,
                "roundtrip_hash_match": roundtrip_hash_match,
                "document_sha256": document_sha256(document),
            },
        }

    def inspect(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments.get("path") or ""), suffixes={".drawio"})
        document = from_drawio_xml(path.read_text(encoding="utf-8"))
        report = validate_document(document)
        return {
            "ok": report.ok,
            "bridge": "diagramforge",
            "action": "inspect",
            "details": {
                "document": document.to_dict(),
                "document_sha256": document_sha256(document),
                "cell_hashes": document_cell_hashes(document),
                "validation": report.to_dict(),
            },
        }

    @staticmethod
    def _apply_patch(document: DiagramDocument, patch: dict[str, Any]) -> list[str]:
        operation = str(patch.get("op") or "")
        element_id = str(patch.get("element_id") or "")
        cells = [cell for page in document.pages for cell in page.cells]
        target = next((cell for cell in cells if cell.cell_id == element_id), None)
        if target is None:
            raise ValueError("Patch element_id was not found")
        if operation == "set_label":
            target.label = str(patch.get("label") or "")[:500]
        elif operation == "move":
            target.x = float(patch.get("x", target.x))
            target.y = float(patch.get("y", target.y))
        elif operation == "set_style":
            style = str(patch.get("style") or "")
            if "javascript" in style.lower() or "url(" in style.lower():
                raise ValueError("Unsafe Draw.io style content is not allowed")
            target.style = style[:2000]
        else:
            raise ValueError("Patch op must be set_label, move, or set_style")
        return [element_id]

    def patch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not bool(arguments.get("confirm_write")):
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "patch",
                "error": {
                    "code": "confirmation_required",
                    "suggested_next_action": "inspect the document first",
                },
            }
        path = self._safe_path(str(arguments.get("path") or ""), suffixes={".drawio"})
        original = from_drawio_xml(path.read_text(encoding="utf-8"))
        candidate = deepcopy(original)
        before = document_cell_hashes(original)
        changed: list[str] = []
        for patch in arguments.get("patches") or []:
            changed.extend(self._apply_patch(candidate, patch))
        report = validate_document(candidate)
        if not report.ok:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "patch",
                "validation": report.to_dict(),
            }
        after = document_cell_hashes(candidate)
        unchanged = [
            key for key, value in before.items() if key not in changed and after.get(key) == value
        ]
        unexpected = [
            key for key, value in before.items() if key not in changed and after.get(key) != value
        ]
        if unexpected:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "patch",
                "error": {"code": "unrelated_region_changed", "element_ids": unexpected},
            }
        checkpoint_path = path.with_suffix(path.suffix + ".bak")
        _atomic_write(checkpoint_path, to_drawio_xml(original))
        _atomic_write(path, to_drawio_xml(candidate))
        svg_path = path.with_suffix(".drawio.svg")
        _atomic_write(svg_path, render_svg(candidate))
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "patch",
            "details": {
                "changed_element_ids": sorted(set(changed)),
                "unchanged_element_count": len(unchanged),
                "unrelated_region_hashes_stable": True,
                "transaction_committed": True,
                "rollback_checkpoint": checkpoint_path.name,
                "validation": report.to_dict(),
            },
        }

    def rollback(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not bool(arguments.get("confirm_write")):
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "rollback",
                "error": {"code": "confirmation_required"},
            }
        path = self._safe_path(str(arguments.get("path") or ""), suffixes={".drawio"})
        checkpoint_path = path.with_suffix(path.suffix + ".bak")
        if not checkpoint_path.is_file():
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "rollback",
                "error": {"code": "rollback_checkpoint_missing"},
            }
        current_xml = path.read_text(encoding="utf-8")
        restored_xml = checkpoint_path.read_text(encoding="utf-8")
        restored = from_drawio_xml(restored_xml)
        report = validate_document(restored)
        if not report.ok:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "rollback",
                "error": {"code": "rollback_checkpoint_invalid"},
                "validation": report.to_dict(),
            }
        _atomic_write(path, restored_xml)
        _atomic_write(path.with_suffix(".drawio.svg"), render_svg(restored))
        _atomic_write(checkpoint_path, current_xml)
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "rollback",
            "details": {
                "document_sha256": document_sha256(restored),
                "checkpoint_rotated_for_redo": True,
                "validation": report.to_dict(),
            },
        }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._safe_path(str(arguments.get("path") or ""), suffixes={".drawio"})
        document = from_drawio_xml(path.read_text(encoding="utf-8"))
        report = validate_document(document)
        return {
            "ok": report.ok,
            "bridge": "diagramforge",
            "action": "validate",
            "details": report.to_dict(),
        }

    def handoff_plan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = str(arguments.get("target") or "").lower()
        if target not in {"canvas", "photoshop", "illustrator"}:
            raise ValueError("target must be canvas, photoshop, or illustrator")
        path = self._safe_path(str(arguments.get("path") or ""), suffixes={".svg", ".pdf"})
        if not path.is_file():
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "handoff_plan",
                "error": {"code": "artifact_not_found"},
            }
        supported = {
            "canvas": {".svg"},
            "photoshop": {".svg", ".pdf"},
            "illustrator": {".svg", ".pdf"},
        }
        if path.suffix.lower() not in supported[target]:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "handoff_plan",
                "error": {"code": "unsupported_target_format"},
            }
        size_bytes = path.stat().st_size
        if size_bytes > 50 * 1024 * 1024:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "handoff_plan",
                "error": {"code": "artifact_too_large"},
            }
        media_type = "image/svg+xml" if path.suffix.lower() == ".svg" else "application/pdf"
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "handoff_plan",
            "details": {
                "target": target,
                "artifact": {
                    "basename": path.name,
                    "media_type": media_type,
                    "size_bytes": size_bytes,
                    "sha256": _sha256_bytes(path.read_bytes()),
                },
                "import_intent": "place_as_user_selected_artifact",
                "writes_files": False,
                "downstream_confirmation_required": True,
                "source_path_exposed": False,
            },
        }

    def export(self, arguments: dict[str, Any]) -> dict[str, Any]:
        source = self._safe_path(str(arguments.get("path") or ""), suffixes={".drawio"})
        output_format = str(arguments.get("format") or "svg").lower()
        if not bool(arguments.get("confirm_write")):
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "export",
                "error": {"code": "confirmation_required"},
            }
        document = from_drawio_xml(source.read_text(encoding="utf-8"))
        if output_format == "svg":
            default_target = source.relative_to(self.repo_root).as_posix() + ".svg"
            target = self._safe_path(
                str(arguments.get("output_path") or default_target), suffixes={".svg"}
            )
            _atomic_write(target, render_svg(document))
            return {
                "ok": True,
                "bridge": "diagramforge",
                "action": "export",
                "details": {"format": "svg", "embedded_xml": True, "basename": target.name},
            }
        if output_format != "pdf":
            raise ValueError("format must be svg or pdf")
        executable = _drawio_executable()
        if not executable:
            return {
                "ok": False,
                "bridge": "diagramforge",
                "action": "export",
                "error": {
                    "code": "drawio_desktop_unavailable",
                    "suggested_next_action": "install the Draw.io desktop app or export SVG",
                },
            }
        default_target = source.relative_to(self.repo_root).with_suffix(".pdf").as_posix()
        target = self._safe_path(
            str(arguments.get("output_path") or default_target), suffixes={".pdf"}
        )
        subprocess.run(
            [
                executable,
                "--export",
                "--format",
                "pdf",
                "--embed-diagram",
                "--output",
                str(target),
                str(source),
            ],
            check=True,
            timeout=45,
            capture_output=True,
        )
        return {
            "ok": target.is_file(),
            "bridge": "diagramforge",
            "action": "export",
            "details": {"format": "pdf", "basename": target.name},
        }

    def batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        jobs = list(arguments.get("jobs") or [])
        completed = {str(item) for item in arguments.get("completed_job_ids") or []}
        plan: list[dict[str, Any]] = []
        for index, job in enumerate(jobs):
            recipe_id = str(job.get("recipe_id") or "research-framework-v1")
            parameters = job.get("parameters") if isinstance(job.get("parameters"), dict) else {}
            spec = recipe_spec(recipe_id, parameters)
            job_id = stable_id(
                "diagramforge-batch",
                "job",
                f"{index}:{recipe_id}:{json.dumps(parameters, sort_keys=True)}",
            )
            plan.append(
                {
                    "job_id": job_id,
                    "recipe_id": recipe_id,
                    "status": "completed" if job_id in completed else "queued",
                    "document_sha256": document_sha256(
                        compile_input(input_format="spec", spec=spec)
                    ),
                }
            )
        pending = [item for item in plan if item["status"] == "queued"]
        return {
            "ok": True,
            "bridge": "diagramforge",
            "action": "batch",
            "details": {
                "jobs": plan,
                "pending_count": len(pending),
                "completed_count": len(plan) - len(pending),
                "concurrency_limit": min(4, max(1, int(arguments.get("concurrency_limit") or 1))),
                "idempotent": True,
                "resume_supported": True,
                "writes_files": False,
            },
        }
