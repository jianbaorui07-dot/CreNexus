from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any

from starbridge_mcp.bridges.cad_schema import DEFAULT_LAYERS, normalize_plan
from starbridge_mcp.core.bridge_base import BaseBridge
from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.security import sanitize_result


class AutocadDxfBridge(BaseBridge):
    """Autocad/DXF bridge implementation using the common BaseBridge."""

    BRIDGE_ID = "autocad_dxf"
    REPO_ROOT = Path(__file__).resolve().parents[2]
    OUTPUT_ROOT = REPO_ROOT / "examples" / "cad" / "output"

    @property
    def bridge_id(self) -> str:
        return self.BRIDGE_ID

    @property
    def repo_root(self) -> Path:
        return self.REPO_ROOT

    def _result(
        self,
        *,
        ok: bool,
        action: str,
        message: str,
        details: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> dict[str, Any]:
        result = make_result(
            ok=ok,
            bridge=self.bridge_id,
            action=action,
            message=message,
            details=details or {},
            warnings=warnings or [],
            next_steps=next_steps or [],
        )
        sanitized = sanitize_result(result)
        validate_result(sanitized)
        return sanitized

    def _ezdxf_available(self) -> bool:
        return importlib.util.find_spec("ezdxf") is not None

    def status(self) -> dict[str, Any]:
        ezdxf_available = self._ezdxf_available()
        warnings = []
        next_steps = []
        if not ezdxf_available:
            warnings.append(
                "ezdxf is not installed; dry-run validation still works, but DXF export is disabled."
            )
            next_steps.append(
                "Install ezdxf in a local environment if you want to write test DXF files."
            )
        return self._result(
            ok=True,
            action="status",
            message="AutoCAD / DXF headless bridge is available for safe plan validation.",
            details={
                "requires_autocad": False,
                "ezdxf_available": ezdxf_available,
                "output_root": "examples/cad/output",
                "default_dry_run": True,
                "supported_entities": ["line", "polyline", "circle", "rectangle", "text"],
            },
            warnings=warnings,
            next_steps=next_steps,
        )

    def validate_cad_plan(self, plan: Any) -> dict[str, Any]:
        normalized, errors, warnings = normalize_plan(plan)
        return self._result(
            ok=not errors,
            action="validate_cad_plan",
            message="CAD plan is valid." if not errors else "CAD plan has validation errors.",
            details={
                "errors": errors,
                "normalized_plan": normalized if not errors else {},
                "entity_count": len(normalized.get("entities", []))
                if isinstance(normalized, dict)
                else 0,
                "layer_count": len(normalized.get("layers", [])) if isinstance(normalized, dict) else 0,
            },
            warnings=warnings,
            next_steps=[] if not errors else ["Fix the validation errors before exporting DXF."],
        )

    def create_dxf_plan(self, prompt_or_spec: Any) -> dict[str, Any]:
        if isinstance(prompt_or_spec, dict):
            validation = self.validate_cad_plan(prompt_or_spec)
            if not validation["ok"]:
                return validation
            return self._result(
                ok=True,
                action="create_dxf_plan",
                message="Created CAD plan from structured spec.",
                details={"plan": validation["details"]["normalized_plan"]},
                warnings=validation["warnings"],
                next_steps=["Run summarize_plan or write_dxf with dry_run=True before exporting."],
            )

        prompt = str(prompt_or_spec or "").strip()
        width = 5000
        height = 3000
        if "large" in prompt.lower() or "大型" in prompt:
            width = 9000
            height = 6000
        if "6000" in prompt or "6米" in prompt:
            width = 6000
        if "4000" in prompt or "4米" in prompt:
            height = 4000

        plan = {
            "units": "mm",
            "layers": DEFAULT_LAYERS,
            "entities": [
                {
                    "type": "rectangle",
                    "layer": "OUTLINE",
                    "x": 0,
                    "y": 0,
                    "width": width,
                    "height": height,
                },
                {"type": "line", "layer": "AUX", "start": [width / 2, 0], "end": [width / 2, height]},
                {"type": "line", "layer": "AUX", "start": [0, height / 2], "end": [width, height / 2]},
                {
                    "type": "text",
                    "layer": "TEXT",
                    "position": [200, height + 260],
                    "height": 180,
                    "value": "安全 DXF 计划示例",
                },
            ],
            "output": "example_generated.dxf",
        }
        return self._result(
            ok=True,
            action="create_dxf_plan",
            message="Created deterministic CAD plan from prompt.",
            details={"prompt_used": bool(prompt), "plan": plan},
            warnings=[],
            next_steps=["Review the plan, then run write_dxf with dry_run=True."],
        )

    def summarize_plan(self, plan: Any) -> dict[str, Any]:
        validation = self.validate_cad_plan(plan)
        normalized = validation["details"].get("normalized_plan", {})
        return self._result(
            ok=validation["ok"],
            action="summarize_plan",
            message="CAD plan summary is ready."
            if validation["ok"]
            else "Cannot summarize invalid CAD plan.",
            details=self._summary_details(normalized) if validation["ok"] else self._empty_summary(),
            warnings=validation["warnings"],
            next_steps=validation["next_steps"],
        )

    def _output_is_allowed(self, output_path: Path) -> bool:
        try:
            resolved = output_path.resolve()
            root = self.OUTPUT_ROOT.resolve()
            rel_path = resolved.relative_to(root)
            rel_str = str(rel_path).replace("\\", "/").lower()
            if rel_str.startswith("examples/output"):
                return False
            return True
        except (ValueError, OSError):
            # outside root or error -> not allowed
            return False

    def _entity_points(self, entity: dict[str, Any]) -> list[list[float]]:
        entity_type = entity.get("type")
        if entity_type == "line":
            return [entity["start"], entity["end"]]
        if entity_type == "polyline":
            return list(entity["points"])
        if entity_type == "circle":
            x, y = entity["center"]
            radius = entity["radius"]
            return [[x - radius, y - radius], [x + radius, y + radius]]
        if entity_type == "rectangle":
            x = entity["x"]
            y = entity["y"]
            width = entity["width"]
            height = entity["height"]
            return [[x, y], [x + width, y + height]]
        if entity_type == "text":
            return [entity["position"]]
        return []

    def _plan_bbox(self, entities: list[dict[str, Any]]) -> dict[str, float] | None:
        points = [point for entity in entities for point in self._entity_points(entity)]
        if not points:
            return None
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}

    def _empty_summary(self) -> dict[str, Any]:
        return {
            "units": None,
            "layer_count": 0,
            "layers": [],
            "entity_count": 0,
            "entity_types": {},
            "bbox": None,
        }

    def _summary_details(self, normalized: dict[str, Any]) -> dict[str, Any]:
        entities = normalized.get("entities", [])
        counts = Counter(entity.get("type", "unknown") for entity in entities)
        return {
            "units": normalized.get("units"),
            "layer_count": len(normalized.get("layers", [])),
            "layers": [layer["name"] for layer in normalized.get("layers", [])],
            "entity_count": len(entities),
            "entity_types": dict(sorted(counts.items())),
            "bbox": self._plan_bbox(entities),
        }

    def _manifest_for(
        self, normalized: dict[str, Any], output: Path, summary: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "bridge": self.bridge_id,
            "action": "write_dxf",
            "output": str(output),
            "plan_summary": summary,
            "normalized_plan": normalized,
        }

    def write_dxf(self, plan: Any, output: str | None = None, output_path: str | None = None, *, dry_run: bool = True, confirm_write: bool = False) -> dict[str, Any]:
        if output is None:
            output = output_path
        validation = self.validate_cad_plan(plan)
        if not validation["ok"]:
            return validation

        if not dry_run and not confirm_write:
            return self._result(
                ok=False,
                action="write_dxf",
                message="Real DXF write requires confirm_write=True.",
                details={"confirm_write": False},
                warnings=["Real writes must be explicitly confirmed."],
                next_steps=["Call with confirm_write=True (and dry_run=False) to proceed."],
            )

        normalized = validation["details"]["normalized_plan"]
        summary = self._summary_details(normalized)

        if output is None:
            output = "example.dxf"
        out_path = (self.OUTPUT_ROOT / output).resolve()

        if not dry_run and not self._output_is_allowed(out_path):
            return self._result(
                ok=False,
                action="write_dxf",
                message="Output path is outside the allowed sandbox (examples/cad/output).",
                details={"output_path": str(out_path)},
                warnings=["Only outputs under examples/cad/output are allowed for real writes."],
                next_steps=["Use a path inside the sandbox or dry_run=True."],
            )

        if dry_run:
            manifest = self._manifest_for(normalized, out_path, summary)
            return self._result(
                ok=True,
                action="write_dxf",
                message="DXF write (dry-run) prepared.",
                details={
                    "dry_run": True,
                    "output_path": str(out_path),
                    "manifest": manifest,
                    "summary": summary,
                    "confirm_write": confirm_write,
                },
                warnings=["dry_run=True."],
                next_steps=["Set dry_run=False with explicit confirmation to write."],
            )

        if not _ezdxf_available():
            return self._result(
                ok=False,
                action="write_dxf",
                message="ezdxf not available; cannot write DXF.",
                details={"ezdxf_available": False, "status": "unavailable"},
                warnings=["Install ezdxf to enable DXF export."],
                next_steps=["pip install ezdxf"],
            )

        # real write would go here
        manifest = self._manifest_for(normalized, out_path, summary)
        return self._result(
            ok=True,
            action="write_dxf",
            message="DXF written (simulated in this version).",
            details={
                "dry_run": False,
                "output_path": str(out_path),
                "manifest": manifest,
                "summary": summary,
                "confirm_write": confirm_write,
            },
        )


# Back-compat module level functions for existing callers
_bridge = AutocadDxfBridge()


def status() -> dict[str, Any]:
    return _bridge.status()


def validate_cad_plan(plan: Any) -> dict[str, Any]:
    return _bridge.validate_cad_plan(plan)


def create_dxf_plan(prompt_or_spec: Any) -> dict[str, Any]:
    return _bridge.create_dxf_plan(prompt_or_spec)


def summarize_plan(plan: Any) -> dict[str, Any]:
    return _bridge.summarize_plan(plan)


def write_dxf(plan: Any, output: str | None = None, output_path: str | None = None, *, dry_run: bool = True, confirm_write: bool = False) -> dict[str, Any]:
    return _bridge.write_dxf(plan, output=output, output_path=output_path, dry_run=dry_run, confirm_write=confirm_write)


# Module level compat for tests and legacy code
OUTPUT_ROOT = AutocadDxfBridge.OUTPUT_ROOT
BRIDGE_ID = AutocadDxfBridge.BRIDGE_ID

_bridge_instance = _bridge

def _ezdxf_available() -> bool:
    return _bridge_instance._ezdxf_available()

def _output_is_allowed(output_path: Path) -> bool:
    return _bridge_instance._output_is_allowed(output_path)

def _entity_points(entity: dict[str, Any]) -> list[list[float]]:
    return _bridge_instance._entity_points(entity)

def _plan_bbox(entities: list[dict[str, Any]]) -> dict[str, float] | None:
    return _bridge_instance._plan_bbox(entities)

def _empty_summary() -> dict[str, Any]:
    return _bridge_instance._empty_summary()

def _summary_details(normalized: dict[str, Any]) -> dict[str, Any]:
    return _bridge_instance._summary_details(normalized)

def _manifest_for(normalized: dict[str, Any], output: Path, summary: dict[str, Any]) -> dict[str, Any]:
    return _bridge_instance._manifest_for(normalized, output, summary)
