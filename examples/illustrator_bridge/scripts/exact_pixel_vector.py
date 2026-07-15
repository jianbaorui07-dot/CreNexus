from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from svg_artifact_verifier import SvgArtifactError, verify_svg_artifact

REPO_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_ROOT = REPO_ROOT / "examples" / "output" / "illustrator" / "exact-pixel"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_PIXELS = 4_000_000
MAX_RECTANGLE_SUBPATHS = 2_000_000
REFERENCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUPPORTED_FORMATS = {"JPEG", "PNG"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class ExactVectorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return "<REDACTED_PATH>"


def resolve_output_dir(requested: str, reference_id: str) -> Path:
    root = SANDBOX_ROOT.resolve()
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
    else:
        candidate = root / reference_id
    resolved = candidate.resolve()
    if resolved == root or root not in resolved.parents:
        raise ExactVectorError(
            "output_outside_sandbox",
            "Output must stay below examples/output/illustrator/exact-pixel.",
        )
    return resolved


def load_source(path_value: str, max_pixels: int) -> tuple[Image.Image, dict[str, Any]]:
    path = Path(path_value)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
        raise ExactVectorError(
            "unsupported_input",
            "Input must be one explicit PNG or JPEG file.",
        )
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ExactVectorError("input_too_large", "Input file exceeds the byte limit.")
    try:
        with Image.open(path) as opened:
            if opened.format not in SUPPORTED_FORMATS:
                raise ExactVectorError(
                    "unsupported_input_format",
                    "Input content must be PNG or JPEG.",
                )
            oriented = ImageOps.exif_transpose(opened)
            width, height = oriented.size
            if width <= 0 or height <= 0 or width * height > max_pixels:
                raise ExactVectorError(
                    "input_too_large",
                    "Input pixel count exceeds the exact-vector safety limit.",
                )
            rgba = oriented.convert("RGBA")
    except ExactVectorError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        raise ExactVectorError("input_unreadable", "Input image could not be decoded.") from exc
    return rgba, {
        "width": width,
        "height": height,
        "pixel_count": width * height,
        "source_sha256": file_sha256(path),
    }


def opacity_value(alpha: int) -> str:
    return format(alpha / 255, ".15g")


def build_paths(
    image: Image.Image,
    max_subpaths: int,
) -> tuple[dict[tuple[int, int, int, int], list[str]], int]:
    width, height = image.size
    pixels = image.load()
    paths: dict[tuple[int, int, int, int], list[str]] = defaultdict(list)
    run_count = 0
    for y in range(height):
        x = 0
        while x < width:
            color = pixels[x, y]
            start = x
            x += 1
            while x < width and pixels[x, y] == color:
                x += 1
            run_count += 1
            if run_count > max_subpaths:
                raise ExactVectorError(
                    "vector_too_complex",
                    "Exact reconstruction exceeds the rectangle-subpath safety limit.",
                )
            paths[color].append(f"M {start} {y} L {x} {y} L {x} {y + 1} L {start} {y + 1} Z")
    return paths, run_count


def write_svg(
    path: Path,
    width: int,
    height: int,
    paths: dict[tuple[int, int, int, int], list[str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">\n'
        )
        for red, green, blue, alpha in sorted(paths):
            fill = f"#{red:02x}{green:02x}{blue:02x}"
            opacity = "" if alpha == 255 else f' fill-opacity="{opacity_value(alpha)}"'
            stream.write(
                f'<path fill="{fill}"{opacity} fill-rule="evenodd" stroke="none" '
                f'd="{" ".join(paths[(red, green, blue, alpha)])}"/>\n'
            )
        stream.write("</svg>\n")


def run_exact_vector(args: argparse.Namespace) -> dict[str, Any]:
    if not REFERENCE_ID.fullmatch(args.reference_id):
        raise ExactVectorError(
            "invalid_reference_id",
            "Reference id must use lowercase letters, digits, underscore, or hyphen.",
        )
    output_dir = resolve_output_dir(args.output_dir, args.reference_id)
    image, source = load_source(args.input, args.max_pixels)
    paths, run_count = build_paths(image, args.max_subpaths)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".exact-pixel-staging-", dir=output_dir.parent
    ) as temporary_dir:
        staging = Path(temporary_dir)
        staged_svg = staging / "exact_pixel_vector.svg"
        write_svg(staged_svg, source["width"], source["height"], paths)
        try:
            evidence = verify_svg_artifact(
                staged_svg,
                expected_width=source["width"],
                expected_height=source["height"],
            )
        except SvgArtifactError as exc:
            raise ExactVectorError(exc.code, str(exc)) from exc

        report = {
            "ok": True,
            "task": "exact_pixel_vector",
            "method": "exact_rgba_pixel_rectangles_grouped_by_paint",
            "image_trace_used": False,
            "embedded_raster_count": 0,
            "source": source,
            "vector": {
                "path_objects": evidence["path_count"],
                "rectangle_subpaths": run_count,
                "rgb_color_count": evidence["color_count"],
                "rgba_paint_count": evidence["paint_count"],
                "covered_pixel_count": source["pixel_count"],
            },
            "artifact": {
                **evidence,
                "path": repo_relative(output_dir / "exact_pixel_vector.svg"),
            },
            "illustrator_handoff": {
                "action": "Open exact_pixel_vector.svg in Illustrator and Save As .ai.",
                "image_trace_required": False,
                "desktop_write_requires_explicit_user_request": True,
            },
        }
        staged_report = staging / "exact_pixel_vector.report.json"
        staged_report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        os.replace(staged_svg, output_dir / staged_svg.name)
        os.replace(staged_report, output_dir / staged_report.name)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild one explicit PNG/JPEG as raster-free exact pixel-grid SVG paths."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--reference-id", default="exact-pixel-vector")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--max-pixels", type=int, default=MAX_SOURCE_PIXELS)
    parser.add_argument("--max-subpaths", type=int, default=MAX_RECTANGLE_SUBPATHS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_exact_vector(parse_args(argv))
    except ExactVectorError as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": exc.code, "message": str(exc)}},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "exact_vector_failed",
                        "message": "Exact pixel-vector reconstruction failed safely.",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
