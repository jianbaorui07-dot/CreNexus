from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .intent import recommended_intent_profile
from .manifest import load_manifest
from .pipeline import DecompositionOptions, decompose_image, plan_image
from .public_dataset import PUBLIC_DATASET_SCHEMA

PUBLIC_EXPERIMENT_SCHEMA = "starbridge.public_client_mode_experiment.v1"


def _enable_public_learning(profile: dict[str, Any]) -> dict[str, Any]:
    profile["learning"]["record_decisions"] = True
    profile["learning"]["include_pixels"] = False
    return profile


def _client_mode(use_case: str, detected_strategy: str) -> tuple[str, dict[str, Any], str]:
    if use_case == "line_art":
        profile = recommended_intent_profile(detected_strategy)
        profile["primary_editing_goal"] = "reposition_subjects"
        profile["subject_granularity"] = "whole_subject"
        profile["text_policy"] = "ignore"
        profile["decoration_policy"] = "keep_with_subject"
        return "auto", _enable_public_learning(profile), "single_line_art_subject"
    if use_case == "product":
        profile = recommended_intent_profile("character_basic")
        profile["primary_editing_goal"] = "reposition_subjects"
        profile["subject_granularity"] = "whole_subject"
        profile["text_policy"] = "pixel_reference_only"
        return (
            "character_basic",
            _enable_public_learning(profile),
            "movable_product_with_brand_pixels_preserved",
        )
    if use_case == "portrait":
        profile = recommended_intent_profile("character_basic")
        profile["primary_editing_goal"] = "reposition_subjects"
        profile["subject_granularity"] = "whole_subject"
        profile["text_policy"] = "ignore"
        return (
            "character_basic",
            _enable_public_learning(profile),
            "movable_person_without_text_rebuild",
        )
    if use_case == "poster":
        profile = recommended_intent_profile("poster_basic")
        profile["primary_editing_goal"] = "all_major_elements"
        profile["subject_granularity"] = "whole_subject"
        profile["text_policy"] = "editable_when_confident"
        return (
            "poster_basic",
            _enable_public_learning(profile),
            "poster_background_subject_and_text",
        )
    raise ValueError(f"Unsupported public experiment use_case: {use_case!r}")


def run_public_client_mode_experiment(
    dataset_manifest_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    dataset_path = Path(dataset_manifest_path).expanduser().resolve()
    dataset_root = dataset_path.parent
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if dataset.get("schema_version") != PUBLIC_DATASET_SCHEMA:
        raise ValueError("Unsupported public dataset manifest schema_version")
    if not dataset.get("license_verified") or dataset.get("private_paths_recorded"):
        raise ValueError("Public dataset manifest did not pass provenance checks")
    output = Path(output_root).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    for item in dataset.get("items", []):
        asset = (dataset_root / str(item["local_asset"])).resolve()
        if not asset.is_relative_to(dataset_root) or not asset.is_file():
            raise ValueError("Public dataset asset escaped its dataset root or is missing")
        plan = plan_image(asset)
        detected_strategy = str(plan["recommended_strategy"]["id"])
        preset, profile, rationale = _client_mode(str(item["use_case"]), detected_strategy)
        job_id = str(item["id"])
        job_dir = output / job_id
        try:
            decompose_image(
                asset,
                job_dir,
                options=DecompositionOptions(preset=preset),
                intent=profile,
                force=True,
            )
            manifest = load_manifest(job_dir / "manifest.json")
            review_packet = json.loads((job_dir / "review_packet.json").read_text(encoding="utf-8"))
            cases.append(
                {
                    "id": job_id,
                    "ok": True,
                    "use_case": item["use_case"],
                    "license_family": item["license_family"],
                    "auto_strategy": detected_strategy,
                    "client_preset": preset,
                    "client_mode_rationale": rationale,
                    "intent": {
                        "editing_goal": profile["primary_editing_goal"],
                        "subject_granularity": profile["subject_granularity"],
                        "text_policy": profile["text_policy"],
                        "background_policy": profile["background_policy"],
                    },
                    "layer_count": len(manifest["layers"]),
                    "review_item_count": len(review_packet.get("items", [])),
                    "requires_manual_review": bool(manifest["quality"]["requires_manual_review"]),
                    "recomposition_similarity": manifest["quality"]["recomposition_similarity"],
                    "overall_score": manifest["quality"]["overall_score"],
                    "ground_truth_status": "unreviewed_candidate_output",
                }
            )
        except Exception as exc:
            cases.append(
                {
                    "id": job_id,
                    "ok": False,
                    "use_case": item["use_case"],
                    "error_type": type(exc).__name__,
                    "error": "Public client-mode decomposition failed for this case.",
                    "ground_truth_status": "unavailable",
                }
            )
    report = {
        "schema_version": PUBLIC_EXPERIMENT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "ok": all(case["ok"] for case in cases),
        "case_count": len(cases),
        "license_verified_inputs": True,
        "simulated_client_mode": True,
        "automatic_outputs_are_training_labels": False,
        "private_paths_recorded": False,
        "cases": cases,
    }
    report_path = output / "experiment_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**report, "report_path": str(report_path)}
