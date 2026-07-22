from __future__ import annotations

import math
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ..svg_verify import SvgArtifactError, verify_svg_artifact
from .candidate_matrix import CandidateConfig, build_candidate_matrix
from .preprocess import preprocess_for_scene
from .report import RenderMetrics, Vector60Report, write_report
from .scene_classifier import SceneClassification, classify_scene, validate_scene
from .scorer import (
    CandidateScore,
    QualityGates,
    score_final_svg_candidate,
    select_pareto_candidate,
)

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
PATH_LEXEME = re.compile(rf"\s*,?\s*([MLCZ]|{NUMBER})", re.IGNORECASE)
TRANSLATE = re.compile(rf"translate\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)\Z")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


class Vector60PipelineError(RuntimeError):
    """A path-free Vector60 pipeline failure."""


CandidateGenerator = Callable[[Path, CandidateConfig, Path], None]
SvgOptimizer = Callable[[Path, Path], None]
GeometryProcessor = Callable[[Path, Path], tuple[str, ...]]


@dataclass(frozen=True)
class Vector60PipelineResult:
    svg_path: Path
    render_path: Path | None
    report: Vector60Report
    score: CandidateScore | None
    classification: SceneClassification
    fallback_used: bool


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _positive_dimension(value: str | None, label: str) -> int:
    try:
        number = float(value or "")
    except ValueError as exc:
        raise Vector60PipelineError(f"VTracer {label} is invalid.") from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise Vector60PipelineError(f"VTracer {label} is invalid.")
    return int(number)


def _path_tokens(path_data: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(path_data):
        match = PATH_LEXEME.match(path_data, position)
        if match is None:
            if not path_data[position:].strip():
                break
            raise Vector60PipelineError("VTracer emitted unsupported path data.")
        tokens.append(match.group(1))
        position = match.end()
    return tokens


def _format_number(value: float, precision: int) -> str:
    rounded = round(value, precision)
    if abs(rounded) < 10 ** (-precision):
        rounded = 0.0
    return f"{rounded:.{precision}f}".rstrip("0").rstrip(".") or "0"


def _translate_path_data(
    path_data: str,
    *,
    translate_x: float,
    translate_y: float,
    width: int,
    height: int,
    precision: int,
) -> str:
    tokens = _path_tokens(path_data)
    output: list[str] = []
    index = 0
    coordinate_pairs = {"M": 1, "L": 1, "C": 3}
    while index < len(tokens):
        command = tokens[index].upper()
        index += 1
        if command == "Z":
            output.append("Z")
            continue
        if command not in coordinate_pairs:
            raise Vector60PipelineError("VTracer emitted an unsupported path command.")
        output.append(command)
        for _ in range(coordinate_pairs[command]):
            if index + 1 >= len(tokens):
                raise Vector60PipelineError("VTracer emitted incomplete path data.")
            if tokens[index].upper() in {*coordinate_pairs, "Z"} or tokens[index + 1].upper() in {
                *coordinate_pairs,
                "Z",
            }:
                raise Vector60PipelineError("VTracer emitted invalid path coordinates.")
            x = min(max(float(tokens[index]) + translate_x, 0.0), float(width))
            y = min(max(float(tokens[index + 1]) + translate_y, 0.0), float(height))
            output.extend((_format_number(x, precision), _format_number(y, precision)))
            index += 2
    return " ".join(output)


def normalize_vtracer_svg(raw_svg: Path, output_svg: Path, *, precision: int = 5) -> None:
    """Reduce VTracer output to CreNexus's verified path-only SVG dialect."""

    try:
        root = ET.parse(raw_svg).getroot()
    except (OSError, ET.ParseError) as exc:
        raise Vector60PipelineError("VTracer output is unreadable.") from exc
    if _tag_name(root.tag) != "svg":
        raise Vector60PipelineError("VTracer output root is invalid.")
    width = _positive_dimension(root.get("width"), "width")
    height = _positive_dimension(root.get("height"), "height")
    paths: list[str] = []
    for child in root:
        if _tag_name(child.tag) != "path" or list(child):
            raise Vector60PipelineError("VTracer output contains an unsupported element.")
        if set(child.attrib) - {"d", "fill", "transform"}:
            raise Vector60PipelineError("VTracer output contains an unsupported attribute.")
        fill = (child.get("fill") or "").lower()
        transform = TRANSLATE.fullmatch(child.get("transform") or "")
        if HEX_COLOR.fullmatch(fill) is None or transform is None:
            raise Vector60PipelineError("VTracer output paint or transform is invalid.")
        path_data = _translate_path_data(
            child.get("d") or "",
            translate_x=float(transform.group(1)),
            translate_y=float(transform.group(2)),
            width=width,
            height=height,
            precision=precision,
        )
        paths.append(f'<path d="{path_data}" fill="{fill}" fill-rule="evenodd" stroke="none"/>')
    if not paths:
        raise Vector60PipelineError("VTracer output contains no paths.")
    output_svg.write_text(
        "\n".join(
            [
                f'<svg xmlns="{SVG_NAMESPACE}" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}">',
                *paths,
                "</svg>",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generate_vtracer_candidate(
    prepared_image_path: Path,
    candidate: CandidateConfig,
    output_svg: Path,
) -> None:
    """Generate one normalized VTracer candidate without retaining a source path."""

    try:
        import vtracer
    except ImportError as exc:
        raise Vector60PipelineError("The approved VTracer runtime is unavailable.") from exc
    parameters = {
        "colormode": "color",
        "hierarchical": "stacked",
        "mode": "spline",
        "filter_speckle": 4,
        "color_precision": 6,
        "layer_difference": 16,
        "corner_threshold": 60,
        "length_threshold": 4.0,
        "max_iterations": 10,
        "splice_threshold": 45,
        "path_precision": 3,
        **dict(candidate.parameters),
    }
    raw_svg = output_svg.with_suffix(".raw.svg")
    try:
        vtracer.convert_image_to_svg_py(
            str(prepared_image_path),
            str(raw_svg),
            **parameters,
        )
        normalize_vtracer_svg(
            raw_svg,
            output_svg,
            precision=max(4, int(parameters["path_precision"]) + 2),
        )
    except Vector60PipelineError:
        raise
    except Exception as exc:
        raise Vector60PipelineError("VTracer candidate generation failed.") from exc
    finally:
        raw_svg.unlink(missing_ok=True)


def _geometry_passthrough(source_svg: Path, output_svg: Path) -> tuple[str, ...]:
    """Fail closed until a candidate exposes proposals that pass both geometry modules."""

    shutil.copyfile(source_svg, output_svg)
    return ("primitive_fit.no_safe_proposal", "seam_repair.no_safe_proposal")


def optimize_with_svgo(source_svg: Path, output_svg: Path) -> None:
    """Run pinned SVGO without allowing it to widen CreNexus's SVG dialect."""

    node = shutil.which("node")
    repository_root = Path(__file__).resolve().parents[3]
    svgo_script = repository_root / "node_modules" / "svgo" / "bin" / "svgo.js"
    if node is None or not svgo_script.is_file():
        raise Vector60PipelineError("The approved SVGO runtime is unavailable.")
    config_path = output_svg.with_suffix(".svgo.config.mjs")
    config_path.write_text(
        """export default {
  multipass: true,
  plugins: [
    {name: "preset-default", params: {overrides: {
      convertPathData: false,
      convertShapeToPath: false,
      mergePaths: false,
      removeViewBox: false,
      cleanupIds: false
    }}},
    "removeScripts"
  ]
};
""",
        encoding="utf-8",
        newline="\n",
    )
    try:
        completed = subprocess.run(
            [
                node,
                str(svgo_script),
                "--input",
                str(source_svg),
                "--output",
                str(output_svg),
                "--config",
                str(config_path),
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Vector60PipelineError("SVGO cleanup failed.") from exc
    finally:
        config_path.unlink(missing_ok=True)
    if completed.returncode != 0 or not output_svg.is_file():
        raise Vector60PipelineError("SVGO cleanup failed.")


def _classification(image: Image.Image, scene_preset: str | None) -> SceneClassification:
    detected = classify_scene(image)
    if scene_preset is None:
        return detected
    selected = validate_scene(scene_preset)
    return SceneClassification(
        scene=selected,
        confidence=1.0,
        reasons=("explicit_scene_preset",),
        features=detected.features,
    )


def _report_metrics(score: CandidateScore) -> RenderMetrics:
    return RenderMetrics(
        ssim=score.visual.ssim,
        normalized_mae=score.visual.normalized_mae,
        edge_dice=score.visual.edge_dice,
        anchors=score.complexity.anchors,
        subpaths=score.complexity.subpaths,
        svg_bytes=score.complexity.bytes,
        elapsed_seconds=score.elapsed_seconds,
        reference_width=score.evidence.original_width,
        reference_height=score.evidence.original_height,
        rendered_width=score.evidence.render_width,
        rendered_height=score.evidence.render_height,
    )


def _safe_score(
    *,
    candidate_id: str,
    reference: Image.Image,
    svg_path: Path,
    render_path: Path,
    expected_width: int,
    expected_height: int,
    detail_protection: float,
) -> CandidateScore:
    return score_final_svg_candidate(
        candidate_id=candidate_id,
        reference=reference,
        svg_path=svg_path,
        render_path=render_path,
        expected_svg_width=expected_width,
        expected_svg_height=expected_height,
        detail_protection=detail_protection,
    )


def _fallback_result(
    *,
    baseline_svg: Path,
    staging_dir: Path,
    reference: Image.Image,
    expected_width: int,
    expected_height: int,
    classification: SceneClassification,
    candidate_count: int,
    reason: str,
    warning_codes: tuple[str, ...],
    detail_protection: float,
) -> Vector60PipelineResult:
    try:
        verify_svg_artifact(
            baseline_svg,
            expected_width=expected_width,
            expected_height=expected_height,
        )
    except SvgArtifactError as exc:
        raise Vector60PipelineError("The Artisan fallback baseline is unsafe.") from exc
    render_path = staging_dir / "vector60_baseline_render.png"
    score: CandidateScore | None = None
    try:
        score = _safe_score(
            candidate_id="artisan_baseline",
            reference=reference,
            svg_path=baseline_svg,
            render_path=render_path,
            expected_width=expected_width,
            expected_height=expected_height,
            detail_protection=detail_protection,
        )
    except Exception:
        render_path = None
        warning_codes = (*warning_codes, "baseline_render_unverified")
    report = Vector60Report(
        scene=classification.scene,
        status=(
            "unsupported_photo_fallback"
            if classification.scene == "unsupported_photo"
            else "artisan_baseline_fallback"
        ),
        candidate_count=candidate_count,
        selected_candidate="artisan_baseline",
        metrics=_report_metrics(score) if score is not None else None,
        fallback_reason=reason,
        safety_verified=True,
        final_render_scored=score is not None,
        warning_codes=tuple(dict.fromkeys(warning_codes)),
    )
    write_report(staging_dir, report)
    return Vector60PipelineResult(
        svg_path=baseline_svg,
        render_path=render_path,
        report=report,
        score=score,
        classification=classification,
        fallback_used=True,
    )


def run_vector60_pipeline(
    *,
    reference: Image.Image,
    candidate_source: Image.Image,
    baseline_svg: Path,
    staging_dir: Path,
    scene_preset: str | None = None,
    candidate_limit: int = 12,
    detail_protection: float = 0.75,
    candidate_generator: CandidateGenerator = generate_vtracer_candidate,
    geometry_processor: GeometryProcessor = _geometry_passthrough,
    svg_optimizer: SvgOptimizer = optimize_with_svgo,
    quality_gates: QualityGates = QualityGates(),
) -> Vector60PipelineResult:
    """Run Vector60 and return the verified Artisan baseline on every stage failure."""

    classification = _classification(reference, scene_preset)
    matrix = build_candidate_matrix(classification.scene, limit=candidate_limit)
    warnings: list[str] = []
    expected_width, expected_height = candidate_source.size
    fallback_arguments = {
        "baseline_svg": baseline_svg,
        "staging_dir": staging_dir,
        "reference": reference,
        "expected_width": expected_width,
        "expected_height": expected_height,
        "classification": classification,
        "candidate_count": len(matrix.candidates),
        "detail_protection": detail_protection,
    }
    if classification.scene == "unsupported_photo":
        return _fallback_result(
            **fallback_arguments,
            reason="unsupported_photo",
            warning_codes=("high_quality_not_claimed",),
        )

    try:
        verify_svg_artifact(
            baseline_svg,
            expected_width=expected_width,
            expected_height=expected_height,
        )
        preprocessed = preprocess_for_scene(candidate_source, classification.scene)
        if not preprocessed.enhancement_allowed:
            return _fallback_result(
                **fallback_arguments,
                reason="enhancement_not_allowed",
                warning_codes=("high_quality_not_claimed",),
            )
        prepared_path = staging_dir / ".vector60-source.png"
        preprocessed.image.save(prepared_path, format="PNG")
        scores: list[CandidateScore] = []
        baseline_render = staging_dir / "candidate-artisan_baseline.png"
        scores.append(
            _safe_score(
                candidate_id="artisan_baseline",
                reference=reference,
                svg_path=baseline_svg,
                render_path=baseline_render,
                expected_width=expected_width,
                expected_height=expected_height,
                detail_protection=detail_protection,
            )
        )
        candidate_paths = {"artisan_baseline": baseline_svg}
        for candidate in matrix.candidates[1:]:
            generated = staging_dir / f"candidate-{candidate.candidate_id}.svg"
            geometry_output = staging_dir / f"candidate-{candidate.candidate_id}-geometry.svg"
            render_output = staging_dir / f"candidate-{candidate.candidate_id}.png"
            try:
                candidate_generator(prepared_path, candidate, generated)
                geometry_warnings = geometry_processor(generated, geometry_output)
                warnings.extend(geometry_warnings)
                score = _safe_score(
                    candidate_id=candidate.candidate_id,
                    reference=reference,
                    svg_path=geometry_output,
                    render_path=render_output,
                    expected_width=expected_width,
                    expected_height=expected_height,
                    detail_protection=detail_protection,
                )
            except Exception:
                warnings.append(f"candidate_failed.{candidate.candidate_id}")
                continue
            scores.append(score)
            candidate_paths[candidate.candidate_id] = geometry_output
        selected = select_pareto_candidate(scores, gates=quality_gates)
        if selected is None or selected.candidate_id == "artisan_baseline":
            return _fallback_result(
                **fallback_arguments,
                reason="pareto_retained_baseline",
                warning_codes=tuple(warnings),
            )
        selected_path = candidate_paths[selected.candidate_id]
        cleaned_path = staging_dir / "vector60_clean.svg"
        svg_optimizer(selected_path, cleaned_path)
        cleaned_render = staging_dir / "vector60_render.png"
        cleaned_score = _safe_score(
            candidate_id=selected.candidate_id,
            reference=reference,
            svg_path=cleaned_path,
            render_path=cleaned_render,
            expected_width=expected_width,
            expected_height=expected_height,
            detail_protection=detail_protection,
        )
        if not cleaned_score.passes(quality_gates):
            return _fallback_result(
                **fallback_arguments,
                reason="post_svgo_quality_gate",
                warning_codes=tuple(warnings),
            )
        verify_svg_artifact(
            cleaned_path,
            expected_width=expected_width,
            expected_height=expected_height,
        )
        report = Vector60Report(
            scene=classification.scene,
            status="selected",
            candidate_count=len(matrix.candidates),
            selected_candidate=selected.candidate_id,
            metrics=_report_metrics(cleaned_score),
            safety_verified=True,
            final_render_scored=True,
            warning_codes=tuple(dict.fromkeys(warnings)),
        )
        write_report(staging_dir, report)
        return Vector60PipelineResult(
            svg_path=cleaned_path,
            render_path=cleaned_render,
            report=report,
            score=cleaned_score,
            classification=classification,
            fallback_used=False,
        )
    except Exception:
        return _fallback_result(
            **fallback_arguments,
            reason="pipeline_stage_failed",
            warning_codes=tuple(warnings),
        )


def fallback_to_artisan_baseline(
    *,
    reference: Image.Image,
    candidate_source: Image.Image,
    baseline_svg: Path,
    staging_dir: Path,
    scene_preset: str | None = None,
    detail_protection: float = 0.75,
) -> Vector60PipelineResult:
    """Create a safe report and render when the orchestrator itself fails unexpectedly."""

    classification = _classification(reference, scene_preset)
    candidate_count = len(build_candidate_matrix(classification.scene).candidates)
    return _fallback_result(
        baseline_svg=baseline_svg,
        staging_dir=staging_dir,
        reference=reference,
        expected_width=candidate_source.width,
        expected_height=candidate_source.height,
        classification=classification,
        candidate_count=candidate_count,
        reason="pipeline_stage_failed",
        warning_codes=("high_quality_not_claimed",),
        detail_protection=detail_protection,
    )


__all__ = [
    "Vector60PipelineError",
    "Vector60PipelineResult",
    "fallback_to_artisan_baseline",
    "generate_vtracer_candidate",
    "normalize_vtracer_svg",
    "optimize_with_svgo",
    "run_vector60_pipeline",
]
