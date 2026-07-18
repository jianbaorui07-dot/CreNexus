from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .intent import recommended_intent_profile
from .manifest import GROUPS_BOTTOM_TO_TOP, load_manifest, resolve_layer_sources
from .pipeline import DecompositionOptions, decompose_image

REGRESSION_SCHEMA_VERSION = "starbridge.image_to_editable_psd.regression.v1"


def _make_line_art(path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (320, 420), (242, 230, 201))
    draw = ImageDraw.Draw(image)
    ink = (174, 73, 52)
    draw.ellipse((55, 70, 265, 300), outline=ink, width=3)
    for offset in range(0, 150, 12):
        draw.arc(
            (70 + offset // 4, 95, 245, 285 - offset // 5),
            20,
            320,
            fill=ink,
            width=2,
        )
    draw.ellipse((132, 173, 190, 231), outline=ink, width=3)
    for x in range(138, 189, 6):
        draw.line((x, 178, 188 - (x - 138), 226), fill=ink, width=2)
    draw.rectangle((265, 342, 300, 383), outline=ink, width=3)
    draw.line((269, 348, 296, 377), fill=ink, width=2)
    draw.line((296, 348, 269, 377), fill=ink, width=2)
    image.save(path)


def _make_poster(image_path: Path, subject_path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (240, 180), (18, 42, 80))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 65, 170, 165), fill=(235, 102, 44))
    draw.text((20, 20), "TITLE", fill=(255, 255, 255))
    image.save(image_path)
    cutout = Image.new("RGBA", image.size, (0, 0, 0, 0))
    cutout.paste(image.crop((70, 65, 170, 165)), (70, 65))
    alpha = Image.new("L", image.size, 0)
    ImageDraw.Draw(alpha).rectangle((70, 65, 169, 164), fill=255)
    cutout.putalpha(alpha)
    cutout.save(subject_path)


def _result_summary(job_dir: Path, expected: dict[str, Any]) -> dict[str, Any]:
    manifest_path = job_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    sources_exist = bool(resolve_layer_sources(manifest_path, manifest))
    layer_types = [str(layer["type"]) for layer in manifest["layers"]]
    editable_text_present = "text" in layer_types
    groups_match = manifest["groups_bottom_to_top"] == list(GROUPS_BOTTOM_TO_TOP)
    checks = {
        "strategy": manifest["strategy"]["id"] == expected["strategy"],
        "intent_explicit": manifest["intent"]["status"] == "explicit",
        "recomposition": float(manifest["quality"]["recomposition_similarity"])
        >= float(expected["minimum_recomposition"]),
        "layer_sources": sources_exist,
        "groups": groups_match,
        "editable_text_contract": editable_text_present == bool(expected["editable_text"]),
        "background_contract": bool(manifest["analysis"]["background_repair_applied"])
        == bool(expected["background_repair_applied"]),
    }
    minimum_regions = int(expected.get("minimum_semantic_regions", 0))
    if minimum_regions:
        checks["semantic_regions"] = (
            len(manifest["analysis"]["semantic_regions"]) >= minimum_regions
        )
    return {
        "ok": all(checks.values()),
        "job_id": job_dir.name,
        "strategy": manifest["strategy"]["id"],
        "intent_profile_sha256": manifest["intent"]["profile_sha256"],
        "layer_count": len(manifest["layers"]),
        "semantic_region_count": len(manifest["analysis"]["semantic_regions"]),
        "editable_text_present": editable_text_present,
        "background_repair_applied": manifest["analysis"]["background_repair_applied"],
        "recomposition_similarity": manifest["quality"]["recomposition_similarity"],
        "checks": checks,
    }


def run_synthetic_regression(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    inputs = root / "generated_inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    line_art = inputs / "public_line_art.png"
    poster = inputs / "public_poster.png"
    poster_subject = inputs / "public_poster_subject.png"
    _make_line_art(line_art)
    _make_poster(poster, poster_subject)

    text_analysis = {
        "subject_mask_path": str(poster_subject),
        "text_regions": [
            {
                "id": "text_01",
                "bbox": [18, 15, 100, 42],
                "content": "TITLE",
                "font_candidates": ["sans-serif-heavy"],
                "font_size": 24,
                "color": "#FFFFFF",
                "confidence": 0.95,
            }
        ],
    }
    line_intent = recommended_intent_profile("line_art_on_texture")
    editable_intent = recommended_intent_profile("poster_basic")
    pixel_text_intent = recommended_intent_profile("poster_basic")
    pixel_text_intent["text_policy"] = "pixel_reference_only"
    original_background_intent = recommended_intent_profile("poster_basic")
    original_background_intent["background_policy"] = "keep_original_pixels"

    cases = [
        {
            "id": "line_art_major_instances",
            "input": line_art,
            "options": DecompositionOptions(preset="auto"),
            "intent": line_intent,
            "analysis": None,
            "expected": {
                "strategy": "line_art_on_texture",
                "minimum_recomposition": 0.98,
                "minimum_semantic_regions": 6,
                "editable_text": False,
                "background_repair_applied": True,
            },
        },
        {
            "id": "poster_editable_text",
            "input": poster,
            "options": DecompositionOptions(preset="poster_basic"),
            "intent": editable_intent,
            "analysis": text_analysis,
            "expected": {
                "strategy": "poster_basic",
                "minimum_recomposition": 0.95,
                "editable_text": True,
                "background_repair_applied": True,
            },
        },
        {
            "id": "poster_pixel_text_reference",
            "input": poster,
            "options": DecompositionOptions(preset="poster_basic"),
            "intent": pixel_text_intent,
            "analysis": text_analysis,
            "expected": {
                "strategy": "poster_basic",
                "minimum_recomposition": 0.95,
                "editable_text": False,
                "background_repair_applied": True,
            },
        },
        {
            "id": "poster_original_background",
            "input": poster,
            "options": DecompositionOptions(preset="poster_basic"),
            "intent": original_background_intent,
            "analysis": text_analysis,
            "expected": {
                "strategy": "poster_basic",
                "minimum_recomposition": 0.99,
                "editable_text": True,
                "background_repair_applied": False,
            },
        },
    ]
    results: list[dict[str, Any]] = []
    for case in cases:
        job_dir = root / str(case["id"])
        decompose_image(
            case["input"],
            job_dir,
            options=case["options"],
            intent=case["intent"],
            analysis=case["analysis"],
            force=True,
        )
        results.append(_result_summary(job_dir, case["expected"]))
    report = {
        "schema_version": REGRESSION_SCHEMA_VERSION,
        "ok": all(item["ok"] for item in results),
        "case_count": len(results),
        "generated_public_inputs": True,
        "private_paths_recorded": False,
        "cases": results,
    }
    report_path = root / "regression_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**report, "report_path": str(report_path)}
