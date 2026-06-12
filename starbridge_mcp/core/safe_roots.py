from __future__ import annotations

from pathlib import Path
from typing import Any

from starbridge_mcp.core.security import sanitize


REPO_ROOT = Path(__file__).resolve().parents[2]


def _root(
    root_id: str,
    path: str,
    access: str,
    purpose: str,
    *,
    commit_policy: str,
    bridges: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "root_id": root_id,
        "path": path,
        "access": access,
        "purpose": purpose,
        "commit_policy": commit_policy,
        "bridges": list(bridges),
    }


SAFE_ROOTS: tuple[dict[str, Any], ...] = (
    _root(
        "repo_docs",
        "docs",
        "read_only",
        "Public documentation, setup notes, and comparison records.",
        commit_policy="tracked_public",
        bridges=("all",),
    ),
    _root(
        "repo_examples",
        "examples",
        "read_only",
        "Public safe examples and bridge probes.",
        commit_policy="tracked_public",
        bridges=("all",),
    ),
    _root(
        "output_evidence",
        "examples/output/evidence",
        "write_allowed",
        "Redacted EvidenceManifest and job-status JSON.",
        commit_policy="ignored_local",
        bridges=("all",),
    ),
    _root(
        "output_photoshop",
        "examples/output/photoshop",
        "write_allowed",
        "Sandbox Photoshop demo outputs only.",
        commit_policy="ignored_local",
        bridges=("photoshop",),
    ),
    _root(
        "output_illustrator",
        "examples/output/illustrator",
        "write_allowed",
        "Sandbox Illustrator demo outputs only.",
        commit_policy="ignored_local",
        bridges=("illustrator",),
    ),
    _root(
        "output_cad",
        "examples/cad/output",
        "write_allowed",
        "Sandbox DXF outputs for validated CAD plans.",
        commit_policy="ignored_local",
        bridges=("autocad_dxf", "autocad", "cad_autocad"),
    ),
    _root(
        "local_output",
        "output",
        "write_allowed",
        "Local private working output outside the public release surface.",
        commit_policy="ignored_local",
        bridges=("all",),
    ),
    _root(
        "local_scratch",
        "scratch",
        "write_allowed",
        "Local scratch area for temporary machine-only work.",
        commit_policy="ignored_local",
        bridges=("all",),
    ),
    _root(
        "local_sandbox",
        "sandbox",
        "write_allowed",
        "Local sandbox area for guarded experiments that stay off GitHub.",
        commit_policy="ignored_local",
        bridges=("all",),
    ),
)


def safe_roots_summary(*, bridge: str = "all") -> dict[str, Any]:
    roots = []
    for item in SAFE_ROOTS:
        if bridge != "all" and bridge not in item["bridges"] and "all" not in item["bridges"]:
            continue
        roots.append(dict(item))

    return sanitize(
        {
            "ok": True,
            "framework": "StarBridge",
            "action": "safe_roots",
            "bridge": bridge,
            "root_count": len(roots),
            "roots": roots,
            "write_policy": {
                "default_mode": "dry_run",
                "confirmation": "Real local writes require explicit confirmation such as confirm_write=true or confirm_export=true.",
                "path_rule": "Write paths must stay inside declared sandbox or ignored output roots.",
                "private_assets": "Do not open or export private PSD, AI, DWG, draft, model, or customer asset paths through public tools.",
            },
            "mcp_alignment": {
                "roots_spec": "Expose these directories as MCP roots in clients that support roots.",
                "repo_relative_only": True,
                "preferred_client_roots": [
                    "docs",
                    "examples",
                    "examples/output/evidence",
                    "examples/output/photoshop",
                    "examples/output/illustrator",
                    "examples/cad/output",
                ],
            },
        }
    )
