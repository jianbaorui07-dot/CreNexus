from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EXTENSIONS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".psd",
    ".dwg",
    ".ai",
    ".blend",
    ".aep",
    ".mp4",
    ".mov",
    ".starbridge-license",
}
FORBIDDEN_TRACKED_PREFIXES = {
    "docs/cad_exact_trace_sync/exports/",
    "examples/unreal_worldforge_agent/",
    "integrations/",
}
TEXT_EXTENSIONS = {".md", ".py", ".ps1", ".json", ".txt", ".yml", ".yaml", ".toml"}
LOCAL_ONLY_DIRS = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".skill-build",
    ".venv",
    ".vscode",
    "__pycache__",
    "docx_render_check",
    "node_modules",
    "output",
    "outputs",
    "reports",
    "scratch",
    "venv",
    "virtual-pet",
    "overtime-analysis-deck",
    "src",
}
LOCAL_ONLY_PREFIXES = {".codex_video_deps", ".codex_video_frames"}
HOME = str(Path.home())
WINDOWS_USER_BACKSLASH = "C:" + r"\\Users\\"
WINDOWS_USER_SLASH = "C:" + "/Users/"
SENSITIVE_PATTERNS = [
    re.compile(re.escape(HOME), re.IGNORECASE),
    re.compile(WINDOWS_USER_BACKSLASH + r"(?!用户名|<USER_HOME>)[^\\\s]+", re.IGNORECASE),
    re.compile(WINDOWS_USER_SLASH + r"(?!用户名|<USER_HOME>)[^/\s]+", re.IGNORECASE),
    re.compile(r"(password|token|cookie|oauth_secret)\s*[:=]\s*['\"]?[^'\"\s]+", re.IGNORECASE),
]


def git_files(root: Path = REPO_ROOT) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [root / line.strip() for line in completed.stdout.splitlines() if line.strip()]


def should_skip_dir(path: Path, root: Path = REPO_ROOT) -> bool:
    name = path.name
    if name in LOCAL_ONLY_DIRS or any(name.startswith(prefix) for prefix in LOCAL_ONLY_PREFIXES):
        return True
    relative = path.relative_to(root).as_posix()
    return relative.endswith("/outputs") or relative.endswith("/reports")


def walk_public_files(root: Path = REPO_ROOT) -> list[Path]:
    files: list[Path] = []
    for directory, dir_names, file_names in os.walk(root):
        dir_path = Path(directory)
        dir_names[:] = [name for name in dir_names if not should_skip_dir(dir_path / name, root)]
        for file_name in file_names:
            files.append(dir_path / file_name)
    return sorted(files)


def repository_files(root: Path = REPO_ROOT) -> list[Path]:
    if shutil.which("git"):
        try:
            return git_files(root)
        except (subprocess.SubprocessError, OSError):
            pass
    return walk_public_files(root)


def is_allowed_example(path: Path) -> bool:
    return path.name.endswith(".example.json")


def find_failures(files: list[Path], root: Path = REPO_ROOT) -> list[str]:
    failures: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if any(relative.startswith(prefix) for prefix in FORBIDDEN_TRACKED_PREFIXES):
            failures.append(f"local-only path is tracked: {relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS and not is_allowed_example(path):
            failures.append(f"forbidden tracked file type: {relative}")
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"sensitive pattern in {relative}: {pattern.pattern}")
    return failures


def main() -> None:
    failures = find_failures(repository_files())

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)

    print("security check passed")


if __name__ == "__main__":
    main()
