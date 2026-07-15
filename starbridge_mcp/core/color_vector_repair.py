from __future__ import annotations

import copy
import math
import re
from typing import Any

from starbridge_mcp.core.color_vectorization import HARD_GATE_NAMES, REFERENCE_ID_PATTERN
from starbridge_mcp.core.security import sanitize

SCHEMA_VERSION = "starbridge.color-vector-repair.v1"
ITERATION_SCHEMA_VERSION = "starbridge.color-vector-iteration.v1"
FINDING_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
VALID_SEVERITIES = {"info", "warn", "critical"}
VALID_VERDICTS = {"pass", "repair_needed", "blocked"}
VALID_MEDIA_TYPES = {"image/png", "image/jpeg"}
VALID_STRATEGIES = {"local_illustrator_trace", "hybrid"}
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


def _execute_context(arguments: dict[str, Any]) -> tuple[str, str]:
    media_type = str(arguments.get("source_media_type") or "image/png")
    if media_type not in VALID_MEDIA_TYPES:
        raise ValueError("source_media_type must be image/png or image/jpeg")
    strategy = str(arguments.get("strategy") or "hybrid")
    if strategy not in VALID_STRATEGIES:
        raise ValueError("strategy must be local_illustrator_trace or hybrid")
    return media_type, strategy


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
    source_media_type: str,
    strategy: str,
) -> dict[str, Any]:
    planned = verdict == "planned"
    pass_through = verdict == "pass_through"
    execute_template = None
    runtime_requirements: list[str] = []
    if planned:
        trace = next_settings["trace"]
        preprocess = next_settings["preprocess"]
        execute_template = {
            "reference_id": reference_id,
            "reference_authorized": True,
            "source_media_type": source_media_type,
            "strategy": strategy,
            "photoshop_preprocess": preprocess["photoshop_preprocess"],
            "normalize_srgb": preprocess["normalize_srgb"],
            "max_dimension": preprocess["max_dimension"],
            "median_radius": preprocess["median_radius"],
            "max_colors": trace["max_colors"],
            "path_fitting": trace["path_fitting"],
            "min_area": trace["min_area"],
            "preprocess_blur": trace["preprocess_blur"],
            "ignore_white": trace["ignore_white"],
            "output_to_swatches": trace["output_to_swatches"],
            "dry_run": True,
            "confirm_write": False,
            "confirm_export": False,
        }
        runtime_requirements = [
            "authorized_source_file",
            "write_confirmation",
            "export_confirmation",
        ]
    remaining_rounds = max(0, max_repair_rounds - repair_round) if planned else 0
    next_repair_round = repair_round + 1 if planned and repair_round < max_repair_rounds else None
    post_execute_compare = None
    if planned:
        post_execute_compare = {
            "tool": "illustrator.color_vectorize_compare",
            "argument_template": {
                "reference_id": reference_id,
                "reference_authorized": True,
                "max_dimension": 512,
                "background_threshold": 24,
                "soft_exit": True,
            },
            "runtime_requirements": [
                "authorized_reference_file",
                "sandbox_preview_file",
                "trace_evidence",
            ],
            "on_pass": "complete",
            "on_repair_needed": (
                "plan_next_repair" if next_repair_round is not None else "stop_for_user"
            ),
            "on_blocked": "stop_for_user",
            "next_repair_round": next_repair_round,
        }
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
            "next_execute_template": execute_template,
            "runtime_requirements": runtime_requirements,
            "iteration_control": {
                "executing_round": repair_round,
                "max_repair_rounds": max_repair_rounds,
                "remaining_rounds_after_execute": remaining_rounds,
                "compare_after_execute": planned,
                "next_repair_round": next_repair_round,
                "stop_after_compare_if_failed": planned and repair_round >= max_repair_rounds,
            },
            "post_execute_compare": post_execute_compare,
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
            source_media_type="image/png",
            strategy="hybrid",
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
    source_media_type, strategy = _execute_context(arguments)
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
            source_media_type=source_media_type,
            strategy=strategy,
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


def advance_color_vector_iteration(arguments: dict[str, Any]) -> dict[str, Any]:
    """Advance one sanitized compare result into completion, repair, or stop."""

    reference_id = str(arguments.get("reference_id") or "")
    if not REFERENCE_ID_PATTERN.fullmatch(reference_id):
        raise ValueError("reference_id must match ^[a-z0-9][a-z0-9_-]{0,63}$")

    def result(
        *,
        reference_authorized: bool,
        state: str,
        executed_round: int,
        max_repair_rounds: int,
        comparison_verdict: str | None,
        next_repair_plan: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        planned = state == "repair_planned"
        next_round = executed_round + 1 if planned else None
        return sanitize(
            {
                "ok": state in {"complete", "repair_planned"},
                "bridge": "illustrator",
                "action": "color_vectorize_advance",
                "schema_version": ITERATION_SCHEMA_VERSION,
                "reference_id": reference_id,
                "reference_authorized": reference_authorized,
                "state": state,
                "executed_round": executed_round,
                "max_repair_rounds": max_repair_rounds,
                "remaining_rounds": max(0, max_repair_rounds - executed_round),
                "comparison_verdict": comparison_verdict,
                "terminal": not planned,
                "next_repair_round": next_round,
                "next_repair_plan": next_repair_plan if planned else None,
                "warnings": warnings or [],
                "safety": {
                    "inputs_sanitized": True,
                    "reads_files": False,
                    "writes_files": False,
                    "starts_adobe": False,
                    "arbitrary_script": False,
                    "quality_gates_relaxed": False,
                    "bounded_iteration": True,
                    "visual_review_required": True,
                },
                "dry_run": True,
                "side_effects": False,
            }
        )

    if arguments.get("reference_authorized") is not True:
        return result(
            reference_authorized=False,
            state="blocked",
            executed_round=1,
            max_repair_rounds=1,
            comparison_verdict=None,
            warnings=["reference_authorized=true is required before iteration advance."],
        )

    executed_round = _integer(
        arguments.get("executed_round"),
        name="executed_round",
        minimum=1,
        maximum=3,
    )
    max_repair_rounds = _integer(
        arguments.get("max_repair_rounds", 3),
        name="max_repair_rounds",
        minimum=1,
        maximum=3,
    )
    if executed_round > max_repair_rounds:
        raise ValueError("executed_round cannot exceed max_repair_rounds")

    source_media_type, strategy = _execute_context(arguments)
    current = _settings(arguments)
    comparison_verdict, gates, findings = _comparison(arguments)
    non_info_codes = {item["code"] for item in findings if item["severity"] != "info"}
    failed_gates = [name for name in HARD_GATE_NAMES if not gates[name]]

    if comparison_verdict == "pass":
        if failed_gates or non_info_codes:
            return result(
                reference_authorized=True,
                state="needs_user",
                executed_round=executed_round,
                max_repair_rounds=max_repair_rounds,
                comparison_verdict=comparison_verdict,
                warnings=["Pass verdict conflicts with hard gates or non-info findings."],
            )
        return result(
            reference_authorized=True,
            state="complete",
            executed_round=executed_round,
            max_repair_rounds=max_repair_rounds,
            comparison_verdict=comparison_verdict,
        )

    if comparison_verdict == "blocked" or failed_gates:
        return result(
            reference_authorized=True,
            state="needs_user",
            executed_round=executed_round,
            max_repair_rounds=max_repair_rounds,
            comparison_verdict=comparison_verdict,
            warnings=["A blocked comparison or failed hard gate requires user review."],
        )

    if executed_round >= max_repair_rounds:
        return result(
            reference_authorized=True,
            state="needs_user",
            executed_round=executed_round,
            max_repair_rounds=max_repair_rounds,
            comparison_verdict=comparison_verdict,
            warnings=["Repair budget is exhausted; do not start another automatic round."],
        )

    repair_arguments = {
        "reference_id": reference_id,
        "reference_authorized": True,
        "source_media_type": source_media_type,
        "strategy": strategy,
        "repair_round": executed_round + 1,
        "max_repair_rounds": max_repair_rounds,
        "comparison": {
            "verdict": comparison_verdict,
            "hard_gates": gates,
            "findings": findings,
        },
        "current_trace": current["trace"],
        "current_preprocess": current["preprocess"],
    }
    repair_plan = build_color_vector_repair_plan(repair_arguments)
    if repair_plan.get("verdict") != "planned":
        return result(
            reference_authorized=True,
            state="needs_user",
            executed_round=executed_round,
            max_repair_rounds=max_repair_rounds,
            comparison_verdict=comparison_verdict,
            warnings=repair_plan.get("warnings")
            or ["No safe deterministic next repair is available."],
        )
    return result(
        reference_authorized=True,
        state="repair_planned",
        executed_round=executed_round,
        max_repair_rounds=max_repair_rounds,
        comparison_verdict=comparison_verdict,
        next_repair_plan=repair_plan,
        warnings=repair_plan.get("warnings") or [],
    )
