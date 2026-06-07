from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_PATH = REPO_ROOT / "examples" / "bridge_capabilities.json"
EXAMPLES_DIR = REPO_ROOT / "examples"
REQUIRED_FIELDS = {
    "bridge_id",
    "display_name",
    "bridge_dir",
    "status_file",
    "primary_docs",
    "safe_probe_commands",
    "local_action_commands",
    "capability_categories",
    "current_capabilities",
    "planned_capabilities",
    "public_safety_rules",
}
LIST_FIELDS = {
    "primary_docs",
    "safe_probe_commands",
    "local_action_commands",
    "capability_categories",
    "current_capabilities",
    "planned_capabilities",
    "public_safety_rules",
}


def load_registry(path: Path = CAPABILITY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def existing_status_ids() -> set[str]:
    ids: set[str] = set()
    for status_path in EXAMPLES_DIR.glob("*_bridge/bridge_status.json"):
        data = json.loads(status_path.read_text(encoding="utf-8"))
        ids.add(str(data.get("bridge_id")))
    return ids


def validate_registry(registry: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if registry.get("schema_version") != "1.0":
        failures.append("schema_version must be 1.0")

    bridges = registry.get("bridges")
    if not isinstance(bridges, list) or not bridges:
        return [*failures, "bridges must be a non-empty list"]

    seen: set[str] = set()
    for index, bridge in enumerate(bridges, start=1):
        if not isinstance(bridge, dict):
            failures.append(f"bridges[{index}] must be an object")
            continue

        bridge_id = str(bridge.get("bridge_id", ""))
        missing = REQUIRED_FIELDS - set(bridge)
        extra = set(bridge) - REQUIRED_FIELDS
        if missing:
            failures.append(f"{bridge_id or index} missing fields: {sorted(missing)}")
        if extra:
            failures.append(f"{bridge_id or index} has unexpected fields: {sorted(extra)}")
        if bridge_id in seen:
            failures.append(f"{bridge_id} is duplicated")
        seen.add(bridge_id)

        for field in LIST_FIELDS:
            value = bridge.get(field)
            if not isinstance(value, list):
                failures.append(f"{bridge_id} {field} must be a list")
                continue
            if field != "local_action_commands" and not value:
                failures.append(f"{bridge_id} {field} must not be empty")

        for field in ("bridge_dir", "status_file"):
            value = bridge.get(field)
            if isinstance(value, str) and value and not (REPO_ROOT / value).exists():
                failures.append(f"{bridge_id} {field} does not exist: {value}")

        for doc in bridge.get("primary_docs", []):
            if not (REPO_ROOT / str(doc)).exists():
                failures.append(f"{bridge_id} primary_docs does not exist: {doc}")

    status_ids = existing_status_ids()
    capability_ids = {str(bridge.get("bridge_id")) for bridge in bridges if isinstance(bridge, dict)}
    missing_from_registry = status_ids - capability_ids
    extra_in_registry = capability_ids - status_ids
    if missing_from_registry:
        failures.append(f"bridge_status exists but registry is missing: {sorted(missing_from_registry)}")
    if extra_in_registry:
        failures.append(f"registry exists but bridge_status is missing: {sorted(extra_in_registry)}")

    return failures


def compact(items: list[str]) -> str:
    return "<br>".join(str(item).replace("|", "\\|") for item in items)


def to_markdown(registry: dict[str, Any]) -> str:
    lines = [
        "| Bridge | Capability categories | Current capabilities | Planned capabilities | Safety rules |",
        "| --- | --- | --- | --- | --- |",
    ]
    for bridge in registry["bridges"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(bridge["display_name"]).replace("|", "\\|"),
                    compact(bridge["capability_categories"]),
                    compact(bridge["current_capabilities"]),
                    compact(bridge["planned_capabilities"]),
                    compact(bridge["public_safety_rules"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def default_report_dir() -> Path:
    return REPO_ROOT / "output" / "bridge_capabilities"


def write_reports(registry: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "bridge_capability_matrix.json").write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (report_dir / "bridge_capability_matrix.md").write_text(to_markdown(registry), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and render the public bridge capability matrix.")
    parser.add_argument("--json", action="store_true", help="Output JSON.")
    parser.add_argument("--markdown", action="store_true", help="Output Markdown.")
    parser.add_argument("--check", action="store_true", help="Validate only.")
    parser.add_argument("--write-report", action="store_true", help="Write reports into output/bridge_capabilities/.")
    parser.add_argument("--report-dir", default=str(default_report_dir()), help="Custom local report directory.")
    args = parser.parse_args()

    registry = load_registry()
    failures = validate_registry(registry)
    if args.check:
        if failures:
            for failure in failures:
                print(failure)
            raise SystemExit(1)
        print("bridge capability matrix passed")
        return

    if args.write_report:
        write_reports(registry, Path(args.report_dir))

    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(registry), end="")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("Use Python 3.10 or newer to run this script.")
    main()
