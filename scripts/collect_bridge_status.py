from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
FIELDS = [
    "bridge_id",
    "name",
    "status",
    "platform",
    "supported_tasks",
    "unsupported_tasks",
    "entrypoints",
]
VALID_STATUS = {"stable", "experimental", "research", "planned"}


def load_bridge_manifests() -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for bridge_dir in sorted(EXAMPLES_DIR.glob("*_bridge")):
        manifest_path = bridge_dir / "bridge.json"
        legacy_path = bridge_dir / "bridge_status.json"
        source_path = manifest_path if manifest_path.exists() else legacy_path
        if not source_path.exists():
            continue

        data = json.loads(source_path.read_text(encoding="utf-8"))
        if source_path.name == "bridge_status.json":
            data = legacy_status_to_manifest(data)
        validate_manifest(data, source_path)
        data["_path"] = str(source_path.relative_to(REPO_ROOT)).replace("\\", "/")
        manifests.append(data)
    return manifests


def legacy_status_to_manifest(data: dict[str, Any]) -> dict[str, Any]:
    maturity = str(data.get("maturity", "planned"))
    status = "experimental" if maturity == "prototype" else maturity
    if status not in VALID_STATUS:
        status = "planned"
    return {
        "bridge_id": data.get("bridge_id"),
        "name": data.get("display_name"),
        "status": status,
        "platform": data.get("platforms", []),
        "requires": data.get("local_dependency", []),
        "entrypoints": {},
        "supported_tasks": ["probe"] if data.get("probe_supported") else [],
        "unsupported_tasks": data.get("next_steps", []),
        "safety_notes": data.get("known_risks", []),
    }


def validate_manifest(data: dict[str, Any], path: Path) -> None:
    required = {
        "bridge_id",
        "name",
        "status",
        "platform",
        "requires",
        "entrypoints",
        "supported_tasks",
        "unsupported_tasks",
        "safety_notes",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(missing)}")
    if data["status"] not in VALID_STATUS:
        raise ValueError(f"{path}: status must be one of {sorted(VALID_STATUS)}")


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
    parser = argparse.ArgumentParser(description="汇总 examples/*_bridge/bridge.json。")
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
    if sys.version_info < (3, 10):
        raise SystemExit("建议使用 Python 3.10 或更新版本运行本脚本。")
    main()
