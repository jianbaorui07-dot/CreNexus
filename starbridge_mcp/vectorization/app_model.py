from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .engine import RunConfig
from .presets import DEFAULT_MODE, PRESETS, normalize_mode

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class AppInputError(ValueError):
    pass


@dataclass(frozen=True)
class ModeCard:
    key: str
    title: str
    tagline: str
    detail: str


MODE_CARDS = (
    ModeCard(
        key="artisan",
        title="匠心矢量",
        tagline="高级 · 少锚点贝塞尔艺术重建",
        detail="保留关键角点，以更少锚点生成更接近人工绘制的曲线。",
    ),
    ModeCard(
        key="smart",
        title="智能矢量",
        tagline="默认 · 视觉与编辑性平衡",
        detail="适合插画、海报素材和日常设计再编辑。",
    ),
    ModeCard(
        key="lightweight",
        title="轻量矢量",
        tagline="更少颜色与节点",
        detail="适合 Logo、图标、纹样和流畅编辑。",
    ),
    ModeCard(
        key="exact",
        title="精确重建",
        tagline="RGBA 像素一致性验证",
        detail="适合技术证明、像素网格存档和高级验证。",
    ),
)


@dataclass(frozen=True)
class AppParameters:
    mode: str = DEFAULT_MODE
    colors: int | None = None
    max_dimension: int | None = None
    simplify_ratio: float | None = None
    min_region_area: int | None = None
    alpha_threshold: int | None = None


def validated_input_path(value: str | Path) -> Path:
    path = Path(value)
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise AppInputError("请选择 PNG 或 JPEG 图片。")
    if not path.is_file():
        raise AppInputError("图片文件不存在或当前不可读取。")
    return path.resolve()


def reference_id_for(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"job-{digest.hexdigest()[:12]}"


def parameters_for_mode(mode: str) -> AppParameters:
    normalized = normalize_mode(mode)
    preset = PRESETS[normalized]
    return AppParameters(
        mode=normalized,
        colors=None if normalized == "exact" else preset.colors,
        max_dimension=None if normalized == "exact" else preset.max_dimension,
        simplify_ratio=None if normalized == "exact" else preset.simplify_ratio,
        min_region_area=None if normalized == "exact" else preset.min_region_area,
        alpha_threshold=None if normalized == "exact" else preset.alpha_threshold,
    )


def build_run_config(input_path: str | Path, parameters: AppParameters) -> RunConfig:
    path = validated_input_path(input_path)
    mode = normalize_mode(parameters.mode)
    return RunConfig(
        input_path=str(path),
        mode=mode,
        reference_id=reference_id_for(path),
        colors=parameters.colors if mode != "exact" else None,
        max_dimension=parameters.max_dimension if mode != "exact" else None,
        simplify_ratio=parameters.simplify_ratio if mode != "exact" else None,
        min_region_area=parameters.min_region_area if mode != "exact" else None,
        alpha_threshold=parameters.alpha_threshold if mode != "exact" else None,
    )


def result_metrics(result: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    vector = result["vector"]
    metrics = [
        ("颜色", str(vector["color_count"])),
        ("子路径", f"{vector['subpaths']:,}"),
        ("节点", f"{vector['points']:,}"),
        ("SVG", _format_bytes(vector["svg_bytes"])),
        ("耗时", f"{result['elapsed_seconds']:.2f}s"),
    ]
    exact = result.get("exact_validation")
    if exact is not None:
        metrics.append(("像素一致", "是" if exact["pixel_match"] else "否"))
    if result.get("mode", {}).get("key") == "artisan":
        metrics.append(("锚点减少", f"{vector['anchor_reduction_ratio']:.1%}"))
    return tuple(metrics)


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"
