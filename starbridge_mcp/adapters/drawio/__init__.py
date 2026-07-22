"""DiagramForge native Draw.io compiler and guarded MCP surface."""

from pathlib import Path

from .service import DiagramForgeService
from .tools import TOOL_DEFINITIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE = DiagramForgeService(REPO_ROOT)

TOOL_HANDLERS = {
    "drawio.probe": _SERVICE.probe,
    "drawio.capabilities": _SERVICE.capabilities,
    "drawio.plan": _SERVICE.plan,
    "drawio.create": _SERVICE.create,
    "drawio.inspect": _SERVICE.inspect,
    "drawio.patch": _SERVICE.patch,
    "drawio.rollback": _SERVICE.rollback,
    "drawio.validate": _SERVICE.validate,
    "drawio.export": _SERVICE.export,
    "drawio.handoff.plan": _SERVICE.handoff_plan,
    "drawio.batch": _SERVICE.batch,
}

__all__ = ["TOOL_DEFINITIONS", "TOOL_HANDLERS", "DiagramForgeService"]
