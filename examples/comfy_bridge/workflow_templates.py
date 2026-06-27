from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.comfy_bridge.workflow_template_registry import (
    compose_from_template,
    get_workflow_template,
    list_workflow_templates,
    validate_workflow_template_registry,
)


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
        description="Inspect and compose bundled public ComfyUI workflow templates."
    )
    output_parent = argparse.ArgumentParser(add_help=False)
    output_parent.add_argument("--json", action="store_true", help="Output JSON. This is the default.")
    output_parent.add_argument("--compact", action="store_true", help="Use compact JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "list", parents=[output_parent], help="List bundled public workflow templates."
    )
    subparsers.add_parser(
        "validate",
        parents=[output_parent],
        help="Validate the bundled workflow template registry.",
    )

    get_parser = subparsers.add_parser(
        "get", parents=[output_parent], help="Return one workflow template."
    )
    get_parser.add_argument("--template-id", required=True)

    compose_parser = subparsers.add_parser(
        "from-template",
        parents=[output_parent],
        help="Compose a safe placeholder workflow from one template.",
    )
    compose_parser.add_argument("--template-id", required=True)
    compose_parser.add_argument("--prompt")
    compose_parser.add_argument("--negative-prompt")
    compose_parser.add_argument("--width", type=int)
    compose_parser.add_argument("--height", type=int)
    compose_parser.add_argument("--seed", type=int)
    compose_parser.add_argument("--steps", type=int)
    compose_parser.add_argument("--cfg", type=float)
    compose_parser.add_argument("--sampler")
    compose_parser.add_argument("--scheduler")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        payload = list_workflow_templates()
    elif args.command == "validate":
        payload = validate_workflow_template_registry()
    elif args.command == "get":
        payload = get_workflow_template(args.template_id)
    elif args.command == "from-template":
        payload = compose_from_template(args.template_id, _template_arguments(args))
    else:  # pragma: no cover - argparse prevents this path.
        parser.error(f"unsupported command: {args.command}")

    _print_json(payload, compact=args.compact)
    if not payload.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
