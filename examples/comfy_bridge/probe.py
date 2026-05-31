from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BRIDGE_ID = "comfyui"
DEFAULT_BASE_URL = "http://127.0.0.1:8188"
BASIC_NODES = ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"]


def redacted_path(value: str) -> str:
    home = str(Path.home())
    if home and value.lower().startswith(home.lower()):
        return "<USER_HOME>" + value[len(home) :]
    return re.sub(r"C:\\Users\\[^\\]+", r"<USER_HOME>", value, flags=re.IGNORECASE)


def safe_error(exc: BaseException) -> str:
    return redacted_path(str(exc))


def build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def get_json(base_url: str, path: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(build_url(base_url, path), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe(base_url: str, timeout: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "bridge_id": BRIDGE_ID,
        "ok": False,
        "detected": {
            "base_url": base_url,
            "system_stats": False,
            "object_info": False,
            "basic_nodes_checked": [],
        },
        "status": "unknown",
        "errors": [],
        "warnings": [],
        "safe_to_commit": True,
    }

    try:
        stats = get_json(base_url, "/system_stats", timeout)
        report["detected"]["system_stats"] = True
        report["detected"]["comfyui_version"] = stats.get("system", {}).get("comfyui_version")
        report["detected"]["python_version"] = stats.get("system", {}).get("python_version")
        report["detected"]["device_count"] = len(stats.get("devices", []))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        report["status"] = "unavailable"
        report["errors"].append({"code": "system_stats_failed", "message": safe_error(exc)})
        return report

    try:
        object_info = get_json(base_url, "/object_info", timeout)
        report["detected"]["object_info"] = True
        report["detected"]["basic_nodes_checked"] = [node for node in BASIC_NODES if node in object_info]
        missing_nodes = [node for node in BASIC_NODES if node not in object_info]
        if missing_nodes:
            report["warnings"].append(
                {
                    "code": "basic_nodes_missing",
                    "message": "Some expected ComfyUI nodes were not listed.",
                    "nodes": missing_nodes,
                }
            )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        report["status"] = "unavailable"
        report["errors"].append({"code": "object_info_failed", "message": safe_error(exc)})
        return report

    report["ok"] = report["detected"]["system_stats"] and report["detected"]["object_info"]
    report["status"] = "available" if report["ok"] else "unavailable"
    return report


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def print_text(report: dict[str, Any]) -> None:
    print("ComfyUI 图像生成桥 probe")
    print("=" * 24)
    print("bridge_id:", report["bridge_id"])
    print("ok:", report["ok"])
    print("base_url:", report["detected"].get("base_url"))
    print("system_stats:", report["detected"].get("system_stats"))
    print("object_info:", report["detected"].get("object_info"))
    print("basic_nodes_checked:", ", ".join(report["detected"].get("basic_nodes_checked", [])))
    for error in report["errors"]:
        print("error:", error.get("code"), error.get("message"))
    for warning in report["warnings"]:
        print("warning:", warning.get("code"), warning.get("message"))


def main() -> None:
    default_url = os.environ.get("STARBRIDGE_COMFYUI_URL") or os.environ.get("COMFY_BASE_URL") or DEFAULT_BASE_URL
    parser = argparse.ArgumentParser(description="只读检测本机 ComfyUI 服务，输出安全 JSON report。")
    parser.add_argument("--comfy-url", default=default_url, help="ComfyUI API 地址，默认读取 STARBRIDGE_COMFYUI_URL。")
    parser.add_argument("--timeout", type=int, default=8, help="HTTP 请求超时时间，单位秒。")
    parser.add_argument("--json", action="store_true", help="只向 stdout 输出 JSON。")
    parser.add_argument("--soft-exit", action="store_true", help="ComfyUI 不在线时仍返回 0，供 CI / preflight 使用。")
    parser.add_argument(
        "--report-path",
        default=str(Path(__file__).resolve().parent / "reports" / "comfyui_probe_report.json"),
        help="本机安全 report 输出路径，reports/ 已被 .gitignore 忽略。",
    )
    args = parser.parse_args()

    report = probe(args.comfy_url, args.timeout)
    write_report(report, Path(args.report_path))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)

    if not report["ok"] and not args.soft_exit:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("建议使用 Python 3.10 或更新版本运行本 probe。")
    main()
