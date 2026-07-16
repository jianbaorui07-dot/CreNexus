from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

DEFAULT_MODE = "smart"
MODE_ALIASES = {"balanced": "smart"}


@dataclass(frozen=True)
class VectorPreset:
    mode: str
    label_zh: str
    purpose_zh: str
    max_dimension: int
    colors: int
    blur_diameter: int
    min_region_area: int
    simplify_ratio: float
    alpha_levels: int
    alpha_threshold: int
    max_source_pixels: int
    max_subpaths: int
    max_points: int
    max_svg_size_mb: float
    curve_smoothing: float
    corner_angle: float

    def public_parameters(self) -> dict[str, Any]:
        return asdict(self)


PRESETS: dict[str, VectorPreset] = {
    "smart": VectorPreset(
        mode="smart",
        label_zh="智能矢量",
        purpose_zh="默认模式；保留主要色块、轮廓和透明层次，兼顾视觉还原与编辑性。",
        max_dimension=1600,
        colors=24,
        blur_diameter=5,
        min_region_area=8,
        simplify_ratio=0.004,
        alpha_levels=4,
        alpha_threshold=8,
        max_source_pixels=40_000_000,
        max_subpaths=30_000,
        max_points=240_000,
        max_svg_size_mb=48.0,
        curve_smoothing=0.0,
        corner_angle=0.0,
    ),
    "lightweight": VectorPreset(
        mode="lightweight",
        label_zh="轻量矢量",
        purpose_zh="Logo、图标和纹样优先；减少颜色、碎片和节点，保证流畅编辑。",
        max_dimension=1024,
        colors=8,
        blur_diameter=7,
        min_region_area=32,
        simplify_ratio=0.012,
        alpha_levels=2,
        alpha_threshold=24,
        max_source_pixels=40_000_000,
        max_subpaths=6_000,
        max_points=40_000,
        max_svg_size_mb=12.0,
        curve_smoothing=0.0,
        corner_angle=0.0,
    ),
    "exact": VectorPreset(
        mode="exact",
        label_zh="精确重建",
        purpose_zh="专业高级模式；按源 RGBA 像素网格生成纯矢量矩形并执行像素一致性验证。",
        max_dimension=0,
        colors=0,
        blur_diameter=0,
        min_region_area=0,
        simplify_ratio=0.0,
        alpha_levels=256,
        alpha_threshold=0,
        max_source_pixels=4_000_000,
        max_subpaths=2_000_000,
        max_points=8_000_000,
        max_svg_size_mb=64.0,
        curve_smoothing=0.0,
        corner_angle=0.0,
    ),
    "artisan": VectorPreset(
        mode="artisan",
        label_zh="匠心矢量",
        purpose_zh="高级艺术模式；保留关键角点，以少量锚点生成直线与三次贝塞尔混合路径。",
        max_dimension=1600,
        colors=16,
        blur_diameter=5,
        min_region_area=24,
        simplify_ratio=0.014,
        alpha_levels=3,
        alpha_threshold=12,
        max_source_pixels=40_000_000,
        max_subpaths=8_000,
        max_points=60_000,
        max_svg_size_mb=16.0,
        curve_smoothing=0.82,
        corner_angle=118.0,
    ),
}


def normalize_mode(value: str) -> str:
    normalized = MODE_ALIASES.get(value.strip().lower(), value.strip().lower())
    if normalized not in PRESETS:
        raise ValueError("Mode must be smart, lightweight, exact, or artisan.")
    return normalized


def configured_preset(
    mode: str,
    *,
    colors: int | None = None,
    max_dimension: int | None = None,
    simplify_ratio: float | None = None,
    min_region_area: int | None = None,
    alpha_threshold: int | None = None,
    max_subpaths: int | None = None,
    max_points: int | None = None,
    max_svg_size_mb: float | None = None,
) -> VectorPreset:
    normalized = normalize_mode(mode)
    preset = PRESETS[normalized]
    overrides = {
        "colors": colors,
        "max_dimension": max_dimension,
        "simplify_ratio": simplify_ratio,
        "min_region_area": min_region_area,
        "alpha_threshold": alpha_threshold,
        "max_subpaths": max_subpaths,
        "max_points": max_points,
        "max_svg_size_mb": max_svg_size_mb,
    }
    preset = replace(
        preset, **{key: value for key, value in overrides.items() if value is not None}
    )
    _validate_preset(preset)
    return preset


def _validate_preset(preset: VectorPreset) -> None:
    if preset.mode != "exact":
        if not 2 <= preset.colors <= 256:
            raise ValueError("Color count must be between 2 and 256.")
        if not 16 <= preset.max_dimension <= 4096:
            raise ValueError("Maximum dimension must be between 16 and 4096.")
        if not 0 <= preset.simplify_ratio <= 0.1:
            raise ValueError("Simplify ratio must be between 0 and 0.1.")
        if preset.min_region_area < 0:
            raise ValueError("Minimum region area cannot be negative.")
    if not 0 <= preset.alpha_threshold <= 255:
        raise ValueError("Alpha threshold must be between 0 and 255.")
    if preset.max_subpaths < 1 or preset.max_points < 3:
        raise ValueError("Path safety limits must be positive.")
    if not 0 < preset.max_svg_size_mb <= 64:
        raise ValueError("SVG size limit must be greater than 0 and no more than 64 MiB.")
    if preset.mode == "artisan":
        if not 0 <= preset.curve_smoothing <= 1.5:
            raise ValueError("Curve smoothing must be between 0 and 1.5.")
        if not 30 <= preset.corner_angle <= 175:
            raise ValueError("Corner angle must be between 30 and 175 degrees.")
