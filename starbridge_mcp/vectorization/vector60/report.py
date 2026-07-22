from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCENES = frozenset({"logo", "lineart", "flat", "illustration", "unsupported_photo"})
STATUSES = frozenset(
    {"selected", "artisan_baseline_fallback", "unsupported_photo_fallback", "failed"}
)
SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")
MAX_CANDIDATES = 12


@dataclass(frozen=True)
class RenderMetrics:
    ssim: float
    normalized_mae: float
    edge_dice: float
    anchors: int
    subpaths: int
    svg_bytes: int
    elapsed_seconds: float
    reference_width: int
    reference_height: int
    rendered_width: int
    rendered_height: int

    def __post_init__(self) -> None:
        unit_metrics = (self.ssim, self.normalized_mae, self.edge_dice)
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in unit_metrics):
            raise ValueError("Render similarity metrics must be finite values from zero to one.")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0.0:
            raise ValueError("Render elapsed time must be finite and non-negative.")
        counts = (
            self.anchors,
            self.subpaths,
            self.svg_bytes,
            self.reference_width,
            self.reference_height,
            self.rendered_width,
            self.rendered_height,
        )
        if any(value < 0 for value in counts):
            raise ValueError("Render counts and dimensions must be non-negative.")
        if self.reference_width <= 0 or self.reference_height <= 0:
            raise ValueError("Reference dimensions must be positive.")
        if (self.rendered_width, self.rendered_height) != (
            self.reference_width,
            self.reference_height,
        ):
            raise ValueError("Formal metrics require an original-resolution final SVG render.")


@dataclass(frozen=True)
class Vector60Report:
    scene: str
    status: str
    candidate_count: int
    safety_verified: bool
    final_render_scored: bool
    selected_candidate: str | None = None
    metrics: RenderMetrics | None = None
    fallback_reason: str | None = None
    warning_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.scene not in SCENES:
            raise ValueError("Vector60 report scene is not supported.")
        if self.status not in STATUSES:
            raise ValueError("Vector60 report status is not supported.")
        if not 0 <= self.candidate_count <= MAX_CANDIDATES:
            raise ValueError("Vector60 report candidate count exceeds the hard limit.")
        safe_codes = (
            *(self.warning_codes or ()),
            *((self.selected_candidate,) if self.selected_candidate is not None else ()),
            *((self.fallback_reason,) if self.fallback_reason is not None else ()),
        )
        if any(SAFE_CODE.fullmatch(value) is None for value in safe_codes):
            raise ValueError("Vector60 reports accept only redaction-safe identifiers.")
        if self.status == "selected":
            if self.metrics is None or not self.final_render_scored or not self.safety_verified:
                raise ValueError(
                    "Selected results require safe original-resolution render evidence."
                )
            if self.selected_candidate is None:
                raise ValueError("Selected results require a candidate identifier.")
        if self.final_render_scored and self.metrics is None:
            raise ValueError("Final-render scoring requires render metrics.")
        if self.status != "selected" and self.fallback_reason is None:
            raise ValueError("Fallback and failure reports require a safe reason code.")

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "scene": self.scene,
            "status": self.status,
            "candidate_count": self.candidate_count,
            "selected_candidate": self.selected_candidate,
            "metrics": asdict(self.metrics) if self.metrics is not None else None,
            "validation": {
                "safety_verified": self.safety_verified,
                "final_render_scored": self.final_render_scored,
                "original_resolution_render": bool(
                    self.metrics is not None
                    and self.metrics.reference_width == self.metrics.rendered_width
                    and self.metrics.reference_height == self.metrics.rendered_height
                ),
            },
            "fallback_reason": self.fallback_reason,
            "warning_codes": list(self.warning_codes),
        }


def report_markdown(report: Vector60Report) -> str:
    payload = report.as_public_dict()
    metrics = report.metrics
    lines = [
        "# Vector60 run report",
        "",
        f"- Scene: `{report.scene}`",
        f"- Status: `{report.status}`",
        f"- Candidates: {report.candidate_count}/{MAX_CANDIDATES}",
        f"- Selected candidate: `{report.selected_candidate or 'none'}`",
        f"- SVG safety verified: `{str(report.safety_verified).lower()}`",
        f"- Original-resolution final render scored: "
        f"`{str(payload['validation']['original_resolution_render']).lower()}`",
    ]
    if metrics is not None:
        lines.extend(
            [
                "",
                "## Final render metrics",
                "",
                f"- SSIM: {metrics.ssim:.6f}",
                f"- Normalized MAE: {metrics.normalized_mae:.6f}",
                f"- Edge Dice: {metrics.edge_dice:.6f}",
                f"- Anchors: {metrics.anchors}",
                f"- Subpaths: {metrics.subpaths}",
                f"- SVG bytes: {metrics.svg_bytes}",
                f"- Elapsed seconds: {metrics.elapsed_seconds:.6f}",
            ]
        )
    if report.fallback_reason is not None:
        lines.extend(["", f"- Fallback reason: `{report.fallback_reason}`"])
    if report.warning_codes:
        lines.extend(["", "## Warning codes", ""])
        lines.extend(f"- `{code}`" for code in report.warning_codes)
    return "\n".join(lines) + "\n"


def write_report(output_directory: Path, report: Vector60Report) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "vector60_report.json"
    markdown_path = output_directory / "vector60_report.md"
    json_path.write_text(
        json.dumps(report.as_public_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(
        report_markdown(report),
        encoding="utf-8",
        newline="\n",
    )
    return json_path, markdown_path
