from __future__ import annotations

import copy
import math
import re
from typing import Any

from starbridge_mcp.core.color_vectorization import HARD_GATE_NAMES, REFERENCE_ID_PATTERN
from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vector-repair.v1"
FINDING_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
VALID_SEVERITIES = {"info", "warn", "critical"}
VALID_VERDICTS = {"pass", "repair_needed", "blocked"}
COLOR_FINDINGS = {"mean_delta_e_high", "p95_delta_e_high"}
FIDELITY_FINDINGS = {"silhouette_iou_low", "perceptual_similarity_low"}
COMPLEXITY_FINDINGS = {"anchor_count_high"}

DEFAULT_SETTINGS: dict[str, Any] = {
    "trace": {
        "max_colors": 64,
        "path_fitting": 1.5,
        "min_area": 2,
        "preprocess_blur": 0.0,
        "ignore_white": False,
        "output_to_swatches": True,
    },
    "preprocess": {
        "photoshop_preprocess": False,
        "normalize_srgb": True,
        "max_dimension": 4096,
        "median_radius": 0,
    },
}


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _number(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def _boolean(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _settings(arguments: dict[str, Any]) -> dict[str, Any]:
    trace = arguments.get("current_trace")
    preprocess = arguments.get("current_preprocess")
    if not isinstance(trace, dict) or not isinstance(preprocess, dict):
        raise ValueError("current_trace and current_preprocess must be objects")
    return {
        "trace": {
            "max_colors": _integer(
                trace.get("max_colors"), name="max_colors", minimum=2, maximum=256
            ),
            "path_fitting": _number(
                trace.get("path_fitting"),
                name="path_fitting",
                minimum=0,
                maximum=10,
            ),
            "min_area": _integer(trace.get("min_area"), name="min_area", minimum=1, maximum=1000),
            "preprocess_blur": _number(
                trace.get("preprocess_blur"),
                name="preprocess_blur",
                minimum=0,
                maximum=2,
            ),
            "ignore_white": _boolean(trace.get("ignore_white"), name="ignore_white"),
            "output_to_swatches": _boolean(
                trace.get("output_to_swatches"), name="output_to_swatches"
            ),
        },
        "preprocess": {
            "photoshop_preprocess": _boolean(
                preprocess.get("photoshop_preprocess"),
                name="photoshop_preprocess",
            ),
            "normalize_srgb": _boolean(preprocess.get("normalize_srgb"), name="normalize_srgb"),
            "max_dimension": _integer(
                preprocess.get("max_dimension"),
                name="max_dimension",
                minimum=256,
                maximum=8192,
            ),
            "median_radius": _integer(
                preprocess.get("median_radius"),
                name="median_radius",
                minimum=0,
                maximum=5,
            ),
        },
    }


def _comparison(arguments: dict[str, Any]) -> tuple[str, dict[str, bool], list[dict[str, str]]]:
    comparison = arguments.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError("comparison must be an object")
    verdict = comparison.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise ValueError("comparison.verdict must be pass, repair_needed, or blocked")

    hard_gates = comparison.get("hard_gates")
    if not isinstance(hard_gates, dict) or set(hard_gates) != set(HARD_GATE_NAMES):
        raise ValueError("comparison.hard_gates must contain every required hard gate")
    validated_gates = {
        name: _boolean(hard_gates[name], name=f"hard_gates.{name}") for name in HARD_GATE_NAMES
    }

    raw_findings = comparison.get("findings")
    if not isinstance(raw_findings, list) or len(raw_findings) > 128:
        raise ValueError("comparison.findings must be an array with at most 128 items")
    findings: list[dict[str, str]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            raise ValueError("each comparison finding must be an object")
        code = item.get("code")
        severity = item.get("severity")
        message = item.get("message", "")
        if not isinstance(code, str) or not FINDING_CODE_PATTERN.fullmatch(code):
            raise ValueError("finding code must be a safe identifier")
        if severity not in VALID_SEVERITIES:
            raise ValueError("finding severity must be info, warn, or critical")
        if not isinstance(message, str) or len(message) > 512:
            raise ValueError("finding message must be at most 512 characters")
        findings.append({"code": code, "severity": str(severity)})
    return str(verdict), validated_gates, findings


def _result(
    *,
    reference_id: str,
    reference_authorized: bool,
    verdict: str,
    repair_round: int,
    max_repair_rounds: int,
    current_settings: dict[str, Any],
    next_settings: dict[str, Any],
    changes: list[dict[str, Any]],
    addressed_findings: list[str],
    unresolved_findings: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    planned = verdict == "planned"
    pass_through = verdict == "pass_through"
    return sanitize(
        {
            "ok": planned or pass_through,
            "bridge": "illustrator",
            "action": "color_vectorize_repair_plan",
            "schema_version": SCHEMA_VERSION,
            "reference_id": reference_id,
            "reference_authorized": reference_authorized,
            "verdict": verdict,
            "repair_round": repair_round,
            "max_repair_rounds": max_repair_rounds,
            "current_settings": current_settings,
            "next_settings": next_settings,
            "changes": changes,
            "addressed_findings": sorted(set(addressed_findings)),
            "unresolved_findings": sorted(set(unresolved_findings)),
            "requires_execute": planned,
            "requires_user_review": verdict in {"needs_user", "blocked"}
            or bool(unresolved_findings),
            "suggested_next_tool": ("illustrator.color_vectorize_execute" if planned else None),
            "warnings": warnings,
            "safety": {
                "inputs_sanitized": True,
                "reads_files": False,
                "writes_files": False,
                "starts_adobe": False,
                "arbitrary_script": False,
                "quality_gates_relaxed": False,
                "bounded_repair": True,
                "visual_review_required": True,
            },
            "dry_run": True,
            "side_effects": False,
        }
    )


def build_color_vector_repair_plan(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compile sanitized comparison findings into bounded trace parameter changes."""

    reference_id = str(arguments.get("reference_id") or "")
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValueError("reference_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")

    if arguments.get("reference_authorized") is not True:
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        return _result(
            reference_id=reference_id,
            reference_authorized=False,
            verdict="blocked",
            repair_round=1,
            max_repair_rounds=1,
            current_settings=settings,
            next_settings=copy.deepcopy(settings),
            changes=[],
            addressed_findings=[],
            unresolved_findings=["authorization_required"],
            warnings=["reference_authorized=true is required before repair planning."],
        )

    repair_round = _integer(
        arguments.get("repair_round", 1),
        name="repair_round",
        minimum=1,
        maximum=3,
    )
    max_repair_rounds = _integer(
        arguments.get("max_repair_rounds", 2),
        name="max_repair_rounds",
        minimum=1,
        maximum=3,
    )
    current = _settings(arguments)
    next_settings = copy.deepcopy(current)
    comparison_verdict, gates, findings = _comparison(arguments)
    non_info_codes = {item["code"] for item in findings if item["severity"] != "info"}
    failed_gates = [name for name in HARD_GATE_NAMES if not gates[name]]

    def finish(
        verdict: str,
        *,
        changes: list[dict[str, Any]] | None = None,
        addressed: list[str] | None = None,
        unresolved: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return _result(
            reference_id=reference_id,
            reference_authorized=True,
            verdict=verdict,
            repair_round=repair_round,
            max_repair_rounds=max_repair_rounds,
            current_settings=current,
            next_settings=next_settings,
            changes=changes or [],
            addressed_findings=addressed or [],
            unresolved_findings=unresolved or [],
            warnings=warnings or [],
        )

    if failed_gates or comparison_verdict == "blocked":
        unresolved = set(non_info_codes)
        unresolved.update(f"hard_gate_{name}" for name in failed_gates)
        if not unresolved:
            unresolved.add("comparison_blocked")
        return finish(
            "needs_user",
            unresolved=sorted(unresolved),
            warnings=["A hard gate or blocked comparison requires user review."],
        )

    if comparison_verdict == "pass":
        if non_info_codes:
            return finish(
                "needs_user",
                unresolved=sorted(non_info_codes),
                warnings=["Pass verdict conflicts with non-informational findings."],
            )
        return finish("pass_through")

    if repair_round > max_repair_rounds:
        return finish(
            "needs_user",
            unresolved=sorted(non_info_codes or {"repair_budget_exhausted"}),
            warnings=["Repair budget is exhausted; do not start another automatic round."],
        )

    changes: list[dict[str, Any]] = []

    def change(section: str, parameter: str, value: int | float | bool, reason: str) -> bool:
        previous = next_settings[section][parameter]
        if previous == value:
            return False
        next_settings[section][parameter] = value
        changes.append(
            {
                "parameter": parameter,
                "previous": previous,
                "next": value,
                "reason_code": reason,
            }
        )
        return True

    addressed: set[str] = set()
    unresolved = set(non_info_codes)
    color_codes = non_info_codes & COLOR_FINDINGS
    fidelity_codes = non_info_codes & FIDELITY_FINDINGS
    complexity_codes = non_info_codes & COMPLEXITY_FINDINGS

    if color_codes:
        before = len(changes)
        current_colors = next_settings["trace"]["max_colors"]
        color_target = min(256, max(current_colors + 16, math.ceil(current_colors * 1.5)))
        change("trace", "max_colors", color_target, "preserve_color_fidelity")
        change(
            "preprocess",
            "photoshop_preprocess",
            True,
            "normalize_color_pipeline",
        )
        change("preprocess", "normalize_srgb", True, "normalize_color_pipeline")
        change("trace", "preprocess_blur", 0.0, "preserve_color_fidelity")
        change("preprocess", "median_radius", 0, "preserve_color_fidelity")
        if len(changes) > before:
            addressed.update(color_codes)

    if fidelity_codes:
        before = len(changes)
        path_fitting = next_settings["trace"]["path_fitting"]
        change(
            "trace",
            "path_fitting",
            round(max(0.0, path_fitting - 0.5), 2),
            "improve_shape_fidelity",
        )
        min_area = next_settings["trace"]["min_area"]
        change(
            "trace",
            "min_area",
            max(1, min_area - 1),
            "improve_shape_fidelity",
        )
        change("trace", "preprocess_blur", 0.0, "preserve_edge_detail")
        change("preprocess", "median_radius", 0, "preserve_edge_detail")
        if len(changes) > before:
            addressed.update(fidelity_codes)

    if complexity_codes and not fidelity_codes:
        before = len(changes)
        path_fitting = next_settings["trace"]["path_fitting"]
        change(
            "trace",
            "path_fitting",
            round(min(10.0, path_fitting + 0.5), 2),
            "reduce_anchor_complexity",
        )
        min_area = next_settings["trace"]["min_area"]
        change(
            "trace",
            "min_area",
            min(1000, min_area + 1),
            "reduce_anchor_complexity",
        )
        if not color_codes:
            blur = next_settings["trace"]["preprocess_blur"]
            change(
                "trace",
                "preprocess_blur",
                round(min(2.0, blur + 0.1), 2),
                "reduce_anchor_complexity",
            )
        if len(changes) > before:
            addressed.update(complexity_codes)

    unresolved.difference_update(addressed)
    if not changes:
        return finish(
            "needs_user",
            unresolved=sorted(unresolved or {"repair_parameters_exhausted"}),
            warnings=["No safe deterministic parameter change can address the findings."],
        )

    warnings = []
    if unresolved:
        warnings.append("Some findings conflict with the selected repair or require user review.")
    return finish(
        "planned",
        changes=changes,
        addressed=sorted(addressed),
        unresolved=sorted(unresolved),
        warnings=warnings,
    )
