from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any


BRIDGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BRIDGE_ROOT.parents[1]
SCRIPTS = BRIDGE_ROOT / "scripts"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "photoshop_bridge_report"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PRACTICE_ARTIFACT_FILENAMES = {
    "probe_output": "codex_photoshop_probe.png",
    "subject_input": "subject_input_clean.png",
    "subject_cutout_output": "subject_cutout_clean.png",
}


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


def png_chunks(path: Path) -> list[tuple[bytes, bytes]]:
    try:
        with path.open("rb") as file:
            if file.read(8) != PNG_SIGNATURE:
                return []
            chunks = []
            while True:
                length_bytes = file.read(4)
                if len(length_bytes) != 4:
                    break
                length = struct.unpack(">I", length_bytes)[0]
                chunk_type = file.read(4)
                data = file.read(length)
                file.read(4)  # CRC
                if len(chunk_type) != 4 or len(data) != length:
                    break
                chunks.append((chunk_type, data))
                if chunk_type == b"IEND":
                    break
            return chunks
    except OSError:
        return []


def png_header(path: Path) -> dict[str, int] | None:
    for chunk_type, data in png_chunks(path):
        if chunk_type == b"IHDR" and len(data) >= 13:
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", data[:13]
            )
            return {
                "width": width,
                "height": height,
                "bit_depth": bit_depth,
                "color_type": color_type,
                "compression": compression,
                "filter_method": filter_method,
                "interlace": interlace,
            }
    return None


def png_dimensions(path: Path) -> tuple[int, int] | None:
    header = png_header(path)
    if not header:
        return None
    return header["width"], header["height"]


def paeth_predictor(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def unfilter_png_rows(raw: bytes, width: int, height: int, bytes_per_pixel: int) -> list[bytes]:
    stride = width * bytes_per_pixel
    offset = 0
    previous = bytearray(stride)
    rows: list[bytes] = []

    for _ in range(height):
        if offset >= len(raw):
            raise ValueError("PNG scanline data ended early.")
        filter_type = raw[offset]
        offset += 1
        scanline = raw[offset : offset + stride]
        offset += stride
        if len(scanline) != stride:
            raise ValueError("PNG scanline length is incomplete.")

        reconstructed = bytearray(stride)
        for index, value in enumerate(scanline):
            left = reconstructed[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0

            if filter_type == 0:
                reconstructed[index] = value
            elif filter_type == 1:
                reconstructed[index] = (value + left) & 0xFF
            elif filter_type == 2:
                reconstructed[index] = (value + above) & 0xFF
            elif filter_type == 3:
                reconstructed[index] = (value + ((left + above) // 2)) & 0xFF
            elif filter_type == 4:
                reconstructed[index] = (value + paeth_predictor(left, above, upper_left)) & 0xFF
            else:
                raise ValueError(f"Unsupported PNG filter type: {filter_type}")

        rows.append(bytes(reconstructed))
        previous = reconstructed

    return rows


def png_alpha_summary(path: Path) -> dict[str, Any]:
    header = png_header(path)
    if not header:
        return {"supported": False, "error": "not a readable PNG"}

    width = header["width"]
    height = header["height"]
    total_pixels = width * height
    color_type = header["color_type"]
    bit_depth = header["bit_depth"]

    if bit_depth != 8 or header["interlace"] != 0:
        return {
            "supported": False,
            "error": "only 8-bit non-interlaced PNG files are supported",
            "total_pixels": total_pixels,
        }

    if color_type == 2:
        return {
            "supported": True,
            "has_alpha_channel": False,
            "total_pixels": total_pixels,
            "transparent_pixels": 0,
            "translucent_pixels": 0,
            "opaque_pixels": total_pixels,
        }

    if color_type not in {4, 6}:
        return {
            "supported": False,
            "error": f"unsupported PNG color type: {color_type}",
            "total_pixels": total_pixels,
        }

    bytes_per_pixel = 2 if color_type == 4 else 4
    alpha_offset = 1 if color_type == 4 else 3
    idat = b"".join(data for chunk_type, data in png_chunks(path) if chunk_type == b"IDAT")
    if not idat:
        return {"supported": False, "error": "PNG has no IDAT data", "total_pixels": total_pixels}

    try:
        rows = unfilter_png_rows(zlib.decompress(idat), width, height, bytes_per_pixel)
    except (OSError, ValueError, zlib.error) as exc:
        return {"supported": False, "error": str(exc), "total_pixels": total_pixels}

    transparent = 0
    translucent = 0
    opaque = 0
    visible = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y, row in enumerate(rows):
        for x, index in enumerate(range(alpha_offset, len(row), bytes_per_pixel)):
            alpha = row[index]
            if alpha == 0:
                transparent += 1
            elif alpha == 255:
                opaque += 1
            else:
                translucent += 1
            if alpha > 0:
                visible += 1
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    visible_bbox = None
    if visible:
        bbox_width = max_x - min_x + 1
        bbox_height = max_y - min_y + 1
        bbox_area = bbox_width * bbox_height
        visible_bbox = {
            "left": min_x,
            "top": min_y,
            "right": max_x,
            "bottom": max_y,
            "width": bbox_width,
            "height": bbox_height,
            "area": bbox_area,
            "visible_pixels": visible,
            "coverage_ratio": round(visible / total_pixels, 6),
            "bbox_fill_ratio": round(visible / bbox_area, 6),
            "edge_margins": {
                "left": min_x,
                "top": min_y,
                "right": width - 1 - max_x,
                "bottom": height - 1 - max_y,
            },
        }

    return {
        "supported": True,
        "has_alpha_channel": True,
        "total_pixels": total_pixels,
        "transparent_pixels": transparent,
        "translucent_pixels": translucent,
        "opaque_pixels": opaque,
        "visible_bbox": visible_bbox,
    }


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def artifact_info(role: str, path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {
            "role": role,
            "path": None,
            "exists": False,
        }

    path = Path(path_value)
    exists = path.exists()
    info: dict[str, Any] = {
        "role": role,
        "path": str(path),
        "exists": exists,
    }
    if exists:
        info["bytes"] = path.stat().st_size
        info["sha256"] = sha256_file(path)
        dimensions = png_dimensions(path)
        if dimensions:
            info["png_width"], info["png_height"] = dimensions
            info["alpha_summary"] = png_alpha_summary(path)
    return info


def add_expected_practice_paths(practice: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    practice.setdefault("output_dir", str(output_dir))
    for key, filename in PRACTICE_ARTIFACT_FILENAMES.items():
        if not practice.get(key):
            practice[key] = str(output_dir / filename)
    return practice


def collect_artifacts(report: dict[str, Any]) -> list[dict[str, Any]]:
    practice = report.get("practice")
    if not practice:
        return []
    return [
        artifact_info("Photoshop 探针 PNG", practice.get("probe_output")),
        artifact_info("公开测试输入图", practice.get("subject_input")),
        artifact_info("主体抠图 PNG", practice.get("subject_cutout_output")),
    ]


def render_artifact_table(artifacts: list[dict[str, Any]]) -> list[str]:
    if not artifacts:
        return ["本次没有记录图片产物。需要完整闭环时加 `--run-practice`。"]

    rows = [
        "| 产物 | 是否存在 | 大小 | 图片尺寸 | 透明统计 | 主体边界 | SHA256 摘要 | 路径 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in artifacts:
        size = item.get("bytes")
        dimensions = "-"
        if item.get("png_width") and item.get("png_height"):
            dimensions = f"{item['png_width']} x {item['png_height']}"
        alpha = item.get("alpha_summary") or {}
        if alpha.get("supported") and alpha.get("has_alpha_channel"):
            alpha_text = "透明 {transparent} / 半透明 {translucent} / 不透明 {opaque}".format(
                transparent=alpha.get("transparent_pixels", 0),
                translucent=alpha.get("translucent_pixels", 0),
                opaque=alpha.get("opaque_pixels", 0),
            )
            bbox = alpha.get("visible_bbox")
            if bbox:
                margins = bbox.get("edge_margins", {})
                bbox_text = "{width} x {height}，边距 {left}/{top}/{right}/{bottom}，占比 {coverage:.2%}".format(
                    width=bbox.get("width", 0),
                    height=bbox.get("height", 0),
                    left=margins.get("left", 0),
                    top=margins.get("top", 0),
                    right=margins.get("right", 0),
                    bottom=margins.get("bottom", 0),
                    coverage=bbox.get("coverage_ratio", 0),
                )
            else:
                bbox_text = "未发现主体"
        elif alpha.get("supported"):
            alpha_text = "无透明通道"
            bbox_text = "无透明通道"
        elif alpha:
            alpha_text = f"未检查：{alpha.get('error')}"
            bbox_text = "未检查"
        else:
            alpha_text = "-"
            bbox_text = "-"
        sha = item.get("sha256") or ""
        rows.append(
            "| {role} | {exists} | {size} | {dimensions} | {alpha_text} | {bbox_text} | `{sha}` | `{path}` |".format(
                role=item["role"],
                exists=yes_no(item.get("exists")),
                size=f"{size} bytes" if size is not None else "-",
                dimensions=dimensions,
                alpha_text=alpha_text,
                bbox_text=bbox_text,
                sha=sha[:16],
                path=item.get("path") or "-",
            )
        )
    return rows


def render_markdown(report: dict[str, Any]) -> str:
    diagnose = report.get("diagnose", {})
    document = report.get("document_info", {})
    practice = report.get("practice")
    artifacts = report.get("artifacts", [])
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
            "## 六、产物清单",
            "",
            *render_artifact_table(artifacts),
            "",
            "## 七、安全说明",
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
        report["practice"] = add_expected_practice_paths(
            run_powershell("run_local_practice.ps1", "-OutputDir", str(practice_dir)),
            practice_dir,
        )

    report["artifacts"] = collect_artifacts(report)

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
