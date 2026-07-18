from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = frozenset(
    {
        ".css",
        ".html",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".mjs",
        ".ps1",
        ".py",
        ".rs",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)
TEXT_FILENAMES = frozenset({"VERSION", "LICENSE", ".gitignore", ".gitattributes"})
MOJIBAKE_MARKERS = (
    "鍥" + "剧墖",
    "绛" + "夊緟",
    "寤" + "虹珛",
    "浠" + "诲姟",
    "鐭" + "㈤噺",
    "杩" + "愯",
    "澶" + "辫触",
    "鎴" + "愬姛",
    "妫" + "€娴",
)


def repository_text_files(repo_root: Path = REPO_ROOT) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    names = completed.stdout.decode("utf-8").split("\0")
    return [
        repo_root / name
        for name in names
        if name
        and (
            (repo_root / name).suffix.lower() in TEXT_SUFFIXES or Path(name).name in TEXT_FILENAMES
        )
    ]


def inspect_text_file(path: Path, *, display_name: str | None = None) -> list[str]:
    label = display_name or path.name
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        return [f"{label}: 不是有效 UTF-8（字节位置 {exc.start}）"]
    issues: list[str] = []
    if "\ufffd" in text:
        issues.append(f"{label}: 包含 Unicode 替换字符 U+FFFD")
    for marker in MOJIBAKE_MARKERS:
        if marker in text:
            issues.append(f"{label}: 包含疑似 UTF-8/GBK 误解码片段 {marker!r}")
    return issues


def check_text_encoding(repo_root: Path = REPO_ROOT) -> list[str]:
    issues: list[str] = []
    for path in repository_text_files(repo_root):
        if path.is_file():
            issues.extend(
                inspect_text_file(path, display_name=path.relative_to(repo_root).as_posix())
            )
    return issues


def main() -> int:
    issues = check_text_encoding()
    if issues:
        print("text encoding check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("text encoding check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
