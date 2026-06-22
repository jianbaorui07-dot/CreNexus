from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import bridge_capability_matrix
import security_check

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
REQUIRED_BRIDGE_FIELDS = {
    "bridge_id",
    "display_name",
    "maturity",
    "platforms",
    "local_dependency",
    "required_env",
    "probe_supported",
    "write_supported",
    "safe_report_supported",
    "last_verified",
    "known_risks",
    "next_steps",
}
REQUIRED_REPORT_FIELDS = {"bridge_id", "ok", "detected", "errors", "warnings", "safe_to_commit"}
VALID_MATURITY = {"stable", "prototype", "planned", "research", "deprecated"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def make_result(
    check_id: str, status: str, message: str, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "message": message,
        "data": data or {},
    }


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def check_security() -> dict[str, Any]:
    failures = security_check.find_failures(security_check.repository_files(REPO_ROOT), REPO_ROOT)
    if failures:
        return make_result(
            "security",
            "fail",
            "发现不能公开提交的文件类型、私有路径或敏感字段。",
            {"failures": failures},
        )
    return make_result("security", "pass", "公开安全扫描通过。")


def check_bridge_metadata() -> dict[str, Any]:
    failures: list[str] = []
    status_paths = sorted(EXAMPLES_DIR.glob("*_bridge/bridge_status.json"))
    if not status_paths:
        failures.append("examples/*_bridge/bridge_status.json 未找到。")

    for status_path in status_paths:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{relative(status_path)} JSON 解析失败：{exc}")
            continue

        missing = REQUIRED_BRIDGE_FIELDS - set(data)
        extra = set(data) - REQUIRED_BRIDGE_FIELDS
        if missing:
            failures.append(f"{relative(status_path)} 缺少字段：{sorted(missing)}")
        if extra:
            failures.append(f"{relative(status_path)} 存在未约定字段：{sorted(extra)}")
        if data.get("maturity") not in VALID_MATURITY:
            failures.append(f"{relative(status_path)} maturity 非法：{data.get('maturity')}")
        for field in ("platforms", "local_dependency", "required_env", "known_risks", "next_steps"):
            if not isinstance(data.get(field), list):
                failures.append(f"{relative(status_path)} {field} 必须是列表。")
        for field in ("probe_supported", "write_supported", "safe_report_supported"):
            if not isinstance(data.get(field), bool):
                failures.append(f"{relative(status_path)} {field} 必须是布尔值。")

    if failures:
        return make_result(
            "bridge_metadata", "fail", "桥状态元数据不符合公开契约。", {"failures": failures}
        )
    return make_result(
        "bridge_metadata",
        "pass",
        "桥状态元数据通过。",
        {"files_checked": [relative(path) for path in status_paths]},
    )


def check_sample_reports() -> dict[str, Any]:
    failures: list[str] = []
    sample_paths = sorted(EXAMPLES_DIR.glob("*_bridge/sample_report.example.json"))
    if not sample_paths:
        failures.append("examples/*_bridge/sample_report.example.json 未找到。")

    for sample_path in sample_paths:
        try:
            data = json.loads(sample_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{relative(sample_path)} JSON 解析失败：{exc}")
            continue

        if set(data) != REQUIRED_REPORT_FIELDS:
            failures.append(f"{relative(sample_path)} 字段集合不符合 probe report 契约。")
            continue
        if data.get("safe_to_commit") is not True:
            failures.append(f"{relative(sample_path)} safe_to_commit 必须为 true。")
        if not isinstance(data.get("detected"), dict):
            failures.append(f"{relative(sample_path)} detected 必须是对象。")
        if not isinstance(data.get("errors"), list) or not isinstance(data.get("warnings"), list):
            failures.append(f"{relative(sample_path)} errors/warnings 必须是列表。")

    if failures:
        return make_result(
            "sample_reports", "fail", "probe 示例报告不符合契约。", {"failures": failures}
        )
    return make_result(
        "sample_reports",
        "pass",
        "probe 示例报告通过。",
        {"files_checked": [relative(path) for path in sample_paths]},
    )


def check_bridge_capabilities() -> dict[str, Any]:
    registry = bridge_capability_matrix.load_registry()
    failures = bridge_capability_matrix.validate_registry(registry)
    if failures:
        return make_result(
            "bridge_capabilities", "fail", "桥应用能力矩阵不符合契约。", {"failures": failures}
        )
    return make_result(
        "bridge_capabilities",
        "pass",
        "桥应用能力矩阵通过。",
        {"bridges_checked": [bridge["bridge_id"] for bridge in registry["bridges"]]},
    )


def normalize_link(raw_target: str) -> str | None:
    target = raw_target.strip()
    if not target:
        return None
    if " " in target:
        target = target.split(" ", 1)[0]
    target = target.strip("<>")
    lower = target.lower()
    if (
        lower.startswith(("http://", "https://", "mailto:", "tel:"))
        or lower.startswith("#")
        or "://" in lower
    ):
        return None
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    return unquote(target).replace("\\", "/")


def markdown_local_links(markdown_path: Path) -> list[str]:
    text = markdown_path.read_text(encoding="utf-8")
    return [
        link
        for link in (normalize_link(match.group(1)) for match in LINK_PATTERN.finditer(text))
        if link
    ]


def check_markdown_links() -> dict[str, Any]:
    failures: list[str] = []
    markdown_paths = sorted(REPO_ROOT.glob("*.md")) + sorted((REPO_ROOT / "docs").glob("*.md"))
    for markdown_path in markdown_paths:
        for link in markdown_local_links(markdown_path):
            target_path = (markdown_path.parent / link).resolve()
            try:
                target_path.relative_to(REPO_ROOT)
            except ValueError:
                failures.append(f"{relative(markdown_path)} 链接越过仓库边界：{link}")
                continue
            if not target_path.exists():
                failures.append(f"{relative(markdown_path)} 本地链接不存在：{link}")

    if failures:
        return make_result(
            "markdown_links", "fail", "Markdown 本地链接检查失败。", {"failures": failures}
        )
    return make_result(
        "markdown_links",
        "pass",
        "Markdown 本地链接通过。",
        {"files_checked": [relative(path) for path in markdown_paths]},
    )


def run_checks() -> list[dict[str, Any]]:
    return [
        check_security(),
        check_bridge_metadata(),
        check_sample_reports(),
        check_bridge_capabilities(),
        check_markdown_links(),
    ]


def to_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "| check_id | status | message |",
        "| --- | --- | --- |",
    ]
    for item in results:
        message = str(item["message"]).replace("|", "\\|")
        lines.append(f"| {item['check_id']} | {item['status']} | {message} |")
    return "\n".join(lines) + "\n"


def default_report_dir() -> Path:
    return REPO_ROOT / "output" / "starbridge_preflight"


def write_reports(payload: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "starbridge_preflight_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (report_dir / "starbridge_preflight_report.md").write_text(
        to_markdown(payload["results"]),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="星桥公开发布前体检：安全、桥元数据、probe 报告和文档链接。"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown 表格。")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="把 JSON 和 Markdown 体检报告写到 output/starbridge_preflight/。",
    )
    parser.add_argument(
        "--report-dir",
        default=str(default_report_dir()),
        help="配合 --write-report 指定本地报告目录；应保持在 Git 提交之外。",
    )
    parser.add_argument(
        "--soft-exit", action="store_true", help="发现失败也返回 0，适合只生成报告。"
    )
    args = parser.parse_args()

    results = run_checks()
    payload = {"ok": all(item["status"] == "pass" for item in results), "results": results}
    if args.write_report:
        write_reports(payload, Path(args.report_dir))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(to_markdown(results), end="")

    if not payload["ok"] and not args.soft_exit:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
