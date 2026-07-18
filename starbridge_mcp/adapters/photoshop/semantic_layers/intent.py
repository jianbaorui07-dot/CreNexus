from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

INTENT_SCHEMA_VERSION = "starbridge.layer_intent.v1"
GITHUB_FEEDBACK_CONSENT_VERSION = "starbridge.github_metrics.v1"

_EDITING_GOALS = {
    "reposition_subjects",
    "edit_text",
    "replace_background",
    "all_major_elements",
}
_SUBJECT_GRANULARITIES = {"whole_subject", "major_instances", "semantic_groups"}
_TEXT_POLICIES = {"editable_when_confident", "pixel_reference_only", "ignore"}
_BACKGROUND_POLICIES = {"preserve_and_complete", "keep_original_pixels"}
_DECORATION_POLICIES = {"separate_salient", "keep_with_subject"}
_RISK_LEVELS = {"conservative", "balanced", "aggressive"}
_LINE_ART_STRATEGIES = {"line_art_on_texture", "monochrome_line_art"}


def recommended_intent_profile(
    strategy_id: str,
    *,
    text_mode: str = "conservative",
    review_region_limit: int = 8,
) -> dict[str, Any]:
    line_art = strategy_id in _LINE_ART_STRATEGIES
    return {
        "schema_version": INTENT_SCHEMA_VERSION,
        "primary_editing_goal": "reposition_subjects" if line_art else "all_major_elements",
        "subject_granularity": "major_instances" if line_art else "whole_subject",
        "text_policy": "ignore" if text_mode == "off" else "editable_when_confident",
        "background_policy": "preserve_and_complete",
        "decoration_policy": "separate_salient",
        "risk_level": "conservative",
        "review_budget": {
            "max_active_crops": 2,
            "max_total_crops": max(1, min(int(review_region_limit), 16)),
            "allow_full_image_followup": False,
        },
        "learning": {
            "record_decisions": False,
            "include_pixels": False,
        },
        "feedback": {
            "github_metrics_upload": False,
            "consent_version": GITHUB_FEEDBACK_CONSENT_VERSION,
            "include_customer_content": False,
        },
    }


def client_questions(strategy_id: str) -> list[dict[str, Any]]:
    subject_recommendation = (
        "major_instances" if strategy_id in _LINE_ART_STRATEGIES else "whole_subject"
    )
    return [
        {
            "id": "primary_editing_goal",
            "question": "交付后最常修改哪一类内容？",
            "recommended_value": "reposition_subjects"
            if strategy_id in _LINE_ART_STRATEGIES
            else "all_major_elements",
            "options": [
                {"value": "all_major_elements", "label": "主体、文字和背景都要改"},
                {"value": "reposition_subjects", "label": "主要移动或替换主体"},
                {"value": "edit_text", "label": "主要修改文字"},
                {"value": "replace_background", "label": "主要替换背景"},
            ],
            "why_it_matters": "决定计算和复核预算优先投入哪里。",
        },
        {
            "id": "subject_granularity",
            "question": "主体需要拆到什么粒度？",
            "recommended_value": subject_recommendation,
            "options": [
                {"value": "whole_subject", "label": "整体主体一层"},
                {"value": "major_instances", "label": "主要人物或物体分别成层"},
                {"value": "semantic_groups", "label": "按语义部件继续细拆"},
            ],
            "why_it_matters": "粒度越细，人工可控性更高，但歧义复核也会增加。",
        },
        {
            "id": "text_policy",
            "question": "文字需要真正可编辑，还是只保留像素参考？",
            "recommended_value": "editable_when_confident",
            "options": [
                {"value": "editable_when_confident", "label": "高置信时重建文字层"},
                {"value": "pixel_reference_only", "label": "只拆成像素参考层"},
                {"value": "ignore", "label": "文字保持在原图中"},
            ],
            "why_it_matters": "字体无法从扁平图中无损恢复，需明确可编辑性与还原度的取舍。",
        },
        {
            "id": "background_policy",
            "question": "移动主体后，是否必须看到补全后的完整背景？",
            "recommended_value": "preserve_and_complete",
            "options": [
                {"value": "preserve_and_complete", "label": "补全遮挡并保留纹理"},
                {"value": "keep_original_pixels", "label": "保留原始背景像素"},
            ],
            "why_it_matters": "背景补全提高可编辑性，但生成区域仍需 QA。",
        },
        {
            "id": "learning.record_decisions",
            "question": "是否允许把复核选择记录为本地、无像素的决策样本？",
            "recommended_value": False,
            "options": [
                {"value": False, "label": "不记录"},
                {"value": True, "label": "仅记录特征与选择"},
            ],
            "why_it_matters": "积累跨图片的标注后才能校准规则或进行后续预训练；源图和裁剪图不会写入样本。",
        },
        {
            "id": "feedback.github_metrics_upload",
            "question": "是否允许任务结束后向配置的 GitHub collector 上传匿名质量指标？",
            "recommended_value": False,
            "options": [
                {"value": False, "label": "不上传"},
                {"value": True, "label": "只上传白名单指标"},
            ],
            "why_it_matters": "用于跨客户发现失败模式；图片、文字、语义名称、路径和源文件指纹始终禁止上传。",
        },
    ]


def load_intent_profile(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("intent JSON must contain an object")
    return payload


def normalise_intent_profile(
    payload: dict[str, Any] | None,
    *,
    strategy_id: str,
    text_mode: str,
    review_region_limit: int,
) -> dict[str, Any]:
    profile = recommended_intent_profile(
        strategy_id,
        text_mode=text_mode,
        review_region_limit=review_region_limit,
    )
    if payload is not None:
        if payload.get("schema_version") != INTENT_SCHEMA_VERSION:
            raise ValueError("Unsupported intent schema_version")
        allowed_keys = {
            "schema_version",
            "primary_editing_goal",
            "subject_granularity",
            "text_policy",
            "background_policy",
            "decoration_policy",
            "risk_level",
            "review_budget",
            "learning",
            "feedback",
        }
        unknown_keys = set(payload) - allowed_keys
        if unknown_keys:
            raise ValueError(f"Unsupported intent keys: {sorted(unknown_keys)!r}")
        for key in (
            "primary_editing_goal",
            "subject_granularity",
            "text_policy",
            "background_policy",
            "decoration_policy",
            "risk_level",
        ):
            if key in payload:
                profile[key] = payload[key]
        if "review_budget" in payload:
            if not isinstance(payload["review_budget"], dict):
                raise ValueError("intent.review_budget must be an object")
            unknown_review_keys = set(payload["review_budget"]) - {
                "max_active_crops",
                "max_total_crops",
                "allow_full_image_followup",
            }
            if unknown_review_keys:
                raise ValueError(
                    f"Unsupported intent.review_budget keys: {sorted(unknown_review_keys)!r}"
                )
            profile["review_budget"].update(payload["review_budget"])
        if "learning" in payload:
            if not isinstance(payload["learning"], dict):
                raise ValueError("intent.learning must be an object")
            unknown_learning_keys = set(payload["learning"]) - {
                "record_decisions",
                "include_pixels",
            }
            if unknown_learning_keys:
                raise ValueError(
                    f"Unsupported intent.learning keys: {sorted(unknown_learning_keys)!r}"
                )
            profile["learning"].update(payload["learning"])
        if "feedback" in payload:
            if not isinstance(payload["feedback"], dict):
                raise ValueError("intent.feedback must be an object")
            unknown_feedback_keys = set(payload["feedback"]) - {
                "github_metrics_upload",
                "consent_version",
                "include_customer_content",
            }
            if unknown_feedback_keys:
                raise ValueError(
                    f"Unsupported intent.feedback keys: {sorted(unknown_feedback_keys)!r}"
                )
            profile["feedback"].update(payload["feedback"])

    allowed_values = {
        "primary_editing_goal": _EDITING_GOALS,
        "subject_granularity": _SUBJECT_GRANULARITIES,
        "text_policy": _TEXT_POLICIES,
        "background_policy": _BACKGROUND_POLICIES,
        "decoration_policy": _DECORATION_POLICIES,
        "risk_level": _RISK_LEVELS,
    }
    for key, allowed in allowed_values.items():
        if profile[key] not in allowed:
            raise ValueError(f"Unsupported intent.{key}: {profile[key]!r}")

    review_budget = profile["review_budget"]
    max_active = int(review_budget.get("max_active_crops", 2))
    max_total = int(review_budget.get("max_total_crops", review_region_limit))
    if not 1 <= max_active <= 4:
        raise ValueError("intent.review_budget.max_active_crops must be between 1 and 4")
    if not 1 <= max_total <= 16:
        raise ValueError("intent.review_budget.max_total_crops must be between 1 and 16")
    review_budget.update(
        {
            "max_active_crops": max_active,
            "max_total_crops": max_total,
            "allow_full_image_followup": bool(
                review_budget.get("allow_full_image_followup", False)
            ),
        }
    )
    learning = profile["learning"]
    learning["record_decisions"] = bool(learning.get("record_decisions", False))
    learning["include_pixels"] = bool(learning.get("include_pixels", False))
    if learning["include_pixels"]:
        raise ValueError("Pixel-bearing learning records are not supported")
    feedback = profile["feedback"]
    feedback["github_metrics_upload"] = bool(feedback.get("github_metrics_upload", False))
    feedback["include_customer_content"] = bool(feedback.get("include_customer_content", False))
    if feedback["include_customer_content"]:
        raise ValueError("Customer content cannot be included in GitHub feedback")
    if feedback["github_metrics_upload"] and (
        feedback.get("consent_version") != GITHUB_FEEDBACK_CONSENT_VERSION
    ):
        raise ValueError("GitHub feedback requires the current consent_version")
    feedback["consent_version"] = GITHUB_FEEDBACK_CONSENT_VERSION
    profile["schema_version"] = INTENT_SCHEMA_VERSION
    return profile


def intent_profile_hash(profile: dict[str, Any]) -> str:
    canonical = json.dumps(
        profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
