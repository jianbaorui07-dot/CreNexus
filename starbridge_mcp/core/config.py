from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


BRIDGE_ENV_VARS = {
    "diagramforge": ("DRAWIO_EXE",),
    "comfyui": ("STARBRIDGE_COMFYUI_URL", "COMFY_BASE_URL", "COMFY_ROOT", "COMFY_LAUNCHER"),
    "blender": ("STARBRIDGE_BLENDER_EXE", "BLENDER_EXE", "BLENDER_MCP_DIR"),
    "cad_autocad": ("STARBRIDGE_CAD_MODE", "AUTOCAD_EXE"),
    "photoshop": ("PHOTOSHOP_EXE",),
    "illustrator": ("ILLUSTRATOR_EXE",),
    "capcut_jianying": ("JIANYING_EXE", "JIANYING_DRAFTS_DIR", "CAPCUT_EXE", "CAPCUT_DRAFTS_DIR"),
}


@dataclass(frozen=True)
class CreNexusConfig:
    repo_root: Path = REPO_ROOT
    comfy_url: str = (
        os.environ.get("STARBRIDGE_COMFYUI_URL")
        or os.environ.get("COMFY_BASE_URL")
        or "http://127.0.0.1:8188"
    )
    timeout: int = int(os.environ.get("STARBRIDGE_PROBE_TIMEOUT", "8"))


# Backward-compatible public name for existing integrations.
StarBridgeConfig = CreNexusConfig


def env_summary() -> dict[str, dict[str, bool]]:
    summary: dict[str, dict[str, bool]] = {}
    for bridge, names in BRIDGE_ENV_VARS.items():
        summary[bridge] = {name: bool(os.environ.get(name)) for name in names}
    return summary
