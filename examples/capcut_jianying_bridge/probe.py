from __future__ import annotations

import argparse
import json
import os
import platform
import re
from pathlib import Path
from typing import Any

BRIDGE_ID = "capcut_jianying"


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    home = str(Path.home())
    if home and value.lower().startswith(home.lower()):
        return "<USER_HOME>" + value[len(home) :]
    return re.sub(r"C:\\Users\\[^\\]+", r"<USER_HOME>", value, flags=re.IGNORECASE)


def env_path_state(name: str) -> tuple[bool, bool]:
    value = os.environ.get(name)
    return bool(value), bool(value and Path(value).exists())


def probe() -> dict[str, Any]:
    jianying_exe_configured, jianying_exe_exists = env_path_state("JIANYING_EXE")
    capcut_exe_configured, capcut_exe_exists = env_path_state("CAPCUT_EXE")
    jianying_drafts_configured, jianying_drafts_exists = env_path_state("JIANYING_DRAFTS_DIR")
    capcut_drafts_configured, capcut_drafts_exists = env_path_state("CAPCUT_DRAFTS_DIR")

    has_exe = jianying_exe_exists or capcut_exe_exists
    has_draft_dir = jianying_drafts_exists or capcut_drafts_exists
    report: dict[str, Any] = {
        "bridge_id": BRIDGE_ID,
        "ok": has_exe and has_draft_dir,
        "detected": {
            "platform": platform.system() or platform.platform(),
            "jianying_exe_configured": jianying_exe_configured,
            "jianying_exe_exists": jianying_exe_exists,
            "capcut_exe_configured": capcut_exe_configured,
            "capcut_exe_exists": capcut_exe_exists,
            "jianying_drafts_dir_configured": jianying_drafts_configured,
            "jianying_drafts_dir_exists": jianying_drafts_exists,
            "capcut_drafts_dir_configured": capcut_drafts_configured,
            "capcut_drafts_dir_exists": capcut_drafts_exists,
        },
        "errors": [],
        "warnings": [
            {
                "code": "research_only",
                "message": "This bridge is research-only and does not automate the desktop app.",
            }
        ],
        "safe_to_commit": True,
    }
    if not report["ok"]:
        report["errors"].append(
            {
                "code": "draft_bridge_not_configured",
                "message": "No Jianying or CapCut executable and draft directory are configured.",
            }
        )
    return report


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def print_text(report: dict[str, Any]) -> None:
    print("剪映 / CapCut 草稿桥 probe")
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
        description="只读检测剪映 / CapCut 草稿桥配置，输出安全 JSON report。"
    )
    parser.add_argument("--json", action="store_true", help="只向 stdout 输出 JSON。")
    parser.add_argument(
        "--report-path",
        default=str(
            Path(__file__).resolve().parent / "reports" / "capcut_jianying_probe_report.json"
        ),
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
