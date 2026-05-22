from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


BRIDGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BRIDGE_ROOT.parents[1]
SCRIPTS = BRIDGE_ROOT / "scripts"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "photoshop_bridge_report"


def run_powershell(script_name: str, *args: str) -> dict[str, Any]:
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPTS / script_name),
        *args,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return {
            "ok": False,
            "script": script_name,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "script": script_name,
            "error": f"JSON parse failed: {exc}",
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    payload.setdefault("ok", True)
    payload["script"] = script_name
    return payload


def yes_no(value: Any) -> str:
    return "是" if bool(value) else "否"


def status_text(report: dict[str, Any]) -> str:
    diagnose = report.get("diagnose", {})
    practice = report.get("practice")
    if practice and practice.get("ok"):
        return "已完成 Photoshop 本机实操"
    if diagnose.get("status") == "ready":
        return "Photoshop COM 已就绪"
    if diagnose.get("status") == "com_registered":
        return "Photoshop COM 已注册，建议继续运行 -ProbeCom"
    return "需要继续配置 Photoshop"


def render_markdown(report: dict[str, Any]) -> str:
    diagnose = report.get("diagnose", {})
    document = report.get("document_info", {})
    practice = report.get("practice")
    com_probe = diagnose.get("com_probe") or {}
    running = diagnose.get("running_processes") or []

    lines = [
        "# Photoshop 本机接入报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 总体状态：{status_text(report)}",
        f"- 报告目录：`{report['output_dir']}`",
        "",
        "## 一、环境诊断",
        "",
        f"- COM 注册：{yes_no(diagnose.get('com_registered'))}",
        f"- CLSID 注册：{yes_no(diagnose.get('clsid_registered'))}",
        f"- `PHOTOSHOP_EXE` 已配置：{yes_no(diagnose.get('env_photoshop_exe'))}",
        f"- `PHOTOSHOP_EXE` 路径存在：{yes_no(diagnose.get('env_photoshop_exe_exists'))}",
        f"- 诊断状态：`{diagnose.get('status')}`",
        f"- 下一步建议：{diagnose.get('next_step')}",
        "",
        "## 二、COM 探测",
        "",
        f"- COM 探测成功：{yes_no(com_probe.get('ok'))}",
        f"- Photoshop 版本：{com_probe.get('version') or document.get('photoshop_version')}",
        f"- 当前文档数量：{com_probe.get('documents') or document.get('documents')}",
        "",
        "## 三、当前进程",
        "",
    ]

    if running:
        lines.extend(["| PID | 路径 | 窗口标题 |", "| --- | --- | --- |"])
        for item in running:
            lines.append(f"| {item.get('id')} | `{item.get('path')}` | {item.get('title') or ''} |")
    else:
        lines.append("未发现正在运行的 Photoshop 进程。")

    lines.extend(
        [
            "",
            "## 四、当前文档",
            "",
            f"- 读取成功：{yes_no(document.get('ok'))}",
            f"- 文档名称：{document.get('active_document') or '无活动文档'}",
            f"- 尺寸：{document.get('width') or '-'} x {document.get('height') or '-'}",
            f"- 模式：{document.get('mode') or '-'}",
            f"- 图层数量：{document.get('layers') or '-'}",
            "",
            "## 五、一键实操",
            "",
        ]
    )

    if practice:
        lines.extend(
            [
                f"- 实操成功：{yes_no(practice.get('ok'))}",
                f"- 探针输出：`{practice.get('probe_output')}`",
                f"- 测试输入图：`{practice.get('subject_input')}`",
                f"- 抠图方法：{practice.get('subject_cutout_method')}",
                f"- 抠图输出：`{practice.get('subject_cutout_output')}`",
            ]
        )
    else:
        lines.append("本次未运行一键实操。需要完整闭环时加 `--run-practice`。")

    lines.extend(
        [
            "",
            "## 六、安全说明",
            "",
            "- 本报告和生成图片默认写入 `output/`，不会提交到 GitHub。",
            "- 不记录账号、授权、Cookie、token、客户图片或 PSD 私有工程。",
            "- 如果要接入真实素材，请把输入和输出都放在本机私有目录。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Photoshop 本机接入中文报告。")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="报告输出目录。")
    parser.add_argument("--run-practice", action="store_true", help="同时运行一键实操并记录输出。")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "diagnose": run_powershell("diagnose_local.ps1", "-ProbeCom"),
        "document_info": run_powershell("document_info.ps1"),
    }

    if args.run_practice:
        practice_dir = output_dir / "practice"
        report["practice"] = run_powershell("run_local_practice.ps1", "-OutputDir", str(practice_dir))

    json_path = output_dir / "photoshop_bridge_report.json"
    md_path = output_dir / "photoshop_bridge_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": bool(report["diagnose"].get("ok")),
                "status": status_text(report),
                "json": str(json_path),
                "markdown": str(md_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if not report["diagnose"].get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ is required.")
    main()
