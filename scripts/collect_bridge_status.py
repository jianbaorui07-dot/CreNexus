from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
FIELDS = [
    "bridge_id",
    "display_name",
    "maturity",
    "platforms",
    "local_dependency",
    "required_env",
    "probe_supported",
    "write_supported",
    "safe_report_supported",
    "last_verified",
    "known_risks",
    "next_steps",
]
VALID_MATURITY = {"stable", "prototype", "planned", "research", "deprecated"}


def load_bridge_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for bridge_dir in sorted(EXAMPLES_DIR.glob("*_bridge")):
        status_path = bridge_dir / "bridge_status.json"
        if not status_path.exists():
            continue

        data = json.loads(status_path.read_text(encoding="utf-8"))
        validate_manifest(data, status_path)
        data["_path"] = str(status_path.relative_to(REPO_ROOT)).replace("\\", "/")
        manifests.append(data)
    return manifests


def validate_manifest(data: dict[str, Any], path: Path) -> None:
    required = {
        "bridge_id",
        "display_name",
        "maturity",
        "platforms",
        "local_dependency",
        "required_env",
        "probe_supported",
        "write_supported",
        "safe_report_supported",
        "last_verified",
        "known_risks",
        "next_steps",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(missing)}")
    if data["maturity"] not in VALID_MATURITY:
        raise ValueError(f"{path}: maturity must be one of {sorted(VALID_MATURITY)}")
    for field in ("platforms", "local_dependency", "required_env", "known_risks", "next_steps"):
        if not isinstance(data.get(field), list):
            raise ValueError(f"{path}: {field} must be a list")
    for field in ("probe_supported", "write_supported", "safe_report_supported"):
        if not isinstance(data.get(field), bool):
            raise ValueError(f"{path}: {field} must be a boolean")


def compact_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def to_markdown(statuses: list[dict[str, Any]]) -> str:
    headers = FIELDS
    rows = []
    for status in statuses:
        rows.append([compact_value(status.get(field, "")) for field in headers])

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总 examples/*_bridge/bridge_status.json。")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="输出 JSON。")
    output.add_argument("--markdown", action="store_true", help="输出 Markdown 表格。")
    args = parser.parse_args()

    statuses = load_bridge_manifests()
    if args.json:
        print(json.dumps({"bridges": statuses}, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(statuses), end="")


if __name__ == "__main__":
    main()
