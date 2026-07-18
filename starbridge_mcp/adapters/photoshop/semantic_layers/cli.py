from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .github_feedback import (
    maybe_submit_batch_feedback,
    maybe_submit_manifest_feedback,
)
from .intent import load_intent_profile
from .manifest import load_manifest, resolve_layer_sources
from .pipeline import (
    DecompositionOptions,
    apply_review_patch,
    batch_decompose,
    decompose_image,
    plan_image,
)
from .public_dataset import acquire_public_dataset
from .public_experiment import run_public_client_mode_experiment
from .regression import run_synthetic_regression
from .training import train_subject_mask_quality_model

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_OUTPUT_ROOT = (REPO_ROOT / "examples" / "output" / "photoshop").resolve()


def _safe_output(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    resolved = path.resolve()
    if not resolved.is_relative_to(ALLOWED_OUTPUT_ROOT):
        raise ValueError("Output must stay inside examples/output/photoshop")
    return resolved


def _public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_payload(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        path = Path(value)
        if not path.is_absolute():
            return value
        resolved = path.resolve()
    except (OSError, ValueError):
        return value
    if resolved.is_relative_to(REPO_ROOT):
        return resolved.relative_to(REPO_ROOT).as_posix()
    return "<LOCAL_PATH>"


def _public_error(exc: Exception) -> str:
    message = str(exc)
    for private_root, replacement in (
        (str(REPO_ROOT), "<REPO_ROOT>"),
        (str(Path.home()), "<USER_HOME>"),
    ):
        message = message.replace(private_root, replacement)
        message = message.replace(private_root.replace("\\", "/"), replacement)
    return message


def _options(args: argparse.Namespace) -> DecompositionOptions:
    return DecompositionOptions(
        preset=args.preset,
        subject_engine="provided_or_photoshop"
        if getattr(args, "subject_mask", None)
        else "offline_iterative",
        max_refinements=args.max_refinements,
        text_mode=args.text_mode,
        resolution=args.resolution,
        review_region_limit=args.review_region_limit,
    )


def _add_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--preset",
        choices=[
            "auto",
            "poster_basic",
            "character_basic",
            "line_art_on_texture",
            "monochrome_line_art",
        ],
        default="auto",
    )
    parser.add_argument("--max-refinements", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--text-mode", choices=["conservative", "off"], default="conservative")
    parser.add_argument("--resolution", type=int, default=72)
    parser.add_argument("--review-region-limit", type=int, default=8)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local-first image to editable Photoshop layer pipeline."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Inspect one image without writing files.")
    plan.add_argument("--input", required=True)
    _add_options(plan)

    run = subparsers.add_parser("run", help="Create layer assets and a manifest.")
    run.add_argument("--input", required=True)
    run.add_argument("--output-dir", required=True)
    run.add_argument("--analysis-json")
    run.add_argument("--intent-json", help="Client-approved starbridge.layer_intent.v1 file.")
    run.add_argument(
        "--require-intent",
        action="store_true",
        help="Fail instead of applying conservative defaults when --intent-json is absent.",
    )
    run.add_argument("--subject-mask", help="Full-canvas RGBA cutout exported by Photoshop.")
    run.add_argument("--confirm-write", action="store_true")
    run.add_argument("--force", action="store_true")
    _add_options(run)

    batch = subparsers.add_parser("batch", help="Decompose a non-recursive image directory.")
    batch.add_argument("--input-dir", required=True)
    batch.add_argument("--output-root", required=True)
    batch.add_argument("--workers", type=int, default=2)
    batch.add_argument("--intent-json", help="One approved intent profile for the batch.")
    batch.add_argument("--require-intent", action="store_true")
    batch.add_argument("--confirm-write", action="store_true")
    batch.add_argument("--force", action="store_true")
    _add_options(batch)

    patch = subparsers.add_parser("patch", help="Apply a small AI/manual review diff.")
    patch.add_argument("--manifest", required=True)
    patch.add_argument("--patch", required=True)
    patch.add_argument("--confirm-write", action="store_true")

    build = subparsers.add_parser("build", help="Build a PSD from an existing manifest.")
    build.add_argument("--manifest", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--confirm-write", action="store_true")
    build.add_argument("--open", action="store_true", dest="open_after_build")
    regression = subparsers.add_parser(
        "regression",
        help="Run public synthetic cross-strategy regression cases.",
    )
    regression.add_argument("--output-root", required=True)
    regression.add_argument("--confirm-write", action="store_true")
    acquire = subparsers.add_parser(
        "acquire-public-dataset",
        help="Download an explicit license-verified Wikimedia Commons dataset.",
    )
    acquire.add_argument("--request", required=True)
    acquire.add_argument("--output-root", required=True)
    acquire.add_argument("--confirm-network", action="store_true")
    acquire.add_argument("--confirm-write", action="store_true")
    experiment = subparsers.add_parser(
        "run-public-experiment",
        help="Run explicit client-mode profiles on a license-verified local public dataset.",
    )
    experiment.add_argument("--dataset-manifest", required=True)
    experiment.add_argument("--output-root", required=True)
    experiment.add_argument("--confirm-write", action="store_true")
    train = subparsers.add_parser(
        "train-subject-quality",
        help="Train a candidate-only subject mask review model from explicit pixel-free JSONL files.",
    )
    train.add_argument("--dataset", action="append", required=True)
    train.add_argument("--output-report", required=True)
    train.add_argument("--confirm-write", action="store_true")
    return parser


def _require_confirmed(value: bool) -> None:
    if not value:
        raise PermissionError("This write operation requires --confirm-write")


def _build_psd(manifest: Path, output: Path, open_after_build: bool) -> dict[str, Any]:
    payload = load_manifest(manifest)
    resolve_layer_sources(manifest, payload)
    script = REPO_ROOT / "examples/photoshop_bridge/scripts/build_editable_psd.ps1"
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ManifestPath",
        str(manifest),
        "-OutputPath",
        str(output),
        "-ConfirmWrite",
    ]
    if open_after_build:
        command.append("-OpenAfterBuild")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError(completed.stderr.strip() or "Photoshop builder returned no JSON")
    result = json.loads(stdout)
    if completed.returncode != 0 or not result.get("ok"):
        detail = result.get("error_detail") or result.get("error") or result.get("message")
        raise RuntimeError(detail or "Photoshop build failed")
    return result


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = plan_image(args.input, _options(args))
        elif args.command == "run":
            _require_confirmed(args.confirm_write)
            if args.require_intent and not args.intent_json:
                raise ValueError("--require-intent requires --intent-json")
            analysis = None
            if args.subject_mask:
                analysis = {}
                if args.analysis_json:
                    analysis = json.loads(Path(args.analysis_json).read_text(encoding="utf-8"))
                analysis["subject_mask_path"] = args.subject_mask
            result = decompose_image(
                args.input,
                _safe_output(args.output_dir),
                options=_options(args),
                analysis_path=None if analysis is not None else args.analysis_json,
                analysis=analysis,
                intent_path=args.intent_json,
                force=args.force,
            )
            result["github_feedback"] = maybe_submit_manifest_feedback(
                result["manifest_path"],
                event_type="run",
                operation_result=result,
            )
        elif args.command == "batch":
            _require_confirmed(args.confirm_write)
            if args.require_intent and not args.intent_json:
                raise ValueError("--require-intent requires --intent-json")
            result = batch_decompose(
                args.input_dir,
                _safe_output(args.output_root),
                options=_options(args),
                intent_path=args.intent_json,
                workers=args.workers,
                force=args.force,
            )
            feedback_intent = load_intent_profile(args.intent_json) if args.intent_json else None
            result["github_feedback"] = maybe_submit_batch_feedback(
                result,
                intent_profile=feedback_intent,
            )
        elif args.command == "patch":
            _require_confirmed(args.confirm_write)
            manifest = _safe_output(args.manifest)
            patch = Path(args.patch).expanduser().resolve()
            result = apply_review_patch(manifest, patch)
            result["github_feedback"] = maybe_submit_manifest_feedback(
                manifest,
                event_type="patch",
                operation_result=result,
            )
        elif args.command == "build":
            _require_confirmed(args.confirm_write)
            manifest = _safe_output(args.manifest)
            output = _safe_output(args.output)
            result = _build_psd(manifest, output, args.open_after_build)
            result["github_feedback"] = maybe_submit_manifest_feedback(
                manifest,
                event_type="build",
                operation_result=result,
            )
        elif args.command == "regression":
            _require_confirmed(args.confirm_write)
            result = run_synthetic_regression(_safe_output(args.output_root))
        elif args.command == "acquire-public-dataset":
            _require_confirmed(args.confirm_write)
            if not args.confirm_network:
                raise PermissionError("Network download requires --confirm-network")
            result = acquire_public_dataset(
                args.request,
                _safe_output(args.output_root),
            )
        elif args.command == "run-public-experiment":
            _require_confirmed(args.confirm_write)
            result = run_public_client_mode_experiment(
                args.dataset_manifest,
                _safe_output(args.output_root),
            )
        elif args.command == "train-subject-quality":
            _require_confirmed(args.confirm_write)
            result = train_subject_mask_quality_model(
                args.dataset,
                _safe_output(args.output_report),
            )
        else:  # pragma: no cover
            raise ValueError(f"Unsupported command: {args.command}")
        print(json.dumps(_public_payload(result), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": _public_error(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
