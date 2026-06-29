from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def isoformat(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_path(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_at": isoformat(stat.st_mtime),
        "sha256": sha256_file(path),
    }


def find_latest_job(jobs_root: Path) -> Path | None:
    if not jobs_root.exists():
        return None
    candidates = [path for path in jobs_root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def copy_if_exists(source: Path, destination: Path) -> bool:
    if not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--jobs-root", required=True)
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    jobs_root = Path(args.jobs_root).resolve()
    repo_root = Path(args.repo_root).resolve()

    snapshot_root = repo_root / "docs" / "cad_exact_trace_sync"
    exports_root = snapshot_root / "exports"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    exports_root.mkdir(parents=True, exist_ok=True)

    latest_job = find_latest_job(jobs_root)

    tracked_workspace_files = [
        workspace_root / "CODEX_CAD_WORKFLOW.md",
        workspace_root / "create_trace_job_from_images.py",
        workspace_root / "run_image_to_cad_job.ps1",
        workspace_root / "autocad_finalize_delivery.py",
        workspace_root / "final_production_export.py",
        workspace_root / "final_polish_export.py",
    ]

    latest_job_files: list[Path] = []
    if latest_job is not None:
        latest_job_files = [
            latest_job / "reference_manifest.json",
            latest_job / "README.md",
            latest_job / "final_production" / "final_production_draft.json",
            latest_job / "final_production" / "final_production_draft.dxf",
            latest_job / "final_production" / "final_production_autocad_polished.dxf",
            latest_job / "comparison" / "trace_fidelity_report.json",
            latest_job / "comparison" / "trace_fidelity_report.md",
            latest_job / "delivery_draft" / "delivery_draft.dxf",
            latest_job / "final_polish" / "final_polish_draft.dxf",
            latest_job / "final_review" / "combined_final_review.dxf",
        ]

    snapshot = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "workspace_root": str(workspace_root),
        "jobs_root": str(jobs_root),
        "repo_root": str(repo_root),
        "latest_job": str(latest_job) if latest_job else None,
        "workspace_files": {path.name: describe_path(path) for path in tracked_workspace_files},
        "latest_job_files": {
            str(path.relative_to(latest_job)): describe_path(path) for path in latest_job_files
        }
        if latest_job
        else {},
    }

    copy_if_exists(
        workspace_root / "CODEX_CAD_WORKFLOW.md", exports_root / "CODEX_CAD_WORKFLOW.local.md"
    )
    copy_if_exists(
        workspace_root / "create_trace_job_from_images.py",
        exports_root / "create_trace_job_from_images.py.txt",
    )
    if latest_job is not None:
        copy_if_exists(
            latest_job / "reference_manifest.json", exports_root / "latest_job_manifest.json"
        )
        copy_if_exists(
            latest_job / "final_production" / "final_production_draft.json",
            exports_root / "final_production_draft.json",
        )
        copy_if_exists(
            latest_job / "comparison" / "trace_fidelity_report.json",
            exports_root / "trace_fidelity_report.json",
        )
        copy_if_exists(
            latest_job / "comparison" / "trace_fidelity_report.md",
            exports_root / "trace_fidelity_report.md",
        )
        copy_if_exists(latest_job / "README.md", exports_root / "latest_job_README.md")

    lines = [
        "# CAD Exact Trace Sync",
        "",
        f"- Generated at: `{snapshot['generated_at']}`",
        f"- Workspace root: `{workspace_root}`",
        f"- Jobs root: `{jobs_root}`",
        f"- Latest job: `{latest_job}`" if latest_job else "- Latest job: `none`",
        "",
        "## Current status",
        "",
    ]

    if latest_job is not None:
        polished = latest_job / "final_production" / "final_production_autocad_polished.dxf"
        draft = latest_job / "final_production" / "final_production_draft.dxf"
        lines.extend(
            [
                f"- Final production draft exists: `{draft.exists()}`",
                f"- AutoCAD polished draft exists: `{polished.exists()}`",
                "",
                "## Exported files",
                "",
                "- `exports/CODEX_CAD_WORKFLOW.local.md`",
                "- `exports/create_trace_job_from_images.py.txt`",
                "- `exports/latest_job_manifest.json`",
                "- `exports/final_production_draft.json`",
                "- `exports/trace_fidelity_report.json`",
                "- `exports/trace_fidelity_report.md`",
                "- `exports/latest_job_README.md`",
            ]
        )
    else:
        lines.append("- No CAD job folder found under the jobs root yet.")

    (snapshot_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (snapshot_root / "latest_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
