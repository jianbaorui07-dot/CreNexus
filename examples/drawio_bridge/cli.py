from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp.adapters.drawio import DiagramForgeService  # noqa: E402


def _print(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DiagramForge safe Draw.io bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("probe")
    sub.add_parser("capabilities")
    plan = sub.add_parser("plan")
    plan.add_argument("--recipe", default="research-framework-v1")
    plan.add_argument("--title", default="Synthetic Research System")
    demo = sub.add_parser("demo")
    demo.add_argument("--recipe", default="research-framework-v1")
    demo.add_argument("--title", default="Synthetic Research System")
    demo.add_argument("--output-base", default="examples/output/diagramforge/research-framework")
    demo.add_argument("--confirm-write", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("path")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("path")
    patch = sub.add_parser("patch")
    patch.add_argument("path")
    patch.add_argument("--element-id", required=True)
    patch.add_argument("--label", required=True)
    patch.add_argument("--confirm-write", action="store_true")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("path")
    rollback.add_argument("--confirm-write", action="store_true")
    export = sub.add_parser("export")
    export.add_argument("path")
    export.add_argument("--format", choices=("svg", "pdf"), default="svg")
    export.add_argument("--output-path")
    export.add_argument("--confirm-write", action="store_true")
    handoff = sub.add_parser("handoff")
    handoff.add_argument("path")
    handoff.add_argument("--target", choices=("canvas", "photoshop", "illustrator"), required=True)
    batch = sub.add_parser("batch")
    batch.add_argument("--recipe", default="system-architecture-v1")
    batch.add_argument("--count", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = DiagramForgeService(REPO_ROOT)
    if args.command == "probe":
        return _print(service.probe({}))
    if args.command == "capabilities":
        return _print(service.capabilities({}))
    if args.command == "plan":
        return _print(
            service.plan(
                {
                    "input_format": "spec",
                    "recipe_id": args.recipe,
                    "parameters": {"title": args.title},
                }
            )
        )
    if args.command == "demo":
        return _print(
            service.create(
                {
                    "input_format": "spec",
                    "recipe_id": args.recipe,
                    "parameters": {"title": args.title},
                    "output_base": args.output_base,
                    "confirm_write": args.confirm_write,
                }
            )
        )
    if args.command == "validate":
        return _print(service.validate({"path": args.path}))
    if args.command == "inspect":
        return _print(service.inspect({"path": args.path}))
    if args.command == "patch":
        return _print(
            service.patch(
                {
                    "path": args.path,
                    "patches": [
                        {"op": "set_label", "element_id": args.element_id, "label": args.label}
                    ],
                    "confirm_write": args.confirm_write,
                }
            )
        )
    if args.command == "rollback":
        return _print(
            service.rollback(
                {
                    "path": args.path,
                    "confirm_write": args.confirm_write,
                }
            )
        )
    if args.command == "export":
        payload = {
            "path": args.path,
            "format": args.format,
            "confirm_write": args.confirm_write,
        }
        if args.output_path:
            payload["output_path"] = args.output_path
        return _print(service.export(payload))
    if args.command == "handoff":
        return _print(service.handoff_plan({"path": args.path, "target": args.target}))
    if args.command == "batch":
        count = min(100, max(1, args.count))
        return _print(
            service.batch(
                {
                    "jobs": [
                        {
                            "recipe_id": args.recipe,
                            "parameters": {"title": f"Batch Diagram {index + 1}"},
                        }
                        for index in range(count)
                    ]
                }
            )
        )
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
