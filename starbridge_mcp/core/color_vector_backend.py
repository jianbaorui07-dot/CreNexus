from __future__ import annotations

from typing import Any

from starbridge_mcp.core.color_vectorization import _reference_id
from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vector-backend-plan.v1"
PREFERENCES = {"auto", "native_illustrator", "headless_svg"}
ARTWORK_KINDS = {"flat_artwork", "illustration", "photo", "mixed"}


def _boolean(arguments: dict[str, Any], name: str, default: bool = False) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _result(
    *,
    reference_id: str,
    authorized: bool,
    state: str,
    backend: str | None,
    reasons: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    next_action = None
    if backend is not None:
        native = backend == "native_illustrator"
        next_action = {
            "kind": "native_trace" if native else "headless_trace_preview",
            "tool": (
                "illustrator.color_vectorize_execute" if native else "standalone_headless_trace"
            ),
            "requires_explicit_file_binding": True,
            "requires_visual_review": True,
        }
    return sanitize(
        {
            "ok": state == "planned",
            "bridge": "illustrator",
            "action": "color_vectorize_backend_plan",
            "schema_version": SCHEMA_VERSION,
            "reference_id": reference_id,
            "reference_authorized": authorized,
            "state": state,
            "selected_backend": backend,
            "reason_codes": reasons,
            "next_action": next_action,
            "warnings": warnings,
            "safety": {
                "inputs_sanitized": True,
                "reads_files": False,
                "writes_files": False,
                "starts_adobe": False,
                "arbitrary_script": False,
                "silent_quality_degradation": False,
            },
            "dry_run": True,
            "side_effects": False,
        }
    )


def build_color_vector_backend_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    """Select a vectorization backend from sanitized caller-provided traits."""

    reference_id = _reference_id(arguments)
    if arguments.get("reference_authorized") is not True:
        return _result(
            reference_id=reference_id,
            authorized=False,
            state="blocked",
            backend=None,
            reasons=["reference_authorization_required"],
            warnings=["reference_authorized=true is required before backend planning."],
        )

    preference = str(arguments.get("backend_preference") or "auto")
    if preference not in PREFERENCES:
        raise ValueError("unsupported backend_preference")
    artwork_kind = str(arguments.get("artwork_kind") or "mixed")
    if artwork_kind not in ARTWORK_KINDS:
        raise ValueError("unsupported artwork_kind")

    native_available = _boolean(arguments, "illustrator_available")
    headless_available = _boolean(arguments, "headless_dependencies_available")
    fidelity_reasons = [
        code
        for field, code in (
            ("requires_gradient_fidelity", "gradient_fidelity_requires_native"),
            ("requires_transparency", "transparency_requires_native"),
            ("requires_text_editability", "editable_text_requires_native"),
        )
        if _boolean(arguments, field)
    ]
    native_required = artwork_kind in {"photo", "mixed"} or bool(fidelity_reasons)
    headless_eligible = artwork_kind in {"flat_artwork", "illustration"} and not native_required

    if preference == "headless_svg" and not headless_eligible:
        return _result(
            reference_id=reference_id,
            authorized=True,
            state="needs_user",
            backend=None,
            reasons=["headless_outside_supported_scope", *fidelity_reasons],
            warnings=[
                "Headless fallback cannot preserve the requested artwork features; use native Illustrator or revise the requirement."
            ],
        )

    wants_native = preference == "native_illustrator" or native_required
    if wants_native:
        if native_available:
            return _result(
                reference_id=reference_id,
                authorized=True,
                state="planned",
                backend="native_illustrator",
                reasons=[
                    "native_backend_required" if native_required else "native_backend_requested",
                    *fidelity_reasons,
                ],
                warnings=[
                    "Real execution remains dry-run by default and requires explicit file binding plus write/export confirmation."
                ],
            )
        return _result(
            reference_id=reference_id,
            authorized=True,
            state="needs_user",
            backend=None,
            reasons=[
                "native_backend_required" if native_required else "native_backend_unavailable",
                *fidelity_reasons,
            ],
            warnings=[
                "Native Illustrator is unavailable and this plan will not silently reduce fidelity."
            ],
        )

    if preference == "auto" and native_available:
        return _result(
            reference_id=reference_id,
            authorized=True,
            state="planned",
            backend="native_illustrator",
            reasons=["native_backend_preferred"],
            warnings=["Use the native compare and bounded repair loop after execution."],
        )
    if headless_eligible and headless_available:
        selection_reason = (
            "headless_backend_requested"
            if preference == "headless_svg"
            else "native_backend_unavailable"
        )
        return _result(
            reference_id=reference_id,
            authorized=True,
            state="planned",
            backend="headless_svg",
            reasons=["headless_scope_eligible", selection_reason],
            warnings=[
                "Headless output proves editable SVG structure, not visual equivalence; visual review remains required."
            ],
        )
    return _result(
        reference_id=reference_id,
        authorized=True,
        state="needs_user",
        backend=None,
        reasons=["no_eligible_backend_available"],
        warnings=["No eligible local backend is currently available."],
    )
