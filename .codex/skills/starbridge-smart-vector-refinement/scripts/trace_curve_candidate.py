from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
OUTPUT_ROOT = REPO_ROOT / "examples" / "output" / "vectorization"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TOKEN = re.compile(rf"\s*,?\s*([MLCZ]|{NUMBER})", re.IGNORECASE)
TRANSLATE = re.compile(rf"translate\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)\Z")


class CurveCandidateError(ValueError):
    pass


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _positive_dimension(value: str | None, label: str) -> int:
    try:
        number = float(value or "")
    except ValueError as exc:
        raise CurveCandidateError(f"VTracer {label} must be numeric.") from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise CurveCandidateError(f"VTracer {label} must be a positive integer.")
    return int(number)


def _tokens(path_data: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(path_data):
        match = TOKEN.match(path_data, position)
        if match is None:
            if path_data[position:].strip() == "":
                break
            raise CurveCandidateError("VTracer emitted unsupported SVG path data.")
        tokens.append(match.group(1))
        position = match.end()
    return tokens


def _format_number(value: float, precision: int) -> str:
    rounded = round(value, precision)
    if abs(rounded) < 10 ** (-precision):
        rounded = 0.0
    text = f"{rounded:.{precision}f}".rstrip("0").rstrip(".")
    return text or "0"


def translate_path_data(
    path_data: str,
    *,
    translate_x: float,
    translate_y: float,
    width: int,
    height: int,
    precision: int = 4,
) -> str:
    tokens = _tokens(path_data)
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
            raise CurveCandidateError("Only absolute M, L, C, and Z commands are supported.")
        output.append(command)
        for _ in range(coordinate_pairs[command]):
            if index + 1 >= len(tokens):
                raise CurveCandidateError("VTracer emitted an incomplete coordinate pair.")
            if tokens[index].upper() in coordinate_pairs or tokens[index].upper() == "Z":
                raise CurveCandidateError("VTracer emitted an invalid coordinate pair.")
            if tokens[index + 1].upper() in coordinate_pairs or tokens[index + 1].upper() == "Z":
                raise CurveCandidateError("VTracer emitted an invalid coordinate pair.")
            x = min(max(float(tokens[index]) + translate_x, 0.0), float(width))
            y = min(max(float(tokens[index + 1]) + translate_y, 0.0), float(height))
            output.extend((_format_number(x, precision), _format_number(y, precision)))
            index += 2
    return " ".join(output)


def normalize_vtracer_svg(raw_svg: Path, output_svg: Path, *, precision: int = 4) -> dict[str, int]:
    try:
        root = ET.parse(raw_svg).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CurveCandidateError("VTracer did not produce a readable SVG.") from exc
    if _tag_name(root.tag) != "svg":
        raise CurveCandidateError("VTracer output root is not SVG.")
    width = _positive_dimension(root.get("width"), "width")
    height = _positive_dimension(root.get("height"), "height")
    normalized_paths: list[str] = []
    for child in root:
        if _tag_name(child.tag) != "path" or list(child):
            raise CurveCandidateError("VTracer output contains an unsupported element.")
        if set(child.attrib) - {"d", "fill", "transform"}:
            raise CurveCandidateError("VTracer path contains an unsupported attribute.")
        fill = (child.get("fill") or "").lower()
        if not HEX_COLOR.fullmatch(fill):
            raise CurveCandidateError("VTracer path fill must be an explicit RGB color.")
        transform = TRANSLATE.fullmatch(child.get("transform") or "")
        if transform is None:
            raise CurveCandidateError("VTracer path transform must be translate(x,y).")
        path_data = translate_path_data(
            child.get("d") or "",
            translate_x=float(transform.group(1)),
            translate_y=float(transform.group(2)),
            width=width,
            height=height,
            precision=precision,
        )
        normalized_paths.append(
            f'<path d="{path_data}" fill="{fill}" fill-rule="evenodd" stroke="none"/>'
        )
    if not normalized_paths:
        raise CurveCandidateError("VTracer output contains no paths.")
    output_svg.write_text(
        "\n".join(
            [
                f'<svg xmlns="{SVG_NAMESPACE}" width="{width}" height="{height}" '
                f'viewBox="0 0 {width} {height}">',
                *normalized_paths,
                "</svg>",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {"width": width, "height": height, "path_count": len(normalized_paths)}


def _safe_output_dir(value: str) -> Path:
    raw = Path(value)
    target = raw.resolve() if raw.is_absolute() else (REPO_ROOT / raw).resolve()
    try:
        relative = target.relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise CurveCandidateError("Output must stay under examples/output/vectorization.") from exc
    if not relative.parts:
        raise CurveCandidateError("Output must use a candidate subdirectory.")
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_candidate(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file() or input_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise CurveCandidateError("Input must be one explicit PNG or JPEG file.")
    output_dir = _safe_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_svg = output_dir / ".vtracer-raw.svg"
    final_svg = output_dir / "vector.svg"
    try:
        import vtracer
    except ImportError as exc:
        raise CurveCandidateError(
            'Install the optional dependency with: pip install -e ".[vector-refinement]"'
        ) from exc

    parameters = {
        "colormode": "color",
        "hierarchical": "stacked",
        "mode": "spline",
        "filter_speckle": args.filter_speckle,
        "color_precision": args.color_precision,
        "layer_difference": args.layer_difference,
        "corner_threshold": args.corner_threshold,
        "length_threshold": args.length_threshold,
        "max_iterations": args.max_iterations,
        "splice_threshold": args.splice_threshold,
        "path_precision": args.path_precision,
    }
    try:
        vtracer.convert_image_to_svg_py(str(input_path), str(raw_svg), **parameters)
    except Exception as exc:
        raise CurveCandidateError("VTracer candidate generation failed.") from exc
    dimensions = normalize_vtracer_svg(
        raw_svg,
        final_svg,
        precision=max(4, args.path_precision + 2),
    )
    if not args.keep_raw:
        raw_svg.unlink(missing_ok=True)

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact

    evidence = verify_svg_artifact(
        final_svg,
        expected_width=dimensions["width"],
        expected_height=dimensions["height"],
    )
    report = {
        "schema_version": 1,
        "ok": True,
        "generator": "vtracer-stacked-spline",
        "input_sha256": _sha256(input_path),
        "parameters": parameters,
        "validation": evidence,
        "artifacts": {
            "svg": str(final_svg.relative_to(REPO_ROOT)).replace("\\", "/"),
        },
    }
    (output_dir / "parameters.json").write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "vector_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a normalized raster-free curve SVG candidate."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--filter-speckle", type=int, default=12)
    parser.add_argument("--color-precision", type=int, default=8)
    parser.add_argument("--layer-difference", type=int, default=4)
    parser.add_argument("--corner-threshold", type=int, default=70)
    parser.add_argument("--length-threshold", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--splice-threshold", type=int, default=50)
    parser.add_argument("--path-precision", type=int, default=2)
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--soft-exit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = generate_candidate(args)
    except Exception as exc:
        message = str(exc) if isinstance(exc, CurveCandidateError) else "Curve generation failed."
        print(
            json.dumps(
                {"ok": False, "error": {"code": "curve_candidate_failed", "message": message}}
            )
        )
        return 0 if args.soft_exit else 1
    compact = {
        "ok": True,
        "svg": report["artifacts"]["svg"],
        "subpaths": report["validation"]["subpath_count"],
        "anchors": report["validation"]["anchor_point_count"],
        "curves": report["validation"]["curve_segment_count"],
        "embedded_rasters": 0,
        "external_references": 0,
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
