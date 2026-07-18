from __future__ import annotations

import argparse
import json

from .engine import RunConfig, VectorizationError, run_vectorization


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise VectorizationError(
            "invalid_arguments", "Required or supplied vectorization arguments are invalid."
        )


def anchor_budget_argument(value: str) -> str | int:
    normalized = value.strip().lower()
    if normalized == "auto":
        return "auto"
    try:
        budget = int(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Anchor budget must be auto or an integer.") from exc
    if not 1_000 <= budget <= 120_000:
        raise argparse.ArgumentTypeError("Anchor budget is outside the supported range.")
    return budget


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(
        description=(
            "Convert one explicit PNG/JPEG to verified raster-free SVG. "
            "Smart vector is the default mode."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--mode",
        default="smart",
        help=(
            "smart (default), lightweight, exact, artisan; balanced is accepted as a smart alias"
        ),
    )
    parser.add_argument("--reference-id", default="vector-job")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--max-colors", type=int, default=None)
    parser.add_argument("--max-dimension", type=int, default=None)
    parser.add_argument("--simplify-ratio", type=float, default=None)
    parser.add_argument("--min-region-area", type=int, default=None)
    parser.add_argument("--alpha-threshold", type=int, default=None)
    parser.add_argument("--max-subpaths", type=int, default=None)
    parser.add_argument("--max-points", type=int, default=None)
    parser.add_argument("--max-svg-size-mb", type=float, default=None)
    parser.add_argument(
        "--quality-preset",
        choices=("high-fidelity", "balanced", "minimal"),
        default="high-fidelity",
    )
    parser.add_argument("--target-difference", type=float, default=None)
    parser.add_argument(
        "--anchor-budget",
        type=anchor_budget_argument,
        default="auto",
        help="Use auto or an integer from 1,000 to 120,000.",
    )
    parser.add_argument(
        "--resource-budget",
        choices=("low", "auto", "high"),
        default="auto",
    )
    parser.add_argument("--detail-protection", type=float, default=0.75)
    parser.add_argument(
        "--no-auto-minimize-anchors",
        action="store_true",
        help="Keep final-render quality gates but skip the minimum-anchor search.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print an agent-friendly summary; the full report is still saved to disk.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        input_path=args.input,
        mode=args.mode,
        reference_id=args.reference_id,
        output_dir=args.output_dir,
        colors=args.max_colors,
        max_dimension=args.max_dimension,
        simplify_ratio=args.simplify_ratio,
        min_region_area=args.min_region_area,
        alpha_threshold=args.alpha_threshold,
        max_subpaths=args.max_subpaths,
        max_points=args.max_points,
        max_svg_size_mb=args.max_svg_size_mb,
        quality_preset=args.quality_preset,
        target_difference=args.target_difference,
        anchor_budget=args.anchor_budget,
        resource_budget=args.resource_budget,
        detail_protection=args.detail_protection,
        auto_minimize_anchors=not args.no_auto_minimize_anchors,
        compact=args.compact,
    )


def compact_result(result: dict[str, object]) -> dict[str, object]:
    if not result.get("ok"):
        return result
    mode = result["mode"]
    vector = result["vector"]
    validation = result["validation"]
    structure = result.get("artisan_structure")
    assert isinstance(mode, dict)
    assert isinstance(vector, dict)
    assert isinstance(validation, dict)
    summary_fields = (
        "width",
        "height",
        "path_objects",
        "subpaths",
        "points",
        "svg_bytes",
        "anchor_reduction_ratio",
        "centerline_candidate_used",
        "centerline_anchor_reduction_ratio",
        "centerline_precision",
        "centerline_recall",
        "centerline_dice",
        "continuation_candidate_used",
        "continuation_path_reduction_ratio",
        "continuation_anchor_reduction_ratio",
        "continuation_batch_reduction_ratio",
        "continuation_mean_path_length_gain_ratio",
        "semantic_candidate_used",
        "semantic_intent_counts",
        "semantic_pruned_micro_paths",
        "semantic_anchor_reduction_ratio",
        "semantic_point_reduction_ratio",
        "semantic_batch_reduction_ratio",
    )
    artifacts = result.get("artifacts")
    compact_roles = {
        "editable_svg",
        "final_svg_render_proof",
        "adaptive_optimization_report",
    }
    artifact_refs = (
        [
            {"role": item["role"], "path": item["path"]}
            for item in artifacts
            if isinstance(item, dict) and item.get("role") in compact_roles and "path" in item
        ]
        if isinstance(artifacts, list)
        else []
    )
    optimization = result.get("adaptive_optimization")
    optimization_summary = None
    if isinstance(optimization, dict):
        anchor_change = optimization.get("anchors", {})
        optimization_summary = {
            "status": optimization.get("status"),
            "quality_ref": optimization.get("quality_ref"),
            "patch_ref": optimization.get("patch_ref"),
            "candidate_count": optimization.get("candidate_count"),
            "final_render_metrics": optimization.get("final_render_metrics"),
            "anchor_change": {
                "before": anchor_change.get("before"),
                "after": anchor_change.get("after"),
                "reduction_ratio": anchor_change.get("reduction_ratio"),
            },
            "cache_hit_rate": optimization.get("cache", {}).get("hit_rate"),
            "stop_reason": optimization.get("stop_reason"),
            "error_hotspots": optimization.get("error_hotspots", [])[:5],
            "external_ai_calls": 0,
        }
    return {
        "ok": True,
        "mode": mode["key"],
        "output_dir": result["output_dir"],
        "vector": {key: vector[key] for key in summary_fields if key in vector},
        "validation": {
            "svg_verified": validation["svg_verified"],
            "embedded_raster_count": validation["embedded_raster_count"],
            "external_reference_count": validation["external_reference_count"],
        },
        "edit_ref": (
            structure.get("edit_ref", structure.get("structure_ref"))
            if isinstance(structure, dict)
            else None
        ),
        "edit_selectors": (
            structure.get("intent_selectors", []) if isinstance(structure, dict) else []
        ),
        "optimization": optimization_summary,
        "artifacts": artifact_refs,
        "elapsed_seconds": result["elapsed_seconds"],
    }


def main(argv: list[str] | None = None) -> int:
    compact_output = False
    try:
        args = parse_args(argv)
        result = run_vectorization(config_from_args(args))
        if args.compact:
            result = compact_result(result)
            compact_output = True
    except VectorizationError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    except Exception:
        result = {
            "ok": False,
            "error": {
                "code": "vectorization_failed",
                "message": "Vectorization failed before verified artifacts were published.",
            },
        }
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=None if compact_output else 2,
            separators=(",", ":") if compact_output else None,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
