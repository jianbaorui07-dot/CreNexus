from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

BRIDGE_ID = "blender"


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    home = str(Path.home())
    if home and value.lower().startswith(home.lower()):
        return "<USER_HOME>" + value[len(home) :]
    return re.sub(r"C:\\Users\\[^\\]+", r"<USER_HOME>", value, flags=re.IGNORECASE)


def probe() -> dict[str, Any]:
    env_value = os.environ.get("STARBRIDGE_BLENDER_EXE") or os.environ.get("BLENDER_EXE")
    env_exists = bool(env_value and Path(env_value).exists())
    blender_on_path = shutil.which("blender") is not None or shutil.which("blender.exe") is not None
    report: dict[str, Any] = {
        "bridge_id": BRIDGE_ID,
        "ok": env_exists or blender_on_path,
        "detected": {
            "platform": platform.system() or platform.platform(),
            "blender_env_configured": bool(env_value),
            "blender_env_exists": env_exists,
            "blender_on_path": blender_on_path,
        },
        "errors": [],
        "warnings": [],
        "safe_to_commit": True,
    }
    if env_value and not env_exists:
        report["warnings"].append(
            {
                "code": "blender_env_missing",
                "message": "Configured Blender executable does not exist.",
            }
        )
    if not report["ok"]:
        report["errors"].append(
            {"code": "blender_not_detected", "message": "Blender executable was not detected."}
        )
    return report


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def print_text(report: dict[str, Any]) -> None:
    print("Blender 三维场景桥 probe")
    print("=" * 24)
    print("bridge_id:", report["bridge_id"])
    print("ok:", report["ok"])
    for key, value in report["detected"].items():
        print(f"{key}:", redact(str(value)) if isinstance(value, str) else value)
    for error in report["errors"]:
        print("error:", error.get("code"), error.get("message"))
    for warning in report["warnings"]:
        print("warning:", warning.get("code"), warning.get("message"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="只读检测本机 Blender bridge，输出安全 JSON report。"
    )
    parser.add_argument("--json", action="store_true", help="只向 stdout 输出 JSON。")
    parser.add_argument(
        "--report-path",
        default=str(Path(__file__).resolve().parent / "reports" / "blender_probe_report.json"),
    )
    args = parser.parse_args()
    report = probe()
    write_report(report, Path(args.report_path))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
