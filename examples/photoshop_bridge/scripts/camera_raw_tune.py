from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SAFE_OUTPUT_DIR = "examples/output/photoshop"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp.mcp_server import handle_request
from starbridge_mcp.adapters.photoshop.camera_raw_protocol import camera_raw_xmp_document


def _slider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--tint", type=float)
    parser.add_argument("--exposure", type=float)
    parser.add_argument("--contrast", type=float)
    parser.add_argument("--highlights", type=float)
    parser.add_argument("--shadows", type=float)
    parser.add_argument("--whites", type=float)
    parser.add_argument("--blacks", type=float)
    parser.add_argument("--texture", type=float)
    parser.add_argument("--clarity", type=float)
    parser.add_argument("--dehaze", type=float)
    parser.add_argument("--vibrance", type=float)
    parser.add_argument("--saturation", type=float)


def build_arguments(args: argparse.Namespace) -> dict[str, Any]:
    params = {
        key: value
        for key, value in {
            "temperature": args.temperature,
            "tint": args.tint,
            "exposure": args.exposure,
            "contrast": args.contrast,
            "highlights": args.highlights,
            "shadows": args.shadows,
            "whites": args.whites,
            "blacks": args.blacks,
            "texture": args.texture,
            "clarity": args.clarity,
            "dehaze": args.dehaze,
            "vibrance": args.vibrance,
            "saturation": args.saturation,
        }.items()
        if value is not None
    }
    source: dict[str, Any] = {"mode": args.source_mode}
    if args.source_path:
        source = {"mode": "explicit_path", "path": args.source_path}
    return {
        "protocol_version": "camera_raw_tune.v1",
        "method": "ps.camera_raw.tune",
        "dry_run": args.dry_run,
        "confirm_apply": args.confirm_apply,
        "confirm_export": args.confirm_export,
        "preset": args.preset,
        "descriptor_fixture_path": args.descriptor_fixture_path,
        "source": source,
        "output": {
            "dir": args.output_dir,
            "basename": args.basename,
            "formats": args.formats,
            "export_after_apply": args.export_after_apply,
        },
        "params": params,
    }


def call_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ps.camera_raw.tune", "arguments": arguments},
        }
    )
    if response is None:
        raise RuntimeError("MCP handler returned no response")
    if "error" in response:
        raise RuntimeError(str(response["error"]))
    return dict(response["result"]["structuredContent"])


def write_plan(payload: dict[str, Any], basename: str) -> Path:
    output_dir = (REPO_ROOT / SAFE_OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / f"{basename}.camera_raw_plan.json"
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan_path


def write_xmp(payload: dict[str, Any], basename: str) -> Path:
    output_dir = (REPO_ROOT / SAFE_OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = dict(payload.get("details", {}).get("plan") or {})
    settings = dict(plan.get("xmp_settings") or {})
    if not settings:
        raise RuntimeError("No xmp_settings were returned by the Camera Raw plan.")
    xmp_path = output_dir / f"{basename}.xmp"
    xmp_path.write_text(camera_raw_xmp_document(settings), encoding="utf-8")
    return xmp_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a StarBridge Photoshop Camera Raw tuning protocol plan.")
    parser.add_argument("--source-path", help="User-explicit local RAW/image path. The script records it in the plan but does not scan directories.")
    parser.add_argument("--source-mode", choices=["active_document", "explicit_path"], default="active_document")
    parser.add_argument("--preset", default="blue_artwork_clean", choices=["blue_artwork_clean"])
    parser.add_argument("--descriptor-fixture-path", help="Optional local verified Camera Raw BatchPlay descriptor fixture JSON.")
    parser.add_argument("--output-dir", default=SAFE_OUTPUT_DIR)
    parser.add_argument("--basename", default="camera_raw_tune_preview")
    parser.add_argument("--formats", nargs="+", default=["jpg"], choices=["jpg", "png"])
    parser.add_argument("--export-after-apply", action="store_true")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.add_argument("--confirm-apply", action="store_true")
    parser.add_argument("--confirm-export", action="store_true")
    parser.add_argument("--write-plan", action="store_true", help=f"Write the JSON response under {SAFE_OUTPUT_DIR}.")
    parser.add_argument("--write-xmp", action="store_true", help=f"Write an XMP sidecar preview under {SAFE_OUTPUT_DIR}.")
    _slider_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = call_tool(build_arguments(args))
    if args.write_plan:
        plan_path = write_plan(payload, args.basename)
        payload.setdefault("details", {})["written_plan_path"] = plan_path.relative_to(REPO_ROOT).as_posix()
    if args.write_xmp:
        xmp_path = write_xmp(payload, args.basename)
        payload.setdefault("details", {})["written_xmp_path"] = xmp_path.relative_to(REPO_ROOT).as_posix()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
