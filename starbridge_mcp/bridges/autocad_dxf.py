from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any

from starbridge_mcp.bridges.cad_schema import DEFAULT_LAYERS, normalize_plan
from starbridge_mcp.core.result_schema import make_result, validate_result
from starbridge_mcp.core.security import sanitize_result


BRIDGE_ID = "autocad_dxf"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "examples" / "cad" / "output"


def _result(
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
        bridge=BRIDGE_ID,
        action=action,
        message=message,
        details=details or {},
        warnings=warnings or [],
        next_steps=next_steps or [],
    )
    sanitized = sanitize_result(result)
    validate_result(sanitized)
    return sanitized


def _ezdxf_available() -> bool:
    return importlib.util.find_spec("ezdxf") is not None


def status() -> dict[str, Any]:
    ezdxf_available = _ezdxf_available()
    warnings = []
    next_steps = []
    if not ezdxf_available:
        warnings.append("ezdxf is not installed; dry-run validation still works, but DXF export is disabled.")
        next_steps.append("Install ezdxf in a local environment if you want to write test DXF files.")
    return _result(
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

def validate_cad_plan(plan: Any) -> dict[str, Any]:
    normalized, errors, warnings = normalize_plan(plan)
    return _result(
        ok=not errors,
        action="validate_cad_plan",
        message="CAD plan is valid." if not errors else "CAD plan has validation errors.",
        details={
            "errors": errors,
            "normalized_plan": normalized if not errors else {},
            "entity_count": len(normalized.get("entities", [])) if isinstance(normalized, dict) else 0,
            "layer_count": len(normalized.get("layers", [])) if isinstance(normalized, dict) else 0,
        },
        warnings=warnings,
        next_steps=[] if not errors else ["Fix the validation errors before exporting DXF."],
    )


def create_dxf_plan(prompt_or_spec: Any) -> dict[str, Any]:
    if isinstance(prompt_or_spec, dict):
        validation = validate_cad_plan(prompt_or_spec)
        if not validation["ok"]:
            return validation
        return _result(
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
            {"type": "rectangle", "layer": "OUTLINE", "x": 0, "y": 0, "width": width, "height": height},
            {"type": "line", "layer": "AUX", "start": [width / 2, 0], "end": [width / 2, height]},
            {"type": "line", "layer": "AUX", "start": [0, height / 2], "end": [width, height / 2]},
            {"type": "text", "layer": "TEXT", "position": [200, height + 260], "height": 180, "value": "安全 DXF 计划示例"},
        ],
        "output": "example_generated.dxf",
    }
    return _result(
        ok=True,
        action="create_dxf_plan",
        message="Created deterministic CAD plan from prompt.",
        details={"prompt_used": bool(prompt), "plan": plan},
        warnings=[],
        next_steps=["Review the plan, then run write_dxf with dry_run=True."],
    )


def summarize_plan(plan: Any) -> dict[str, Any]:
    validation = validate_cad_plan(plan)
    normalized = validation["details"].get("normalized_plan", {})
    entities = normalized.get("entities", []) if validation["ok"] else []
    counts = Counter(entity.get("type", "unknown") for entity in entities)
    return _result(
        ok=validation["ok"],
        action="summarize_plan",
        message="CAD plan summary is ready." if validation["ok"] else "Cannot summarize invalid CAD plan.",
        details={
            "units": normalized.get("units") if validation["ok"] else None,
            "layer_count": len(normalized.get("layers", [])) if validation["ok"] else 0,
            "entity_count": len(entities),
            "entity_types": dict(sorted(counts.items())),
        },
        warnings=validation["warnings"],
        next_steps=validation["next_steps"],
    )


def _output_is_allowed(output_path: Path) -> bool:
    try:
        resolved = output_path.resolve()
        root = OUTPUT_ROOT.resolve()
        return resolved == root or root in resolved.parents
    except OSError:
        return False


def write_dxf(plan: Any, output_path: str | Path, dry_run: bool = True) -> dict[str, Any]:
    validation = validate_cad_plan(plan)
    if not validation["ok"]:
        return _result(
            ok=False,
            action="write_dxf",
            message="DXF was not written because the CAD plan is invalid.",
            details={"dry_run": dry_run, "output": Path(output_path).name},
            warnings=validation["warnings"],
            next_steps=validation["next_steps"],
        )

    output = Path(output_path)
    summary = summarize_plan(validation["details"]["normalized_plan"])
    details = {
        "dry_run": dry_run,
        "output": output.name,
        "output_root": "examples/cad/output",
        "summary": summary["details"],
    }
    if dry_run:
        return _result(
            ok=True,
            action="write_dxf",
            message="Dry run completed; no DXF file was written.",
            details=details,
            warnings=validation["warnings"],
            next_steps=["Run with dry_run=False and an output path under examples/cad/output to write a test DXF."],
        )

    if not _output_is_allowed(output):
        return _result(
            ok=False,
            action="write_dxf",
            message="DXF output path is outside the allowed examples/cad/output directory.",
            details=details,
            warnings=["Refusing to write outside examples/cad/output."],
            next_steps=["Choose an output path under examples/cad/output."],
        )
    if not _ezdxf_available():
        return _result(
            ok=False,
            action="write_dxf",
            message="DXF export requires ezdxf, but ezdxf is not installed.",
            details=details,
            warnings=["ezdxf is optional and currently unavailable."],
            next_steps=["Install ezdxf locally, then rerun the export."],
        )

    import ezdxf  # type: ignore[import-not-found]

    normalized = validation["details"]["normalized_plan"]
    doc = ezdxf.new("R2010")
    doc.units = 4
    for layer in normalized.get("layers", []):
        name = layer["name"]
        if name != "0" and name not in doc.layers:
            doc.layers.add(name=name, color=int(layer.get("color", 7)))

    msp = doc.modelspace()
    for entity in normalized.get("entities", []):
        layer = entity.get("layer", "0")
        if entity["type"] == "line":
            msp.add_line(entity["start"], entity["end"], dxfattribs={"layer": layer})
        elif entity["type"] == "polyline":
            msp.add_lwpolyline(entity["points"], close=bool(entity.get("closed", False)), dxfattribs={"layer": layer})
        elif entity["type"] == "circle":
            msp.add_circle(entity["center"], entity["radius"], dxfattribs={"layer": layer})
        elif entity["type"] == "rectangle":
            x = entity["x"]
            y = entity["y"]
            width = entity["width"]
            height = entity["height"]
            msp.add_lwpolyline(
                [[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
                close=True,
                dxfattribs={"layer": layer},
            )
        elif entity["type"] == "text":
            text = msp.add_text(entity["value"], height=entity["height"], dxfattribs={"layer": layer})
            text.dxf.insert = entity["position"]

    output.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output)
    return _result(
        ok=True,
        action="write_dxf",
        message="DXF test file was written under examples/cad/output.",
        details=details,
        warnings=validation["warnings"],
        next_steps=["Open the generated DXF manually in a CAD viewer if needed."],
    )
