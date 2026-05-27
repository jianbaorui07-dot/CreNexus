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
BASIC_COMFY_NODES = ["CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode", "SaveImage"]
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp.core.security import sanitize_details, sanitize_text  # noqa: E402

DOWNLOAD_INBOX = os.environ.get("STARBRIDGE_DOWNLOAD_INBOX")
STATUS_LABELS = {
    "ok": "正常",
    "warn": "需配置",
    "missing": "未找到",
    "error": "错误",
}


def safe_value(value):
    return sanitize_details(value)


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def status(name: str, state: str, details: list[str], data: dict | None = None, label: str | None = None) -> dict:
    return {
        "name": name,
        "label": label or name,
        "status": state,
        "status_label": STATUS_LABELS.get(state, state),
        "details": safe_value(details),
        "data": safe_value(data or {}),
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

    candidates.extend([REPO_ROOT / "ComfyUI"])

    for candidate in unique_paths(candidates):
        if (candidate / "main.py").exists():
            return candidate
    return None


def find_comfy_launcher() -> Path | None:
    env_path = os.environ.get("COMFY_LAUNCHER") or os.environ.get("COMFY_START_SCRIPT")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend([REPO_ROOT / "Start_ComfyUI_Codex.cmd"])

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
            f"接口地址：{base_url}",
            f"状态说明：无法连接 ComfyUI。",
            f"错误信息：{exc}",
            "处理建议：先启动 ComfyUI，再重新运行本脚本。",
        ]
        if comfy_root:
            details.append(f"本机 ComfyUI 根目录：{comfy_root}")
        if comfy_launcher:
            details.append(f"本机启动脚本：{comfy_launcher}")
        if DOWNLOAD_INBOX:
            details.append(f"下载收件箱 STARBRIDGE_DOWNLOAD_INBOX：{DOWNLOAD_INBOX}")
        return status(
            "ComfyUI",
            "missing",
            details,
            {
                "base_url": base_url,
                "local_root": str(comfy_root) if comfy_root else None,
                "launcher": str(comfy_launcher) if comfy_launcher else None,
            },
            "ComfyUI 图像生成桥",
        )

    system = stats.get("system", {})
    devices = stats.get("devices", [])
    details = [
        f"接口地址：{base_url}",
        f"ComfyUI 版本：{system.get('comfyui_version') or '未知'}",
        f"Python 版本：{system.get('python_version') or '未知'}",
        f"显卡设备数量：{len(devices)}",
    ]

    try:
        object_info = get_json(base_url, "/object_info", timeout)
        detected_nodes = [node for node in BASIC_COMFY_NODES if node in object_info]
        details.append(f"基础节点可读数量：{len(detected_nodes)}/{len(BASIC_COMFY_NODES)}")
    except Exception as exc:  # noqa: BLE001 - status script should keep going.
        detected_nodes = []
        details.append(f"基础节点检查失败：{exc}")

    if comfy_root:
        details.append(f"本机 ComfyUI 根目录：{comfy_root}")
    if comfy_launcher:
        details.append(f"本机启动脚本：{comfy_launcher}")

    return status(
        "ComfyUI",
        "ok",
        details,
        {
            "base_url": base_url,
            "local_root": str(comfy_root) if comfy_root else None,
            "launcher": str(comfy_launcher) if comfy_launcher else None,
            "basic_nodes_checked": detected_nodes,
        },
        "ComfyUI 图像生成桥",
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
            "状态说明：未找到 Blender 可执行文件。",
            "处理建议：把 BLENDER_EXE 设置为完整 blender.exe 路径，或安装到常见目录。",
            f"Blender MCP 桥目录：{blender_mcp if blender_mcp else '未找到'}",
        ]
        if blender_mcp_launcher:
            details.append(f"Blender MCP 启动脚本：{blender_mcp_launcher}")
        if blender_mcp:
            return status(
                "Blender",
                "warn",
                [
                    *details,
                    "桥接文件存在，但 Blender 可执行文件还没有配置。",
                ],
                {
                    "blender_mcp_dir": str(blender_mcp),
                    "blender_mcp_launcher": str(blender_mcp_launcher) if blender_mcp_launcher else None,
                },
                "Blender 三维场景桥",
            )
        return status(
            "Blender",
            "missing",
            details,
            label="Blender 三维场景桥",
        )

    details = [
        f"Blender 可执行文件：{blender}",
        f"Blender MCP 桥目录：{blender_mcp if blender_mcp else '未找到'}",
    ]
    if blender_mcp_launcher:
        details.append(f"Blender MCP 启动脚本：{blender_mcp_launcher}")
    if probe_executable:
        try:
            details.append(f"版本探测：{command_version(blender, ['--version'], timeout)}")
        except Exception as exc:  # noqa: BLE001 - status script should keep going.
            return status("Blender", "warn", [*details, f"版本探测失败：{exc}"], label="Blender 三维场景桥")
    else:
        details.append("已跳过可执行文件探测。需要运行 blender --version 时加 --probe-executables。")

    return status(
        "Blender",
        "ok",
        details,
        {
            "executable": str(blender),
            "blender_mcp_dir": str(blender_mcp) if blender_mcp else None,
            "blender_mcp_launcher": str(blender_mcp_launcher) if blender_mcp_launcher else None,
        },
        "Blender 三维场景桥",
    )


def find_autocad() -> Path | None:
    env_path = os.environ.get("AUTOCAD_EXE")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    candidates.extend(
        [
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
        f"MCP 服务脚本：{'已找到' if server.exists() else '未找到'}（{server}）",
        f"依赖文件：{'已找到' if requirements.exists() else '未找到'}（{requirements}）",
        f"AutoCAD 可执行文件：{autocad if autocad else '未找到'}",
        f"当前 Python 是否有 pywin32/win32com：{has_win32com}",
    ]

    if server.exists() and autocad:
        state = "ok"
    elif server.exists():
        state = "warn"
        details.append("CAD MCP 项目存在，但默认目录和 AUTOCAD_EXE 中未找到 AutoCAD。")
    else:
        state = "missing"
        details.append("AutoCAD MCP 服务项目缺失。")

    return status("CAD", state, details, {"autocad_executable": str(autocad) if autocad else None}, "CAD 工程制图桥")


def find_photoshop() -> Path | None:
    env_path = os.environ.get("PHOTOSHOP_EXE")
    if not env_path:
        return None

    candidate = Path(env_path)
    return candidate if candidate.exists() else None


def check_photoshop(probe_com: bool) -> dict:
    photoshop = find_photoshop()
    has_win32com = importlib.util.find_spec("win32com") is not None
    details = [
        "安全说明：Photoshop 安装路径不写死在公开仓库里。",
        f"是否配置 PHOTOSHOP_EXE：{bool(os.environ.get('PHOTOSHOP_EXE'))}",
        f"PHOTOSHOP_EXE 路径是否存在：{bool(photoshop)}",
        f"当前 Python 是否有 pywin32/win32com：{has_win32com}",
    ]
    data: dict[str, str | bool | int | None] = {
        "photoshop_exe_configured": bool(os.environ.get("PHOTOSHOP_EXE")),
        "photoshop_exe_exists": bool(photoshop),
        "has_win32com": has_win32com,
    }

    if not probe_com:
        details.append("已跳过 COM 探测。需要连接已打开的 Photoshop 时加 --probe-executables。")
        return status("Photoshop", "warn" if not has_win32com else "ok", details, data, "Photoshop 修图桥")

    if not has_win32com:
        details.append("处理建议：如需 Python COM 探测，请安装 pywin32。")
        return status("Photoshop", "warn", details, data, "Photoshop 修图桥")

    try:
        import win32com.client  # type: ignore[import-not-found]

        app = win32com.client.GetActiveObject("Photoshop.Application")
        version = str(app.Version)
        documents = int(app.Documents.Count)
        details.append(f"已连接 Photoshop COM：版本 {version}，当前文档数 {documents}")
        data.update({"active_com_object": True, "version": version, "documents": documents})
        return status("Photoshop", "ok", details, data, "Photoshop 修图桥")
    except Exception as exc:  # noqa: BLE001 - status script should keep going.
        details.append(f"未找到正在运行的 Photoshop COM 对象：{exc}")
        details.append("处理建议：手动打开 Photoshop 后，再加 --probe-executables 运行。")
        data["active_com_object"] = False
        return status("Photoshop", "warn", details, data, "Photoshop 修图桥")


def find_illustrator() -> Path | None:
    env_path = os.environ.get("ILLUSTRATOR_EXE")
    if not env_path:
        return None

    candidate = Path(env_path)
    return candidate if candidate.exists() else None


def check_illustrator(probe_com: bool) -> dict:
    illustrator = find_illustrator()
    has_win32com = importlib.util.find_spec("win32com") is not None
    details = [
        "术语说明：这里的 AI 文件指 Adobe Illustrator 的 .ai 矢量工程，不是大模型 AI。",
        "安全说明：Illustrator 安装路径、AI 私有工程、源图和导出结果不写进公开仓库。",
        f"是否配置 ILLUSTRATOR_EXE：{bool(os.environ.get('ILLUSTRATOR_EXE'))}",
        f"ILLUSTRATOR_EXE 路径是否存在：{bool(illustrator)}",
        f"当前 Python 是否有 pywin32/win32com：{has_win32com}",
    ]
    data: dict[str, str | bool | int | None] = {
        "illustrator_exe_configured": bool(os.environ.get("ILLUSTRATOR_EXE")),
        "illustrator_exe_exists": bool(illustrator),
        "has_win32com": has_win32com,
    }

    if not probe_com:
        details.append("已跳过 COM 探测。需要连接已打开的 Illustrator 时加 --probe-executables。")
        if illustrator:
            state = "ok"
        elif has_win32com:
            state = "warn"
            details.append("pywin32/win32com 可用，但还没有确认 Illustrator 可执行文件或正在运行的 COM 对象。")
        else:
            state = "warn"
        return status("Illustrator", state, details, data, "AI 矢量文件桥")

    if not has_win32com:
        details.append("处理建议：如需 Python COM 探测，请安装 pywin32。")
        return status("Illustrator", "warn", details, data, "AI 矢量文件桥")

    try:
        import win32com.client  # type: ignore[import-not-found]

        app = win32com.client.GetActiveObject("Illustrator.Application")
        version = str(app.Version)
        documents = int(app.Documents.Count)
        details.append(f"已连接 Illustrator COM：版本 {version}，当前文档数 {documents}")
        data.update({"active_com_object": True, "version": version, "documents": documents})
        return status("Illustrator", "ok", details, data, "AI 矢量文件桥")
    except Exception as exc:  # noqa: BLE001 - status script should keep going.
        details.append(f"未找到正在运行的 Illustrator COM 对象：{exc}")
        details.append("处理建议：手动打开 Illustrator 后，再加 --probe-executables 运行。")
        data["active_com_object"] = False
        return status("Illustrator", "warn", details, data, "AI 矢量文件桥")


def env_path_exists(name: str) -> tuple[bool, bool]:
    value = os.environ.get(name)
    return bool(value), bool(value and Path(value).exists())


def check_jianying_capcut() -> dict:
    jianying_exe_configured, jianying_exe_exists = env_path_exists("JIANYING_EXE")
    capcut_exe_configured, capcut_exe_exists = env_path_exists("CAPCUT_EXE")
    jianying_drafts_configured, jianying_drafts_exists = env_path_exists("JIANYING_DRAFTS_DIR")
    capcut_drafts_configured, capcut_drafts_exists = env_path_exists("CAPCUT_DRAFTS_DIR")

    details = [
        "安全说明：剪映/CapCut 草稿路径、素材路径、账号和导出视频不写进公开仓库。",
        f"是否配置 JIANYING_EXE：{jianying_exe_configured}，路径是否存在：{jianying_exe_exists}",
        f"是否配置 CAPCUT_EXE：{capcut_exe_configured}，路径是否存在：{capcut_exe_exists}",
        f"是否配置 JIANYING_DRAFTS_DIR：{jianying_drafts_configured}，路径是否存在：{jianying_drafts_exists}",
        f"是否配置 CAPCUT_DRAFTS_DIR：{capcut_drafts_configured}，路径是否存在：{capcut_drafts_exists}",
    ]
    data = {
        "jianying_exe_configured": jianying_exe_configured,
        "jianying_exe_exists": jianying_exe_exists,
        "capcut_exe_configured": capcut_exe_configured,
        "capcut_exe_exists": capcut_exe_exists,
        "jianying_drafts_dir_configured": jianying_drafts_configured,
        "jianying_drafts_dir_exists": jianying_drafts_exists,
        "capcut_drafts_dir_configured": capcut_drafts_configured,
        "capcut_drafts_dir_exists": capcut_drafts_exists,
    }

    has_executable = jianying_exe_exists or capcut_exe_exists
    has_drafts = jianying_drafts_exists or capcut_drafts_exists
    if has_executable and has_drafts:
        state = "ok"
        details.append("本机实例已具备可执行文件和草稿目录线索。")
    elif any(data.values()):
        state = "warn"
        details.append("本机实例已有部分配置，但还缺可执行文件或草稿目录确认。")
    else:
        state = "warn"
        details.append("处理建议：先手动确认剪映/CapCut 能正常打开，再用环境变量配置草稿目录。")

    return status("JianyingCapCut", state, details, data, "剪映/CapCut 短视频草稿桥")


def print_text_report(results: list[dict]) -> None:
    print("星桥本地软件接入状态")
    print("=" * 28)
    for result in results:
        print(f"\n[{result['status_label']}] {result['label']}")
        for detail in result["details"]:
            print(f"- {sanitize_text(str(detail))}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="检查星桥本地软件接入状态，不读取账号、密钥或私有素材。",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="显示帮助并退出。")
    parser.add_argument(
        "--comfy-url",
        default=os.environ.get("STARBRIDGE_COMFYUI_URL") or os.environ.get("COMFY_BASE_URL", DEFAULT_COMFY_URL),
    )
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument(
        "--probe-executables",
        action="store_true",
        help="对已找到的软件运行轻量版本探测；部分商业软件可能启动较慢。",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    parser.add_argument("--strict", action="store_true", help="任一 bridge 未通过时返回退出码 1。")
    args = parser.parse_args()

    results = [
        check_comfy(args.comfy_url, args.timeout),
        check_blender(args.probe_executables, args.timeout),
        check_cad(),
        check_photoshop(args.probe_executables),
        check_illustrator(args.probe_executables),
        check_jianying_capcut(),
    ]

    if args.json:
        print(json.dumps(sanitize_details({"results": results}), ensure_ascii=False, indent=2))
    else:
        print_text_report(results)

    if args.strict and any(result["status"] in {"error", "missing", "warn"} for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("建议使用 Python 3.10 或更新版本运行本状态脚本。")
    main()
