from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
REPO_ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_INBOX = Path(r"E:\00_待整理收件箱\下载")


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def status(name: str, state: str, details: list[str], data: dict | None = None) -> dict:
    return {
        "name": name,
        "status": state,
        "details": details,
        "data": data or {},
    }


def get_json(base_url: str, path: str, timeout: int) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def find_comfy_root() -> Path | None:
    env_path = os.environ.get("COMFY_ROOT") or os.environ.get("COMFYUI_PATH")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            Path(r"D:\AIGC\comfyui安装包\ComfyUI"),
            Path(r"D:\AIGC\ComfyUI"),
            Path(r"C:\Users\jian\AppData\Local\ComfyUI"),
            REPO_ROOT / "ComfyUI",
        ]
    )

    for candidate in unique_paths(candidates):
        if (candidate / "main.py").exists():
            return candidate
    return None


def find_comfy_launcher() -> Path | None:
    env_path = os.environ.get("COMFY_LAUNCHER") or os.environ.get("COMFY_START_SCRIPT")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            Path(r"D:\AIGC\Start_ComfyUI_Codex.cmd"),
            REPO_ROOT / "Start_ComfyUI_Codex.cmd",
        ]
    )

    for candidate in unique_paths(candidates):
        if candidate.exists():
            return candidate
    return None


def check_comfy(base_url: str, timeout: int) -> dict:
    comfy_root = find_comfy_root()
    comfy_launcher = find_comfy_launcher()
    try:
        stats = get_json(base_url, "/system_stats", timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        details = [
            f"Not reachable at {base_url}.",
            f"Error: {exc}",
            "Start ComfyUI first, then rerun this script.",
        ]
        if comfy_root:
            details.append(f"Local ComfyUI root: {comfy_root}")
        if comfy_launcher:
            details.append(f"Launch script: {comfy_launcher}")
        if DOWNLOAD_INBOX.exists():
            details.append(f"Download inbox for new source/projects: {DOWNLOAD_INBOX}")
        return status(
            "ComfyUI",
            "missing",
            details,
            {
                "base_url": base_url,
                "local_root": str(comfy_root) if comfy_root else None,
                "launcher": str(comfy_launcher) if comfy_launcher else None,
            },
        )

    system = stats.get("system", {})
    devices = stats.get("devices", [])
    details = [
        f"API: {base_url}",
        f"ComfyUI version: {system.get('comfyui_version') or 'unknown'}",
        f"Python: {system.get('python_version') or 'unknown'}",
        f"Devices: {len(devices)}",
    ]

    try:
        queue = get_json(base_url, "/queue", timeout)
        details.append(f"Queue running: {len(queue.get('queue_running', []))}")
        details.append(f"Queue pending: {len(queue.get('queue_pending', []))}")
    except Exception as exc:  # noqa: BLE001 - status script should keep going.
        details.append(f"Queue check failed: {exc}")

    try:
        loader = get_json(base_url, "/object_info/CheckpointLoaderSimple", timeout)
        checkpoints = loader["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        details.append(f"Checkpoints: {len(checkpoints)}")
    except Exception as exc:  # noqa: BLE001 - status script should keep going.
        details.append(f"Checkpoint check failed: {exc}")

    if comfy_root:
        details.append(f"Local ComfyUI root: {comfy_root}")
    if comfy_launcher:
        details.append(f"Launch script: {comfy_launcher}")

    return status(
        "ComfyUI",
        "ok",
        details,
        {
            "base_url": base_url,
            "local_root": str(comfy_root) if comfy_root else None,
            "launcher": str(comfy_launcher) if comfy_launcher else None,
        },
    )


def command_version(command: Path | str, args: list[str], timeout: int) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [str(command), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=creationflags,
        check=False,
    )
    output = (completed.stdout or completed.stderr).strip()
    first_line = output.splitlines()[0] if output else f"exit code {completed.returncode}"
    return first_line


def find_blender() -> Path | None:
    env_path = os.environ.get("BLENDER_EXE")
    path_candidates: list[Path] = []
    if env_path:
        path_candidates.append(Path(env_path))

    which = shutil.which("blender")
    if which:
        path_candidates.append(Path(which))

    path_candidates.extend(
        [
            Path(r"D:\AIGC\CAD\blender.exe"),
            Path(r"D:\AIGC\CAD\5.0\blender.exe"),
            Path(r"D:\AIGC\Blender 5.0\blender.exe"),
            Path(r"D:\AIGC\Blender\blender.exe"),
            Path(r"D:\AIGC\blender\blender.exe"),
            Path(r"D:\AIGC\blender-5.0\blender.exe"),
            Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
            Path(r"C:\Program Files\Blender Foundation\Blender\blender.exe"),
        ]
    )

    for candidate in unique_paths(path_candidates):
        if candidate.exists():
            return candidate
    return None


def find_blender_mcp_dir() -> Path | None:
    env_path = os.environ.get("BLENDER_MCP_DIR")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            Path(r"D:\AIGC\blender-mcp"),
            REPO_ROOT / "blender-mcp",
        ]
    )

    for candidate in unique_paths(candidates):
        if (candidate / "start_blender_mcp_server.py").exists() or (candidate / "addon.py").exists():
            return candidate
    return None


def check_blender(probe_executable: bool, timeout: int) -> dict:
    blender = find_blender()
    blender_mcp = find_blender_mcp_dir()
    blender_mcp_launcher = blender_mcp / "Start-Blender-MCP.cmd" if blender_mcp else None
    if blender_mcp_launcher and not blender_mcp_launcher.exists():
        blender_mcp_launcher = None
    if not blender:
        details = [
            "No Blender executable found.",
            "Set BLENDER_EXE to the full blender.exe path or install Blender in a standard location.",
            f"Blender MCP bridge: {blender_mcp if blender_mcp else 'not found'}",
        ]
        if blender_mcp_launcher:
            details.append(f"Blender MCP launch script: {blender_mcp_launcher}")
        if blender_mcp:
            return status(
                "Blender",
                "warn",
                [
                    *details,
                    "Bridge files exist, but the Blender executable is not configured yet.",
                ],
                {
                    "blender_mcp_dir": str(blender_mcp),
                    "blender_mcp_launcher": str(blender_mcp_launcher) if blender_mcp_launcher else None,
                },
            )
        return status(
            "Blender",
            "missing",
            details,
        )

    details = [
        f"Executable: {blender}",
        f"Blender MCP bridge: {blender_mcp if blender_mcp else 'not found'}",
    ]
    if blender_mcp_launcher:
        details.append(f"Blender MCP launch script: {blender_mcp_launcher}")
    if probe_executable:
        try:
            details.append(f"Version probe: {command_version(blender, ['--version'], timeout)}")
        except Exception as exc:  # noqa: BLE001 - status script should keep going.
            return status("Blender", "warn", [*details, f"Version probe failed: {exc}"])
    else:
        details.append("Executable probe skipped. Use --probe-executables to run blender --version.")

    return status(
        "Blender",
        "ok",
        details,
        {
            "executable": str(blender),
            "blender_mcp_dir": str(blender_mcp) if blender_mcp else None,
            "blender_mcp_launcher": str(blender_mcp_launcher) if blender_mcp_launcher else None,
        },
    )


def find_autocad() -> Path | None:
    env_path = os.environ.get("AUTOCAD_EXE")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
            Path(r"D:\AIGC\cad2026\CAD2026\AutoCAD 2026\acad.exe"),
            Path(r"C:\Program Files\Autodesk\AutoCAD 2026\acad.exe"),
            Path(r"C:\Program Files\Autodesk\AutoCAD 2025\acad.exe"),
        ]
    )

    for candidate in unique_paths(candidates):
        if candidate.exists():
            return candidate
    return None


def check_cad() -> dict:
    server = REPO_ROOT / "cad-mcp-autocad" / "src" / "server.py"
    requirements = REPO_ROOT / "cad-mcp-autocad" / "requirements.txt"
    autocad = find_autocad()
    has_win32com = importlib.util.find_spec("win32com") is not None

    details = [
        f"MCP server: {'found' if server.exists() else 'missing'} ({server})",
        f"Requirements: {'found' if requirements.exists() else 'missing'} ({requirements})",
        f"AutoCAD executable: {autocad if autocad else 'not found'}",
        f"Current Python has pywin32/win32com: {has_win32com}",
    ]

    if server.exists() and autocad:
        state = "ok"
    elif server.exists():
        state = "warn"
        details.append("MCP project exists, but AutoCAD was not found in default locations.")
    else:
        state = "missing"
        details.append("AutoCAD MCP server project is missing.")

    return status("CAD", state, details, {"autocad_executable": str(autocad) if autocad else None})


def print_text_report(results: list[dict]) -> None:
    print("StarBridge local bridge status")
    print("=" * 30)
    for result in results:
        marker = {"ok": "OK", "warn": "WARN", "missing": "MISSING", "error": "ERROR"}.get(
            result["status"], result["status"].upper()
        )
        print(f"\n[{marker}] {result['name']}")
        for detail in result["details"]:
            print(f"- {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check local StarBridge integrations without reading credentials or private files."
    )
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_BASE_URL", DEFAULT_COMFY_URL))
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument(
        "--probe-executables",
        action="store_true",
        help="Run lightweight version commands for detected executables. This may start slow vendor binaries.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results = [
        check_comfy(args.comfy_url, args.timeout),
        check_blender(args.probe_executables, args.timeout),
        check_cad(),
    ]

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        print_text_report(results)

    if any(result["status"] == "error" for result in results):
        raise SystemExit(2)
    if any(result["status"] in {"missing", "warn"} for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ is recommended for this status script.")
    main()
