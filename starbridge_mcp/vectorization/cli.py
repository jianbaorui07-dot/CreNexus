from __future__ import annotations

import argparse
import json

from .engine import RunConfig, VectorizationError, run_vectorization


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise VectorizationError(
            "invalid_arguments", "Required or supplied vectorization arguments are invalid."
        )


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
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_vectorization(config_from_args(parse_args(argv)))
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
