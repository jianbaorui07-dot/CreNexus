from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .intent import GITHUB_FEEDBACK_CONSENT_VERSION
from .manifest import load_manifest

FEEDBACK_SCHEMA_VERSION = "starbridge.github_issue_metrics.v1"
_EVENT_TYPES = {"run", "patch", "build", "batch"}
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_DISCUSSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_=:-]{8,200}$")
_WINDOWS_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\]+\\)")
_POSIX_PRIVATE_PATH = re.compile(r"(?:^|[\s\"'])/(?:home|users|private|var|tmp)/")


def _bucket_megapixels(width: int, height: int) -> str:
    megapixels = width * height / 1_000_000.0
    if megapixels <= 1:
        return "up_to_1mp"
    if megapixels <= 4:
        return "1_to_4mp"
    if megapixels <= 16:
        return "4_to_16mp"
    return "over_16mp"


def _orientation(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if 0.9 <= ratio <= 1.1:
        return "square"
    return "landscape" if ratio > 1 else "portrait"


def _rounded(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def build_manifest_feedback(
    manifest: dict[str, Any],
    *,
    event_type: str,
    operation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in _EVENT_TYPES - {"batch"}:
        raise ValueError("Unsupported manifest feedback event_type")
    result = operation_result or {}
    intent = manifest.get("intent", {}).get("profile", {})
    quality = manifest.get("quality", {})
    semantic_quality = quality.get("semantic_subdivision", {})
    background_quality = quality.get("background", {})
    width = int(manifest["canvas"]["width"])
    height = int(manifest["canvas"]["height"])
    return {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "event_id": secrets.token_hex(8),
        "day_utc": datetime.now(UTC).date().isoformat(),
        "event_type": event_type,
        "pipeline_version": str(manifest.get("pipeline", {}).get("version") or "unknown"),
        "strategy": str(manifest.get("strategy", {}).get("id") or "unknown"),
        "intent": {
            "editing_goal": str(intent.get("primary_editing_goal") or "unknown"),
            "subject_granularity": str(intent.get("subject_granularity") or "unknown"),
            "text_policy": str(intent.get("text_policy") or "unknown"),
            "background_policy": str(intent.get("background_policy") or "unknown"),
            "decoration_policy": str(intent.get("decoration_policy") or "unknown"),
            "risk_level": str(intent.get("risk_level") or "unknown"),
        },
        "document": {
            "orientation": _orientation(width, height),
            "size_bucket": _bucket_megapixels(width, height),
        },
        "quality": {
            "overall": _rounded(quality.get("overall_score")),
            "recomposition": _rounded(quality.get("recomposition_similarity")),
            "background_clean": _rounded(background_quality.get("clean_score")),
            "layer_editability": _rounded(semantic_quality.get("layer_editability_score")),
            "manual_review_required": bool(quality.get("requires_manual_review")),
        },
        "result": {
            "ok": bool(result.get("ok", True)),
            "cached": bool(result.get("cached", False)),
            "layer_count": len(manifest.get("layers", [])),
            "semantic_region_count": len(manifest.get("analysis", {}).get("semantic_regions", [])),
            "local_patch_applied": bool(result.get("reprocessed_pixels", False)),
            "background_recomputed": bool(result.get("background_recomputed", False)),
        },
        "privacy": {
            "customer_material_included": False,
            "local_identifiers_included": False,
            "asset_fingerprints_included": False,
        },
    }


def build_batch_feedback(
    report: dict[str, Any],
    *,
    intent_profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": FEEDBACK_SCHEMA_VERSION,
        "event_id": secrets.token_hex(8),
        "day_utc": datetime.now(UTC).date().isoformat(),
        "event_type": "batch",
        "pipeline_version": "batch_v1",
        "strategy": "mixed_or_configured",
        "intent": {
            "editing_goal": str(intent_profile.get("primary_editing_goal") or "unknown"),
            "subject_granularity": str(intent_profile.get("subject_granularity") or "unknown"),
            "text_policy": str(intent_profile.get("text_policy") or "unknown"),
            "background_policy": str(intent_profile.get("background_policy") or "unknown"),
            "decoration_policy": str(intent_profile.get("decoration_policy") or "unknown"),
            "risk_level": str(intent_profile.get("risk_level") or "unknown"),
        },
        "document": {"orientation": "mixed", "size_bucket": "mixed"},
        "quality": {
            "overall": None,
            "recomposition": None,
            "background_clean": None,
            "layer_editability": None,
            "manual_review_required": False,
        },
        "result": {
            "ok": int(report.get("failed", 0)) == 0,
            "cached": int(report.get("cached", 0)) > 0,
            "layer_count": 0,
            "semantic_region_count": 0,
            "local_patch_applied": False,
            "background_recomputed": False,
            "batch_size": int(report.get("input_count", 0)),
            "completed_count": int(report.get("completed", 0)),
            "failed_count": int(report.get("failed", 0)),
        },
        "privacy": {
            "customer_material_included": False,
            "local_identifiers_included": False,
            "asset_fingerprints_included": False,
        },
    }


def validate_feedback_payload(payload: dict[str, Any]) -> None:
    allowed_top_level = {
        "schema_version",
        "event_id",
        "day_utc",
        "event_type",
        "pipeline_version",
        "strategy",
        "intent",
        "document",
        "quality",
        "result",
        "privacy",
    }
    if payload.get("schema_version") != FEEDBACK_SCHEMA_VERSION:
        raise ValueError("Unsupported GitHub feedback schema_version")
    if set(payload) != allowed_top_level:
        raise ValueError("GitHub feedback top-level fields do not match the allowlist")
    if payload.get("event_type") not in _EVENT_TYPES:
        raise ValueError("Unsupported GitHub feedback event_type")

    exact_nested_fields = {
        "intent": {
            "editing_goal",
            "subject_granularity",
            "text_policy",
            "background_policy",
            "decoration_policy",
            "risk_level",
        },
        "document": {"orientation", "size_bucket"},
        "quality": {
            "overall",
            "recomposition",
            "background_clean",
            "layer_editability",
            "manual_review_required",
        },
        "privacy": {
            "customer_material_included",
            "local_identifiers_included",
            "asset_fingerprints_included",
        },
    }
    result_fields = {
        "ok",
        "cached",
        "layer_count",
        "semantic_region_count",
        "local_patch_applied",
        "background_recomputed",
    }
    batch_result_fields = {"batch_size", "completed_count", "failed_count"}
    for section, expected in exact_nested_fields.items():
        if not isinstance(payload.get(section), dict) or set(payload[section]) != expected:
            raise ValueError(f"GitHub feedback {section} fields do not match the allowlist")
    actual_result_fields = set(payload.get("result", {}))
    allowed_result_fields = result_fields | (
        batch_result_fields if payload.get("event_type") == "batch" else set()
    )
    if actual_result_fields != allowed_result_fields:
        raise ValueError("GitHub feedback result fields do not match the allowlist")

    def inspect(value: Any, key_path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                inspect(item, (*key_path, str(key)))
            return
        if isinstance(value, list):
            for item in value:
                inspect(item, key_path)
            return
        if isinstance(value, str):
            if len(value) > 128:
                raise ValueError("GitHub feedback string exceeds 128 characters")
            if _WINDOWS_PATH.search(value) or _POSIX_PRIVATE_PATH.search(value):
                raise ValueError("GitHub feedback contains a local path")

    inspect(payload)
    privacy = payload.get("privacy", {})
    if any(bool(value) for value in privacy.values()):
        raise ValueError("GitHub feedback privacy flags must all be false")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > 8192:
        raise ValueError("GitHub feedback payload exceeds 8 KiB")


def _feedback_consent(profile: dict[str, Any]) -> bool:
    feedback = profile.get("feedback", {})
    return (
        bool(feedback.get("github_metrics_upload"))
        and (feedback.get("consent_version") == GITHUB_FEEDBACK_CONSENT_VERSION)
        and not bool(feedback.get("include_customer_content"))
    )


def _collector_target() -> dict[str, Any] | None:
    transport = os.environ.get("STARBRIDGE_FEEDBACK_TRANSPORT", "issue_comment").strip()
    if transport not in {"issue_comment", "discussion_comment"}:
        raise ValueError("STARBRIDGE_FEEDBACK_TRANSPORT is not allowlisted")
    repository = os.environ.get("STARBRIDGE_FEEDBACK_REPOSITORY", "").strip()
    if not repository:
        return None
    if not _REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("STARBRIDGE_FEEDBACK_REPOSITORY must be owner/repository")
    if transport == "issue_comment":
        issue_text = os.environ.get("STARBRIDGE_FEEDBACK_ISSUE", "").strip()
        if not issue_text:
            return None
        issue_number = int(issue_text)
        if issue_number <= 0:
            raise ValueError("STARBRIDGE_FEEDBACK_ISSUE must be a positive integer")
        return {
            "transport": transport,
            "repository": repository,
            "issue_number": issue_number,
        }
    discussion_id = os.environ.get("STARBRIDGE_FEEDBACK_DISCUSSION_ID", "").strip()
    if not discussion_id:
        return None
    if not _DISCUSSION_ID_PATTERN.fullmatch(discussion_id):
        raise ValueError("STARBRIDGE_FEEDBACK_DISCUSSION_ID is invalid")
    return {
        "transport": transport,
        "repository": repository,
        "discussion_id": discussion_id,
    }


def _issue_comment_body(payload: dict[str, Any]) -> str:
    return (
        "<!-- starbridge-layer-feedback-v1 -->\n"
        "Anonymous metrics-only layer pipeline feedback.\n\n"
        "```json\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n```"
    )


def submit_feedback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_feedback_payload(payload)
    target = _collector_target()
    if target is None:
        return {"status": "not_configured", "uploaded": False}
    if os.environ.get("STARBRIDGE_FEEDBACK_DRY_RUN") == "1":
        return {
            "status": "dry_run",
            "uploaded": False,
            "payload": payload,
        }
    body = _issue_comment_body(payload)
    if target["transport"] == "issue_comment":
        command = [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{target['repository']}/issues/{target['issue_number']}/comments",
            "-f",
            f"body={body}",
        ]
    else:
        query = (
            "mutation($discussionId:ID!,$body:String!){"
            "addDiscussionComment(input:{discussionId:$discussionId,body:$body}){"
            "comment{id url}}}"
        )
        command = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"discussionId={target['discussion_id']}",
            "-f",
            f"body={body}",
        ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {"status": "transport_error", "uploaded": False}
    if completed.returncode != 0:
        return {"status": "github_rejected", "uploaded": False}
    return {
        "status": "uploaded",
        "uploaded": True,
        "event_id": payload["event_id"],
        "transport": target["transport"],
    }


def maybe_submit_manifest_feedback(
    manifest_path: str | Path,
    *,
    event_type: str,
    operation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(Path(manifest_path).expanduser().resolve())
    profile = manifest.get("intent", {}).get("profile", {})
    if not _feedback_consent(profile):
        return {"status": "disabled", "uploaded": False}
    try:
        payload = build_manifest_feedback(
            manifest,
            event_type=event_type,
            operation_result=operation_result,
        )
        return submit_feedback_payload(payload)
    except (TypeError, ValueError):
        return {"status": "privacy_or_configuration_rejected", "uploaded": False}


def maybe_submit_batch_feedback(
    report: dict[str, Any],
    *,
    intent_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    profile = intent_profile or {}
    if not _feedback_consent(profile):
        return {"status": "disabled", "uploaded": False}
    try:
        return submit_feedback_payload(build_batch_feedback(report, intent_profile=profile))
    except (TypeError, ValueError):
        return {"status": "privacy_or_configuration_rejected", "uploaded": False}
