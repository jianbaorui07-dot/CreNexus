from __future__ import annotations

import csv
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .app_data import AppDataPaths, resolve_app_data_paths
from .security import sanitize

SCHEMA_VERSION = "starbridge.desktop-connections.v2"
PAIRING_VERSION = "starbridge.desktop-pairing.v1"
APPLICATION_PAIRING_VERSION = "starbridge.application-pairings.v1"
CONNECTOR_BEGIN = "# BEGIN STARBRIDGE DESKTOP CONNECTOR (managed by StarBridge Desktop)"
CONNECTOR_END = "# END STARBRIDGE DESKTOP CONNECTOR"
PAIRING_CODE_ALPHABET = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
PAIRING_CODE_LENGTH = 8
PAIRING_TTL_SECONDS = 15 * 60
MAX_CONFIG_BYTES = 2 * 1024 * 1024
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

JsonObject = dict[str, Any]
ProcessProbe = Callable[[], set[str]]
InstallProbe = Callable[[Iterable[str], str | None], bool]
BridgeProbe = Callable[[str], bool]

APPLICATION_DEFINITIONS: tuple[JsonObject, ...] = (
    {
        "id": "photoshop",
        "name": "Photoshop",
        "mark": "Ps",
        "executables": ("Photoshop.exe",),
        "environment": "PHOTOSHOP_EXE",
        "adapter_kind": "com",
        "capabilities": ("COM 只读握手", "受确认的沙箱任务"),
    },
    {
        "id": "illustrator",
        "name": "Illustrator",
        "mark": "Ai",
        "executables": ("Illustrator.exe",),
        "environment": "ILLUSTRATOR_EXE",
        "adapter_kind": "com",
        "capabilities": ("COM 只读握手", "受确认的矢量任务"),
    },
    {
        "id": "comfyui",
        "name": "ComfyUI",
        "mark": "Co",
        "executables": ("ComfyUI.exe",),
        "environment": "COMFY_ROOT",
        "adapter_kind": "http",
        "capabilities": ("回环 HTTP 健康检查", "受确认的工作流任务"),
    },
    {
        "id": "autocad",
        "name": "AutoCAD / CAD",
        "mark": "CAD",
        "executables": ("acad.exe",),
        "environment": "AUTOCAD_EXE",
        "adapter_kind": "com",
        "capabilities": ("COM 只读握手", "受确认的 CAD 任务"),
    },
    {
        "id": "blender",
        "name": "Blender",
        "mark": "Bl",
        "executables": ("blender.exe",),
        "environment": "BLENDER_EXE",
        "adapter_kind": "process",
        "capabilities": ("进程会话检测", "本机任务路由"),
    },
    {
        "id": "jianying_capcut",
        "name": "剪映 / CapCut",
        "mark": "剪",
        "executables": ("JianyingPro.exe", "CapCut.exe"),
        "environment": "JIANYING_EXE",
        "adapter_kind": "process",
        "capabilities": ("进程会话检测", "本机任务路由"),
    },
)
APPLICATION_BY_ID = {str(item["id"]): item for item in APPLICATION_DEFINITIONS}
COM_PROG_IDS = {
    "photoshop": "Photoshop.Application",
    "illustrator": "Illustrator.Application",
    "autocad": "AutoCAD.Application",
}


class ConnectionSetupError(ValueError):
    def __init__(self, code: str, message: str, next_steps: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.next_steps = next_steps or []


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utc_now().isoformat(timespec="seconds")


def _read_small_json(path: Path) -> JsonObject | None:
    try:
        if not path.is_file() or path.stat().st_size > 16 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_json(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex[:8]}.tmp")
    temporary.write_text(
        json.dumps(sanitize(payload), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def _challenge_path(paths: AppDataPaths) -> Path:
    return paths.cache / "desktop_pairing_challenge.json"


def _receipt_path(paths: AppDataPaths) -> Path:
    return paths.cache / "desktop_pairing_receipt.json"


def _application_pairings_path(paths: AppDataPaths) -> Path:
    return paths.cache / "application_pairings.json"


def _parse_created_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def pair_desktop_session(
    paths: AppDataPaths | None = None,
    *,
    pairing_code: str,
    confirm_pairing: bool,
    dry_run: bool = False,
) -> JsonObject:
    """Write a receipt for the active desktop challenge without reading Codex credentials."""

    if dry_run:
        return {
            "ok": True,
            "paired": False,
            "dry_run": True,
            "message": "配对计划已验证，尚未写入当前桌面会话回执。",
            "next_steps": ["核对连接中心配对码后，设置 dry_run=false 和 confirm_pairing=true。"],
        }
    if not confirm_pairing:
        return {
            "ok": False,
            "error": {
                "code": "confirmation_required",
                "message": "关联当前 StarBridge 桌面会话前需要明确确认。",
                "next_steps": ["确认连接中心显示的配对码，再设置 confirm_pairing=true。"],
            },
        }
    normalized = str(pairing_code or "").strip().upper()
    if not re.fullmatch(r"[A-Z2-9]{8}", normalized):
        return {
            "ok": False,
            "error": {
                "code": "pairing_code_invalid",
                "message": "配对码格式无效。",
                "next_steps": ["回到 StarBridge 连接中心复制当前 8 位配对码。"],
            },
        }

    app_paths = paths or resolve_app_data_paths()
    challenge = _read_small_json(_challenge_path(app_paths))
    if not challenge or challenge.get("schema_version") != PAIRING_VERSION:
        return {
            "ok": False,
            "error": {
                "code": "desktop_session_not_found",
                "message": "没有找到正在等待关联的 StarBridge 桌面会话。",
                "next_steps": ["打开 StarBridge 的连接中心后重试。"],
            },
        }
    created_at = _parse_created_at(challenge.get("created_at"))
    if created_at is None or (_utc_now() - created_at).total_seconds() > PAIRING_TTL_SECONDS:
        return {
            "ok": False,
            "error": {
                "code": "pairing_code_expired",
                "message": "该配对码已过期。",
                "next_steps": ["在 StarBridge 连接中心点击“重新生成配对码”。"],
            },
        }
    expected = challenge.get("pairing_code")
    session_id = challenge.get("session_id")
    if not isinstance(expected, str) or not secrets.compare_digest(normalized, expected):
        return {
            "ok": False,
            "error": {
                "code": "pairing_code_invalid",
                "message": "配对码与当前 StarBridge Desktop 会话不匹配。",
                "next_steps": ["复制连接中心当前显示的配对码，不要使用旧任务中的配对码。"],
            },
        }
    if not isinstance(session_id, str) or len(session_id) < 24:
        return {
            "ok": False,
            "error": {"code": "desktop_session_invalid", "message": "桌面会话挑战无效。"},
        }

    _atomic_json(
        _receipt_path(app_paths),
        {
            "schema_version": PAIRING_VERSION,
            "session_id": session_id,
            "paired_by": "codex_mcp",
            "confirmed_at": _iso_now(),
        },
    )
    return {
        "ok": True,
        "paired": True,
        "dry_run": False,
        "message": "Codex 已与当前 StarBridge 桌面会话关联。",
        "drawing_enabled": True,
        "next_steps": ["返回 StarBridge；连接中心会自动刷新并开放制图入口。"],
    }


def _default_process_probe() -> set[str]:
    if os.name != "nt":
        return set()
    completed = subprocess.run(
        ["tasklist.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=4,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if completed.returncode != 0:
        return set()
    names: set[str] = set()
    for row in csv.reader(completed.stdout.splitlines()):
        if row:
            names.add(Path(row[0]).name.lower())
    return names


def _registry_app_path_exists(executable_names: Iterable[str]) -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
    except ImportError:
        return False
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = (0, getattr(winreg, "KEY_WOW64_64KEY", 0), getattr(winreg, "KEY_WOW64_32KEY", 0))
    for executable in executable_names:
        key_name = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}"
        for root in roots:
            for view in views:
                try:
                    with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ | view):
                        return True
                except OSError:
                    continue
    return False


def _default_install_probe(executable_names: Iterable[str], environment_name: str | None) -> bool:
    if environment_name:
        configured = os.environ.get(environment_name)
        if configured and Path(configured).expanduser().exists():
            return True
    names = tuple(executable_names)
    return any(shutil.which(name) for name in names) or _registry_app_path_exists(names)


def _default_codex_app_probe() -> bool:
    if shutil.which("codex"):
        return True
    if os.name != "nt":
        return False
    try:
        import winreg

        for root, key_name in (
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\codex"),
            (winreg.HKEY_CLASSES_ROOT, "codex"),
        ):
            try:
                with winreg.OpenKey(root, key_name, 0, winreg.KEY_READ):
                    return True
            except OSError:
                continue
    except ImportError:
        return False
    return False


def _default_comfy_probe() -> bool:
    base_url = os.environ.get("STARBRIDGE_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    try:
        request = urllib.request.Request(
            f"{base_url}/system_stats", headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _default_bridge_probe(application_id: str) -> bool:
    """Perform a fixed, read-only COM handshake for an already running application."""

    prog_id = COM_PROG_IDS.get(application_id)
    if os.name != "nt" or prog_id is None:
        return False
    script = (
        "$ErrorActionPreference='Stop';"
        f"$app=[Runtime.InteropServices.Marshal]::GetActiveObject('{prog_id}');"
        "if($null -eq $app){exit 1};exit 0"
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            capture_output=True,
            timeout=4,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _connector_command() -> tuple[Path, list[str], Path | None]:
    command = Path(sys.executable).resolve(strict=False)
    if getattr(sys, "frozen", False):
        return command, ["--mcp"], None
    repository_root = Path(__file__).resolve().parents[2]
    return command, ["-m", "starbridge_mcp.mcp_server"], repository_root


class DesktopConnectionManager:
    def __init__(
        self,
        paths: AppDataPaths,
        *,
        codex_app_probe: Callable[[], bool] | None = None,
        process_probe: ProcessProbe | None = None,
        install_probe: InstallProbe | None = None,
        comfy_probe: Callable[[], bool] | None = None,
        bridge_probe: BridgeProbe | None = None,
    ) -> None:
        self.paths = paths
        self._codex_app_probe = codex_app_probe or _default_codex_app_probe
        self._process_probe = process_probe or _default_process_probe
        self._install_probe = install_probe or _default_install_probe
        self._comfy_probe = comfy_probe or _default_comfy_probe
        self._bridge_probe = bridge_probe or _default_bridge_probe
        self._bridge_cache: dict[str, tuple[datetime, bool]] = {}
        self._session_id = "desktop-" + uuid4().hex
        self._pairing_code = ""
        self._challenge_created_at = _utc_now()
        self.reset_pairing()

    def reset_pairing(self) -> JsonObject:
        self._session_id = "desktop-" + uuid4().hex
        self._pairing_code = "".join(
            secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH)
        )
        self._challenge_created_at = _utc_now()
        _atomic_json(
            _challenge_path(self.paths),
            {
                "schema_version": PAIRING_VERSION,
                "session_id": self._session_id,
                "pairing_code": self._pairing_code,
                "created_at": self._challenge_created_at.isoformat(timespec="seconds"),
            },
        )
        return {"reset": True, "pairing_code": self._pairing_code}

    def _rotate_expired_challenge(self) -> None:
        if (_utc_now() - self._challenge_created_at).total_seconds() > PAIRING_TTL_SECONDS:
            self.reset_pairing()

    def _paired(self) -> bool:
        receipt = _read_small_json(_receipt_path(self.paths))
        return bool(
            receipt
            and receipt.get("schema_version") == PAIRING_VERSION
            and receipt.get("session_id") == self._session_id
            and receipt.get("paired_by") == "codex_mcp"
        )

    def drawing_enabled(self) -> bool:
        self._rotate_expired_challenge()
        return self._paired()

    @staticmethod
    def _connector_configured() -> bool:
        config = _codex_home() / "config.toml"
        try:
            if not config.is_file() or config.stat().st_size > MAX_CONFIG_BYTES:
                return False
            contents = config.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
        return CONNECTOR_BEGIN in contents and CONNECTOR_END in contents

    def install_codex_connector(self, *, confirm_install: bool) -> JsonObject:
        if not confirm_install:
            raise ConnectionSetupError(
                "confirmation_required",
                "安装 Codex 本地连接器前需要明确确认。",
                ["确认后重试；StarBridge 只修改自己的托管配置区块。"],
            )
        command, arguments, cwd = _connector_command()
        if not command.is_file():
            raise ConnectionSetupError(
                "connector_executable_missing",
                "没有找到 StarBridge 本地连接器程序。",
                ["重新安装 StarBridge Desktop 后重试。"],
            )
        codex_home = _codex_home()
        config = codex_home / "config.toml"
        codex_home.mkdir(parents=True, exist_ok=True)
        try:
            if config.exists() and config.stat().st_size > MAX_CONFIG_BYTES:
                raise ConnectionSetupError(
                    "codex_config_too_large",
                    "Codex 配置文件过大，StarBridge 未修改它。",
                    ["请手动检查 config.toml 后重试。"],
                )
            contents = config.read_text(encoding="utf-8") if config.exists() else ""
        except UnicodeDecodeError as error:
            raise ConnectionSetupError(
                "codex_config_invalid_encoding", "Codex 配置不是有效的 UTF-8，未做修改。"
            ) from error
        except OSError as error:
            raise ConnectionSetupError(
                "codex_config_unavailable", "无法读取 Codex 配置，未做修改。"
            ) from error

        managed_pattern = re.compile(
            rf"(?ms)^\s*{re.escape(CONNECTOR_BEGIN)}.*?{re.escape(CONNECTOR_END)}\s*"
        )
        preserved = managed_pattern.sub("\n", contents).rstrip()
        if re.search(r"(?m)^\s*\[mcp_servers\.starbridge-desktop(?:\.env)?\]\s*$", preserved):
            raise ConnectionSetupError(
                "connector_config_conflict",
                "Codex 配置中已有非托管的 starbridge-desktop 条目，StarBridge 未覆盖它。",
                ["请先在 config.toml 中重命名或删除冲突条目。"],
            )

        block_lines = [
            CONNECTOR_BEGIN,
            "[mcp_servers.starbridge-desktop]",
            f"command = {_toml_string(command)}",
            "args = [" + ", ".join(_toml_string(item) for item in arguments) + "]",
        ]
        if cwd is not None:
            block_lines.append(f"cwd = {_toml_string(cwd)}")
        block_lines.extend(
            [
                "",
                "[mcp_servers.starbridge-desktop.env]",
                f"STARBRIDGE_APP_DATA_DIR = {_toml_string(self.paths.root)}",
                'STARBRIDGE_PHOTOSHOP_SAFE_ONLY = "1"',
                'STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN = "1"',
                'STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE = "0"',
                CONNECTOR_END,
            ]
        )
        updated = ((preserved + "\n\n") if preserved else "") + "\n".join(block_lines) + "\n"
        temporary = config.with_name(f".{config.name}.{uuid4().hex[:8]}.tmp")
        try:
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, config)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ConnectionSetupError(
                "codex_config_write_failed", "无法更新 Codex 配置，原配置未被替换。"
            ) from error

        return {
            "installed": True,
            "connector": "starbridge-desktop",
            "message": "Codex 本地连接器已安装或更新。",
            "restart_required": True,
            "next_steps": ["打开一个新的 Codex 任务，再发送 StarBridge 预填的配对指令。"],
        }

    @staticmethod
    def _application_definition(application_id: str) -> JsonObject:
        definition = APPLICATION_BY_ID.get(str(application_id or "").strip().lower())
        if definition is None:
            raise ConnectionSetupError(
                "application_not_supported",
                "该软件不在 StarBridge 固定配对清单中。",
                ["在连接中心选择 Photoshop、Illustrator、ComfyUI、AutoCAD、Blender 或剪映。"],
            )
        return definition

    def _application_receipts(self) -> JsonObject:
        payload = _read_small_json(_application_pairings_path(self.paths))
        if (
            not payload
            or payload.get("schema_version") != APPLICATION_PAIRING_VERSION
            or payload.get("session_id") != self._session_id
        ):
            return {}
        applications = payload.get("applications")
        return applications if isinstance(applications, dict) else {}

    def _write_application_receipts(self, applications: JsonObject) -> None:
        _atomic_json(
            _application_pairings_path(self.paths),
            {
                "schema_version": APPLICATION_PAIRING_VERSION,
                "session_id": self._session_id,
                "applications": applications,
            },
        )

    def _probe_application_bridge(self, application_id: str, *, refresh: bool = False) -> bool:
        if application_id == "comfyui":
            try:
                return bool(self._comfy_probe())
            except (OSError, urllib.error.URLError):
                return False
        definition = self._application_definition(application_id)
        if definition["adapter_kind"] != "com":
            return False
        cached = self._bridge_cache.get(application_id)
        if cached and not refresh and (_utc_now() - cached[0]).total_seconds() < 3:
            return cached[1]
        try:
            ready = bool(self._bridge_probe(application_id))
        except (OSError, subprocess.SubprocessError):
            ready = False
        self._bridge_cache[application_id] = (_utc_now(), ready)
        return ready

    def _application_statuses(self) -> list[JsonObject]:
        try:
            processes = self._process_probe()
            process_probe_failed = False
        except (OSError, subprocess.SubprocessError):
            processes = set()
            process_probe_failed = True
        normalized_processes = {item.lower() for item in processes}
        receipts = self._application_receipts()
        results: list[JsonObject] = []

        for definition in APPLICATION_DEFINITIONS:
            application_id = str(definition["id"])
            executable_names = tuple(str(item) for item in definition["executables"])
            environment_name = str(definition["environment"])
            process_running = any(item.lower() in normalized_processes for item in executable_names)
            bridge_ready = False
            if application_id == "comfyui":
                bridge_ready = self._probe_application_bridge(application_id)
            running = process_running or bridge_ready
            try:
                installed = running or self._install_probe(executable_names, environment_name)
                if application_id == "comfyui" and not installed:
                    installed = self._install_probe(("ComfyUI.exe",), "COMFYUI_PATH")
            except OSError:
                installed = running

            receipt = receipts.get(application_id)
            has_receipt = isinstance(receipt, dict)
            if has_receipt and running and application_id != "comfyui":
                bridge_ready = self._probe_application_bridge(application_id)
            active_pairing = has_receipt and running
            last_connected_at = receipt.get("confirmed_at") if isinstance(receipt, dict) else None
            adapter_kind = str(definition["adapter_kind"])
            control_level = "verified_bridge" if bridge_ready else "session_detection"

            if process_probe_failed and not installed and not bridge_ready:
                state = "unavailable"
                pairing_state = "unavailable"
                message = "本轮进程探测未完成，可安全地重新检测。"
                next_steps = ["点击“重新检测全部”。"]
            elif has_receipt and not running:
                state = "installed" if installed else "not_installed"
                pairing_state = "reconnect_required"
                message = "软件已停止或本地接口没有响应；配对暂时失效。"
                next_steps = ["手动打开软件，再点击“重新连接”。"]
            elif active_pairing and bridge_ready:
                state = "bridge_ready"
                pairing_state = "paired"
                message = "当前软件会话已配对，只读桥接握手成功。"
                next_steps = ["可从 Codex 发起任务；实际写入仍需逐项确认。"]
            elif active_pairing:
                state = "running"
                pairing_state = "paired_limited"
                message = "当前软件会话已配对；目前仅支持检测和任务路由。"
                next_steps = ["安装并验证对应控制适配器后，重新连接可升级为桥接可用。"]
            elif running:
                state = "running"
                pairing_state = "ready_to_pair"
                message = "软件正在运行，等待与当前 StarBridge 会话配对。"
                next_steps = ["确认软件中没有未保存的敏感任务后，点击“开始配对”。"]
            elif installed:
                state = "installed"
                pairing_state = "open_required"
                message = "已找到安装线索；手动打开软件后即可配对。"
                next_steps = ["打开软件，再返回连接中心重新检测。"]
            else:
                state = "not_installed"
                pairing_state = "not_available"
                message = "没有找到安装或运行线索。"
                next_steps = ["安装软件，或通过受支持的环境变量提供明确安装线索。"]

            result: JsonObject = {
                "id": application_id,
                "name": definition["name"],
                "mark": definition["mark"],
                "state": state,
                "installed": installed,
                "running": running,
                "bridge_available": bridge_ready,
                "managed": False,
                "message": message,
                "pairing_state": pairing_state,
                "paired": active_pairing,
                "adapter_kind": adapter_kind,
                "control_level": control_level,
                "capabilities": list(definition["capabilities"]),
                "next_steps": next_steps,
            }
            if isinstance(last_connected_at, str):
                result["last_connected_at"] = last_connected_at
            results.append(result)
        return results

    def _application_status(self, application_id: str) -> JsonObject:
        self._application_definition(application_id)
        return next(item for item in self._application_statuses() if item["id"] == application_id)

    def pair_application(self, application_id: str, *, confirm_pairing: bool) -> JsonObject:
        application_id = str(self._application_definition(application_id)["id"])
        if not confirm_pairing:
            raise ConnectionSetupError(
                "confirmation_required",
                "配对外部创意软件前需要明确确认。",
                ["确认当前软件会话可以交给 StarBridge 检测后重试。"],
            )
        if not self.drawing_enabled():
            raise ConnectionSetupError(
                "codex_association_required",
                "请先关联当前 Codex 会话，再配对创意软件。",
                ["先在连接中心完成 Codex 三步配对。"],
            )
        status = self._application_status(application_id)
        if not status["installed"]:
            raise ConnectionSetupError(
                "application_not_found",
                "没有找到该软件，未创建配对。",
                ["安装软件后重新检测。"],
            )
        if not status["running"]:
            raise ConnectionSetupError(
                "application_not_running",
                "该软件尚未运行，未创建配对。",
                ["手动打开软件后重新检测；StarBridge 不会代替用户启动或重启外部软件。"],
            )
        self._probe_application_bridge(application_id, refresh=True)
        receipts = self._application_receipts()
        receipts[application_id] = {
            "confirmed_at": _iso_now(),
            "adapter_kind": self._application_definition(application_id)["adapter_kind"],
        }
        self._write_application_receipts(receipts)
        return self._application_status(application_id)

    def reconnect_application(self, application_id: str, *, confirm_reconnect: bool) -> JsonObject:
        application_id = str(self._application_definition(application_id)["id"])
        if not confirm_reconnect:
            raise ConnectionSetupError(
                "confirmation_required",
                "重新连接外部软件前需要明确确认。",
            )
        if application_id not in self._application_receipts():
            raise ConnectionSetupError(
                "application_not_paired",
                "当前 StarBridge 会话还没有配对该软件。",
                ["软件运行后点击“开始配对”。"],
            )
        return self.pair_application(application_id, confirm_pairing=True)

    def disconnect_application(
        self, application_id: str, *, confirm_disconnect: bool
    ) -> JsonObject:
        application_id = str(self._application_definition(application_id)["id"])
        if not confirm_disconnect:
            raise ConnectionSetupError(
                "confirmation_required",
                "解除软件配对前需要明确确认。",
            )
        receipts = self._application_receipts()
        receipts.pop(application_id, None)
        self._write_application_receipts(receipts)
        self._bridge_cache.pop(application_id, None)
        return self._application_status(application_id)

    def overview(self) -> JsonObject:
        self._rotate_expired_challenge()
        paired = self._paired()
        connector_configured = self._connector_configured()
        try:
            app_available = self._codex_app_probe()
        except OSError:
            app_available = False
        if paired:
            state = "paired"
            message = "Codex 已关联当前桌面会话，制图入口已开放。"
            next_steps = ["可以开始本机制图；写入和导出仍需逐次确认。"]
        elif not app_available:
            state = "not_found"
            message = "没有找到可打开的 Codex 应用或 CLI。"
            next_steps = ["先安装并登录 Codex，再返回连接中心重新检测。"]
        elif not connector_configured:
            state = "connector_required"
            message = "已找到 Codex；需要安装 StarBridge 本地连接器。"
            next_steps = ["确认安装连接器，然后在新的 Codex 任务中完成配对。"]
        else:
            state = "awaiting_pairing"
            message = "连接器已配置，正在等待 Codex 确认当前桌面会话。"
            next_steps = ["打开新的 Codex 任务并发送预填的配对指令。"]
        return sanitize(
            {
                "schema_version": SCHEMA_VERSION,
                "checked_at": _iso_now(),
                "drawing_enabled": paired,
                "codex": {
                    "state": state,
                    "app_available": app_available,
                    "connector_configured": connector_configured,
                    "session_paired": paired,
                    "pairing_code": self._pairing_code,
                    "message": message,
                    "next_steps": next_steps,
                },
                "applications": self._application_statuses(),
                "safety": {
                    "loopback_only": True,
                    "credentials_read": False,
                    "external_apps_force_restarted": False,
                },
            }
        )
