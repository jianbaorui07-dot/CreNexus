from __future__ import annotations

from typing import Any


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _annotations(*, read_only: bool, requires_confirmation: bool) -> dict[str, Any]:
    return {
        "readOnlyHint": read_only,
        "destructiveHint": not read_only,
        "openWorldHint": False,
        "riskLevel": "safe_read_only" if read_only else "guarded_local_write",
        "safeDefault": read_only,
        "requiresConfirmation": requires_confirmation,
        "requiresLocalSoftware": False,
        "currentStatus": "stable" if read_only else "experimental",
    }


def _tool(
    name: str,
    title: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": {"type": "object", "additionalProperties": True},
        "annotations": _annotations(read_only=read_only, requires_confirmation=not read_only),
    }


INPUT_PROPERTIES = {
    "input_format": {
        "type": "string",
        "enum": ["spec", "natural_language", "outline", "mermaid", "csv", "drawio_xml"],
        "default": "spec",
    },
    "content": {"type": "string", "maxLength": 100000},
    "spec": {"type": "object"},
    "recipe_id": {
        "type": "string",
        "enum": ["research-framework-v1", "system-architecture-v1"],
    },
    "parameters": {"type": "object"},
}


TOOL_DEFINITIONS = [
    _tool(
        "drawio.probe",
        "DiagramForge Probe",
        "Probe the deterministic headless compiler and optional Draw.io desktop exporter.",
        _schema({}),
        read_only=True,
    ),
    _tool(
        "drawio.capabilities",
        "DiagramForge Capabilities",
        "List supported inputs, elements, recipes, layouts, patches, and exports.",
        _schema({}),
        read_only=True,
    ),
    _tool(
        "drawio.plan",
        "DiagramForge Plan",
        "Compile and validate a native Draw.io document in memory without writing files.",
        _schema(INPUT_PROPERTIES),
        read_only=True,
    ),
    _tool(
        "drawio.create",
        "DiagramForge Create",
        "Create validated .drawio, editable SVG preview, and manifest files in an ignored safe root.",
        _schema(
            {
                **INPUT_PROPERTIES,
                "output_base": {
                    "type": "string",
                    "default": "examples/output/diagramforge/diagramforge",
                },
                "confirm_write": {"type": "boolean", "default": False},
            }
        ),
        read_only=False,
    ),
    _tool(
        "drawio.inspect",
        "DiagramForge Inspect",
        "Inspect one explicit .drawio file inside a safe output root and return stable element hashes.",
        _schema({"path": {"type": "string"}}, required=["path"]),
        read_only=True,
    ),
    _tool(
        "drawio.patch",
        "DiagramForge Patch",
        "Apply transactional stable-ID label, move, or style patches without rebuilding unrelated regions.",
        _schema(
            {
                "path": {"type": "string"},
                "patches": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["set_label", "move", "set_style"]},
                            "element_id": {"type": "string"},
                            "label": {"type": "string"},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "style": {"type": "string"},
                        },
                        "required": ["op", "element_id"],
                        "additionalProperties": False,
                    },
                },
                "confirm_write": {"type": "boolean", "default": False},
            },
            required=["path", "patches"],
        ),
        read_only=False,
    ),
    _tool(
        "drawio.rollback",
        "DiagramForge Rollback",
        "Restore the one-level validated checkpoint for an explicit safe-root Draw.io document.",
        _schema(
            {
                "path": {"type": "string"},
                "confirm_write": {"type": "boolean", "default": False},
            },
            required=["path"],
        ),
        read_only=False,
    ),
    _tool(
        "drawio.validate",
        "DiagramForge Validate",
        "Validate XML, references, geometry, overlap, text fit, and contrast for one safe .drawio file.",
        _schema({"path": {"type": "string"}}, required=["path"]),
        read_only=True,
    ),
    _tool(
        "drawio.export",
        "DiagramForge Export",
        "Export editable SVG internally or PDF through an installed Draw.io desktop CLI.",
        _schema(
            {
                "path": {"type": "string"},
                "format": {"type": "string", "enum": ["svg", "pdf"], "default": "svg"},
                "output_path": {"type": "string"},
                "confirm_write": {"type": "boolean", "default": False},
            },
            required=["path"],
        ),
        read_only=False,
    ),
    _tool(
        "drawio.handoff.plan",
        "DiagramForge Handoff Plan",
        "Build a path-redacted, hash-bound import plan for Canvas, Photoshop, or Illustrator.",
        _schema(
            {
                "path": {"type": "string"},
                "target": {
                    "type": "string",
                    "enum": ["canvas", "photoshop", "illustrator"],
                },
            },
            required=["path", "target"],
        ),
        read_only=True,
    ),
    _tool(
        "drawio.batch",
        "DiagramForge Batch Plan",
        "Build an idempotent resumable batch plan with deterministic job and document hashes.",
        _schema(
            {
                "jobs": {"type": "array", "maxItems": 100, "items": {"type": "object"}},
                "completed_job_ids": {"type": "array", "items": {"type": "string"}},
                "concurrency_limit": {"type": "integer", "minimum": 1, "maximum": 4},
            },
            required=["jobs"],
        ),
        read_only=True,
    ),
]
