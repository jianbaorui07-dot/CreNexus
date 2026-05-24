from __future__ import annotations

import re
import subprocess
import sys
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
    ".aep",
    ".mp4",
    ".mov",
}
TEXT_EXTENSIONS = {".md", ".py", ".ps1", ".json", ".txt", ".yml", ".yaml", ".toml"}
HOME = str(Path.home())
WINDOWS_USERS_BACKSLASH = "C:" + r"\\Users\\"
WINDOWS_USERS_SLASH = "C:" + r"/Users/"
SENSITIVE_PATTERNS = [
    re.compile(re.escape(HOME), re.IGNORECASE),
    re.compile(WINDOWS_USERS_BACKSLASH + r"(?!用户名|<USER_HOME>)[^\\\s]+", re.IGNORECASE),
    re.compile(WINDOWS_USERS_SLASH + r"(?!用户名|<USER_HOME>)[^/\s]+", re.IGNORECASE),
    re.compile(r"(password|token|cookie|oauth_secret)\s*[:=]\s*['\"]?[^'\"\s]+", re.IGNORECASE),
]


def git_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / line.strip() for line in completed.stdout.splitlines() if line.strip()]


def is_allowed_example(path: Path) -> bool:
    return path.name.endswith(".example.json")


def main() -> None:
    failures: list[str] = []
    for path in git_files():
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS and not is_allowed_example(path):
            failures.append(f"forbidden tracked file type: {path.relative_to(REPO_ROOT)}")
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                failures.append(f"sensitive pattern in {path.relative_to(REPO_ROOT)}: {pattern.pattern}")

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)

    print("security check passed")


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("建议使用 Python 3.10 或更新版本运行本脚本。")
    main()
