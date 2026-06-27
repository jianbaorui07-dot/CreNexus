from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.comfy_bridge.workflow_agent import workflow_lifecycle_summary


def _print_json(payload: dict[str, Any], *, compact: bool = False) -> None:
    if compact:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _template_arguments(args: argparse.Namespace) -> dict[str, Any]:
    allowed = (
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "seed",
        "steps",
        "cfg",
        "sampler",
        "scheduler",
    )
    return {key: getattr(args, key) for key in allowed if getattr(args, key) is not None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize a ComfyUI workflow job and asset lifecycle without submitting it."
    )
    parser.add_argument(
        "--template-id",
        default="txt2img_basic_v1",
        help="Bundled public template id to compose before summarizing.",
    )
    parser.add_argument(
        "--task-type",
        choices=["txt2img", "img2img", "inpaint", "upscale"],
        help="Compose a default placeholder workflow instead of using --template-id.",
    )
    parser.add_argument("--prompt")
    parser.add_argument("--negative-prompt")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--cfg", type=float)
    parser.add_argument("--sampler")
    parser.add_argument("--scheduler")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output JSON. This is the default.")
    parser.add_argument("--compact", action="store_true", help="Use compact JSON output.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    payload: dict[str, Any] = {
        "confirm_run": args.confirm_run,
        "arguments": _template_arguments(args),
    }
    if args.task_type:
        payload.pop("arguments")
        payload.update(_template_arguments(args))
        payload["task_type"] = args.task_type
    else:
        payload["template_id"] = args.template_id

    result = workflow_lifecycle_summary(payload)
    _print_json(result, compact=args.compact)
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
