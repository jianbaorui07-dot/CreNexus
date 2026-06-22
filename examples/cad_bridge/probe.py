from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

BRIDGE_ID = "cad_autocad"


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    home = str(Path.home())
    if home and value.lower().startswith(home.lower()):
        return "<USER_HOME>" + value[len(home) :]
    return re.sub(r"C:\\Users\\[^\\]+", r"<USER_HOME>", value, flags=re.IGNORECASE)


def check_com_registration() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"AutoCAD.Application\CLSID"):
            return True
    except OSError:
        return False


def probe() -> dict[str, Any]:
    is_windows = platform.system() == "Windows"
    cad_mode = os.environ.get("STARBRIDGE_CAD_MODE")
    autocad_env = os.environ.get("AUTOCAD_EXE")
    autocad_env_exists = bool(autocad_env and Path(autocad_env).exists())
    acad_on_path = shutil.which("acad") is not None or shutil.which("acad.exe") is not None
    win32com_available = importlib.util.find_spec("win32com") is not None
    com_registered = check_com_registration()

    report: dict[str, Any] = {
        "bridge_id": BRIDGE_ID,
        "ok": False,
        "detected": {
            "platform": platform.system() or platform.platform(),
            "is_windows": is_windows,
            "starbridge_cad_mode_configured": bool(cad_mode),
            "starbridge_cad_mode": cad_mode if cad_mode else None,
            "autocad_exe_configured": bool(autocad_env),
            "autocad_exe_exists": autocad_env_exists,
            "acad_on_path": acad_on_path,
            "win32com_available": win32com_available,
            "com_registered": com_registered,
        },
        "errors": [],
        "warnings": [],
        "safe_to_commit": True,
    }

    if not is_windows:
        report["errors"].append(
            {"code": "unsupported_platform", "message": "AutoCAD bridge is Windows-first."}
        )
    if autocad_env and not autocad_env_exists:
        report["warnings"].append(
            {
                "code": "autocad_exe_missing",
                "message": "AUTOCAD_EXE is configured but the file does not exist.",
            }
        )
    if not cad_mode:
        report["warnings"].append(
            {"code": "cad_mode_missing", "message": "STARBRIDGE_CAD_MODE is not configured."}
        )
    if not (autocad_env_exists or acad_on_path or com_registered):
        report["errors"].append(
            {
                "code": "autocad_not_detected",
                "message": "AutoCAD executable or COM registration was not detected.",
            }
        )
    if not win32com_available:
        report["warnings"].append(
            {
                "code": "win32com_missing",
                "message": "pywin32/win32com is not available in this Python environment.",
            }
        )

    report["ok"] = is_windows and (autocad_env_exists or acad_on_path or com_registered)
    return report


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def print_text(report: dict[str, Any]) -> None:
    print("CAD / AutoCAD 工程制图桥 probe")
    print("=" * 28)
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
        description="只读检测本机 CAD / AutoCAD 桥，输出安全 JSON report。"
    )
    parser.add_argument("--json", action="store_true", help="只向 stdout 输出 JSON。")
    parser.add_argument(
        "--report-path",
        default=str(Path(__file__).resolve().parent / "reports" / "cad_autocad_probe_report.json"),
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
