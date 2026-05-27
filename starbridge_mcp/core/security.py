from __future__ import annotations

import re
from pathlib import Path
from typing import Any


SENSITIVE_FILE_EXTENSIONS = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".psd",
    ".ai",
    ".ait",
    ".dwg",
    ".dxf",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".prproj",
    ".aep",
    ".aepx",
}
SENSITIVE_FILENAMES = {"draft_content.json", "draft_info.json"}
PRIVATE_PATH_PARTS = {"appdata", "desktop", "documents"}
SENSITIVE_KEYWORDS = (
    "password",
    "token",
    "cookie",
    "oauth",
    "secret",
    "api_key",
    "apikey",
    "authorization",
)


def _safe_tail(parts: list[str], separator: str) -> str:
    cleaned = [("<REDACTED>" if part.lower() in PRIVATE_PATH_PARTS else part) for part in parts if part]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return separator.join(cleaned)


REDACTION_PATTERNS = [
    (re.compile(r"(?i)(password|token|cookie|oauth_secret|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;}]+"), r"\1=<REDACTED>"),
]


def sanitize_path(value: str) -> str:
    redacted = value

    def replace_windows_user(match: re.Match[str]) -> str:
        tail = _safe_tail(re.split(r"[\\/]+", match.group("tail") or ""), "\\")
        return "<USER_HOME>" + (f"\\{tail}" if tail else "")

    def replace_unix_user(match: re.Match[str]) -> str:
        tail = _safe_tail((match.group("tail") or "").split("/"), "/")
        return "<USER_HOME>" + (f"/{tail}" if tail else "")

    def replace_drive_path(match: re.Match[str]) -> str:
        parts = re.split(r"[\\/]+", match.group(0))
        filename = parts[-1] if parts else ""
        return "<REDACTED>" + (f"\\{filename}" if filename else "")

    home = str(Path.home())
    if home:
        home_pattern = re.compile(re.escape(home) + r"(?P<tail>(?:[\\/][^\s\"'<>，）)]+)*)", re.IGNORECASE)
        redacted = home_pattern.sub(lambda match: replace_windows_user(match) if "\\" in match.group(0) else replace_unix_user(match), redacted)

    redacted = re.sub(
        "C:" + r"[\\/]Users[\\/][^\\/\s\"'<>，）)]+(?P<tail>(?:[\\/][^\s\"'<>，）)]+)*)",
        replace_windows_user,
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"/Users/[^/\s\"'<>，）)]+(?P<tail>(?:/[^\s\"'<>，）)]+)*)",
        replace_unix_user,
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"/home/[^/\s\"'<>，）)]+(?P<tail>(?:/[^\s\"'<>，）)]+)*)",
        replace_unix_user,
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(?i)\b[A-Z]:[\\/][^\s\"'<>，）)]+(?:[\\/][^\s\"'<>，）)]+)*",
        replace_drive_path,
        redacted,
    )
    for private_part in PRIVATE_PATH_PARTS:
        redacted = re.sub(rf"(?i)([\\/]){re.escape(private_part)}(?=([\\/])|$)", r"\1<REDACTED>", redacted)
    for filename in SENSITIVE_FILENAMES:
        redacted = re.sub(re.escape(filename), "<SENSITIVE_DRAFT_FILE>", redacted, flags=re.IGNORECASE)
    for extension in SENSITIVE_FILE_EXTENSIONS:
        escaped = re.escape(extension.lstrip("."))
        redacted = re.sub(
            rf"(?i)([A-Za-z]:)?[^\s\"'<>|]+\.{escaped}\b",
            "<SENSITIVE_FILE>",
            redacted,
        )
    return redacted


def sanitize_text(value: str) -> str:
    redacted = sanitize_path(value)
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    return redacted


def redact_text(value: str) -> str:
    return sanitize_text(value)


def sanitize_details(value: Any) -> Any:
    return sanitize(value)


def sanitize_result(result: Any) -> Any:
    return sanitize(value=result)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(keyword in key_text.lower() for keyword in SENSITIVE_KEYWORDS):
                sanitized[key_text] = "<REDACTED>"
            else:
                sanitized[key_text] = sanitize(item)
        return sanitized
    return value


def contains_sensitive_text(value: Any) -> bool:
    text = str(value)
    if str(Path.home()) and str(Path.home()) in text:
        return True
    if re.search(r"C:\\Users\\(?!用户名|<USER_HOME>)[^\\\s]+", text, re.IGNORECASE):
        return True
    if re.search("C:" + r"/Users/(?!用户名|<USER_HOME>)[^/\s]+", text, re.IGNORECASE):
        return True
    if re.search(r"/Users/(?!<USER_HOME>)[^/\s]+", text, re.IGNORECASE):
        return True
    if re.search(r"/home/(?!<USER_HOME>)[^/\s]+", text, re.IGNORECASE):
        return True
    if re.search(r"(?i)\b[A-Z]:[\\/][^\s\"'<>]+", text):
        return True
    if any(part in text.lower() for part in PRIVATE_PATH_PARTS):
        return True
    if re.search(r"(?i)(password|token|cookie|oauth_secret|api[_-]?key)\s*[:=]\s*[^<\s]+", text):
        return True
    lowered = text.lower()
    if any(filename in lowered for filename in SENSITIVE_FILENAMES):
        return True
    for extension in SENSITIVE_FILE_EXTENSIONS:
        escaped = re.escape(extension.lstrip("."))
        if re.search(rf"(?i)([A-Za-z]:)?[^\s\"'<>|]+\.{escaped}\b", text):
            return True
    return False
