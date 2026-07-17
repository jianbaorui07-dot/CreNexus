from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
OUTPUT_ROOT = REPO_ROOT / "examples" / "output"
CANDIDATE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


class CandidateEvaluationError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_rgba(path: Path) -> Image.Image:
    try:
        with Image.open(path) as image:
            return ImageOps.exif_transpose(image).convert("RGBA")
    except (OSError, ValueError) as exc:
        raise CandidateEvaluationError(
            "Reference and rendered proof must be readable images."
        ) from exc


def _composite_white(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    rgba = np.asarray(image, dtype=np.float32)
    alpha = rgba[:, :, 3:4] / 255.0
    rgb = rgba[:, :, :3] * alpha + 255.0 * (1.0 - alpha)
    return rgb, rgba[:, :, 3]


def structural_similarity(first: np.ndarray, second: np.ndarray) -> float:
    if first.shape != second.shape:
        raise CandidateEvaluationError("SSIM inputs must have matching shapes.")
    first = first.astype(np.float32)
    second = second.astype(np.float32)
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    if min(first.shape[:2]) < 11:
        mu_first = np.mean(first, axis=(0, 1), keepdims=True)
        mu_second = np.mean(second, axis=(0, 1), keepdims=True)
        var_first = np.mean((first - mu_first) ** 2, axis=(0, 1), keepdims=True)
        var_second = np.mean((second - mu_second) ** 2, axis=(0, 1), keepdims=True)
        covariance = np.mean((first - mu_first) * (second - mu_second), axis=(0, 1), keepdims=True)
    else:
        mu_first = cv2.GaussianBlur(first, (11, 11), 1.5)
        mu_second = cv2.GaussianBlur(second, (11, 11), 1.5)
        var_first = cv2.GaussianBlur(first * first, (11, 11), 1.5) - mu_first * mu_first
        var_second = cv2.GaussianBlur(second * second, (11, 11), 1.5) - mu_second * mu_second
        covariance = cv2.GaussianBlur(first * second, (11, 11), 1.5) - mu_first * mu_second
    numerator = (2 * mu_first * mu_second + c1) * (2 * covariance + c2)
    denominator = (mu_first * mu_first + mu_second * mu_second + c1) * (var_first + var_second + c2)
    score = float(np.mean(numerator / np.maximum(denominator, 1e-12)))
    return min(max(score, -1.0), 1.0)


def evaluate_candidate(
    *,
    candidate_id: str,
    reference_path: Path,
    rendered_path: Path,
    svg_path: Path,
    max_difference_percent: float = 30.0,
    max_normalized_mae: float = 0.12,
    max_subpaths: int = 12_000,
    max_anchors: int = 120_000,
    require_curves: bool = True,
) -> dict[str, Any]:
    if not CANDIDATE_ID.fullmatch(candidate_id):
        raise CandidateEvaluationError(
            "Candidate id must use lowercase letters, digits, and hyphens."
        )
    for path, label in (
        (reference_path, "Reference"),
        (rendered_path, "Rendered proof"),
        (svg_path, "SVG"),
    ):
        if not path.is_file():
            raise CandidateEvaluationError(f"{label} file is missing.")
    reference = _load_rgba(reference_path)
    rendered = _load_rgba(rendered_path)
    reference_ratio = reference.width / reference.height
    rendered_ratio = rendered.width / rendered.height
    aspect_ratio_difference = abs(reference_ratio - rendered_ratio) / reference_ratio
    if reference.size != rendered.size:
        reference = reference.resize(rendered.size, Image.Resampling.LANCZOS)
    reference_rgb, reference_alpha = _composite_white(reference)
    rendered_rgb, rendered_alpha = _composite_white(rendered)
    ssim = structural_similarity(reference_rgb, rendered_rgb)
    normalized_mae = float(np.mean(np.abs(reference_rgb - rendered_rgb)) / 255.0)
    alpha_mae = float(np.mean(np.abs(reference_alpha - rendered_alpha)) / 255.0)
    difference_percent = max(0.0, (1.0 - ssim) * 100.0)

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact

    evidence = verify_svg_artifact(svg_path)
    gates = {
        "aspect_ratio": aspect_ratio_difference <= 0.005,
        "structural_difference": difference_percent <= max_difference_percent,
        "normalized_mae": normalized_mae <= max_normalized_mae,
        "subpaths": evidence["subpath_count"] <= max_subpaths,
        "anchors": evidence["anchor_point_count"] <= max_anchors,
        "curves": (not require_curves) or evidence["curve_segment_count"] > 0,
        "embedded_rasters": evidence["embedded_raster_count"] == 0,
        "external_references": evidence["external_reference_count"] == 0,
    }
    passed = all(gates.values())
    return {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "status": "pass" if passed else "reject",
        "visual": {
            "ssim": round(ssim, 6),
            "difference_percent": round(difference_percent, 3),
            "normalized_mae": round(normalized_mae, 6),
            "alpha_mae": round(alpha_mae, 6),
            "aspect_ratio_difference": round(aspect_ratio_difference, 6),
        },
        "vector": {
            "bytes": evidence["bytes"],
            "paths": evidence["path_count"],
            "subpaths": evidence["subpath_count"],
            "anchors": evidence["anchor_point_count"],
            "control_points": evidence["control_point_count"],
            "curve_segments": evidence["curve_segment_count"],
            "line_segments": evidence["line_segment_count"],
            "colors": evidence["color_count"],
            "paints": evidence["paint_count"],
            "embedded_rasters": evidence["embedded_raster_count"],
            "external_references": evidence["external_reference_count"],
        },
        "gates": gates,
        "thresholds": {
            "max_difference_percent": max_difference_percent,
            "max_normalized_mae": max_normalized_mae,
            "max_subpaths": max_subpaths,
            "max_anchors": max_anchors,
            "require_curves": require_curves,
        },
        "hashes": {
            "reference_sha256": _sha256(reference_path),
            "rendered_sha256": _sha256(rendered_path),
            "svg_sha256": evidence["sha256"],
        },
    }


def _safe_output(value: str) -> Path:
    raw = Path(value)
    target = raw.resolve() if raw.is_absolute() else (REPO_ROOT / raw).resolve()
    try:
        target.relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise CandidateEvaluationError("Quality report must stay under examples/output.") from exc
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score the actual render of a verified SVG candidate."
    )
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--rendered", required=True)
    parser.add_argument("--svg", required=True)
    parser.add_argument("--output")
    parser.add_argument("--max-difference-percent", type=float, default=30.0)
    parser.add_argument("--max-normalized-mae", type=float, default=0.12)
    parser.add_argument("--max-subpaths", type=int, default=12_000)
    parser.add_argument("--max-anchors", type=int, default=120_000)
    parser.add_argument("--allow-line-only", action="store_true")
    parser.add_argument("--soft-exit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = evaluate_candidate(
            candidate_id=args.candidate_id,
            reference_path=Path(args.reference).expanduser().resolve(),
            rendered_path=Path(args.rendered).expanduser().resolve(),
            svg_path=Path(args.svg).expanduser().resolve(),
            max_difference_percent=args.max_difference_percent,
            max_normalized_mae=args.max_normalized_mae,
            max_subpaths=args.max_subpaths,
            max_anchors=args.max_anchors,
            require_curves=not args.allow_line_only,
        )
        if args.output:
            output = _safe_output(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, ensure_ascii=False))
        if report["status"] == "reject" and not args.soft_exit:
            return 2
        return 0
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, CandidateEvaluationError)
            else "Candidate evaluation failed."
        )
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {"code": "candidate_evaluation_failed", "message": message},
                }
            )
        )
        return 0 if args.soft_exit else 1


if __name__ == "__main__":
    raise SystemExit(main())
