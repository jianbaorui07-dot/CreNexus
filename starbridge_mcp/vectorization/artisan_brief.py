from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MAX_ANSWERS_BYTES = 64 * 1024
ANSWER_OPTIONS = {
    "primary_goal": ("art-detail", "minimum-anchors", "editing-balance"),
    "routing_rule": ("strict-topology", "smooth-flow", "source-fidelity"),
    "paint_strategy": (
        "preserve-palette",
        "reduce-near-colors",
        "monochrome",
        "manual-groups",
    ),
}
RECOMMENDED_ANSWERS = {
    "primary_goal": "art-detail",
    "routing_rule": "strict-topology",
    "paint_strategy": "preserve-palette",
}


class ArtisanBriefError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def brief_questions() -> dict[str, Any]:
    """Return the stable, short client questions used before local refinement."""
    return {
        "schema_version": 2,
        "questions": [
            {
                "id": "primary_goal",
                "prompt_zh": "本轮最优先保留什么？",
                "options": list(ANSWER_OPTIONS["primary_goal"]),
                "recommended": RECOMMENDED_ANSWERS["primary_goal"],
            },
            {
                "id": "routing_rule",
                "prompt_zh": "布线允许怎样调整？",
                "options": list(ANSWER_OPTIONS["routing_rule"]),
                "recommended": RECOMMENDED_ANSWERS["routing_rule"],
            },
            {
                "id": "paint_strategy",
                "prompt_zh": "颜色和块面怎样处理？",
                "options": list(ANSWER_OPTIONS["paint_strategy"]),
                "recommended": RECOMMENDED_ANSWERS["paint_strategy"],
            },
        ],
        "recommended_answers": RECOMMENDED_ANSWERS,
        "answer_format": RECOMMENDED_ANSWERS,
        "local_precalibration": True,
        "external_ai_calls": 0,
    }


def _validated_answers(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(ANSWER_OPTIONS):
        raise ArtisanBriefError(
            "invalid_brief_answers",
            "Answers must provide exactly primary_goal, routing_rule, and paint_strategy.",
        )
    answers: dict[str, str] = {}
    for key, options in ANSWER_OPTIONS.items():
        answer = value.get(key)
        if not isinstance(answer, str) or answer not in options:
            raise ArtisanBriefError(
                "invalid_brief_answers",
                f"Answer for {key} is not one of the supported options.",
            )
        answers[key] = answer
    return answers


def _compile_style_profile(answers_value: Any, *, schema_version: int) -> dict[str, Any]:
    answers = _validated_answers(answers_value)
    goal = answers["primary_goal"]
    routing = answers["routing_rule"]
    paint = answers["paint_strategy"]
    minimum_reduction = {
        "art-detail": 0.03,
        "minimum-anchors": 0.08,
        "editing-balance": 0.05,
    }[goal]
    maximum_deviation = {
        "art-detail": 0.8,
        "minimum-anchors": 1.6,
        "editing-balance": 1.1,
    }[goal]
    if routing == "source-fidelity":
        maximum_deviation *= 0.75
    elif routing == "smooth-flow":
        maximum_deviation *= 1.15
    intent_deviation = {
        "art-detail": {
            "flow-contour": 2.4,
            "ornament": 1.4,
            "detail": 0.9,
            "micro-detail": 0.65,
        },
        "minimum-anchors": {
            "flow-contour": 3.2,
            "ornament": 2.2,
            "detail": 1.6,
            "micro-detail": 1.1,
        },
        "editing-balance": {
            "flow-contour": 2.7,
            "ornament": 1.8,
            "detail": 1.2,
            "micro-detail": 0.85,
        },
    }[goal]
    routing_scale = {"strict-topology": 1.0, "smooth-flow": 1.1, "source-fidelity": 0.75}[routing]
    intent_deviation = {
        intent: round(value * routing_scale, 4) for intent, value in intent_deviation.items()
    }
    if schema_version == 1:
        appearance = {
            "preserve_path_count": True,
            "preserve_color_count": paint == "preserve-palette",
            "preserve_paint_count": paint == "preserve-palette",
            "preserve_unselected_paths": True,
        }
    else:
        appearance = {
            "preserve_unselected_paths": True,
            "paint": {
                "strategy": paint,
                "delta_e": {
                    "preserve-palette": 0.0,
                    "reduce-near-colors": 6.0,
                    "monochrome": 200.0,
                    "manual-groups": 0.0,
                }[paint],
                "min_block_reduction": 0.03,
                "max_subpaths": 96,
                "max_anchors": 1024,
            },
        }
    core = {
        "schema_version": schema_version,
        "answers": answers,
        "geometry": {
            "minimum_anchor_reduction_ratio": minimum_reduction,
            "maximum_mean_deviation_px": round(maximum_deviation * 0.45, 4),
            "maximum_deviation_px": round(maximum_deviation, 4),
            "maximum_mean_deviation_by_intent_px": {
                intent: round(value * 0.6, 4) for intent, value in intent_deviation.items()
            },
            "maximum_deviation_by_intent_px": intent_deviation,
            "preserve_endpoints": True,
            "reject_new_self_intersections": True,
            "reject_new_backtracking": True,
            "preserve_subpath_count": True,
        },
        "appearance": appearance,
        "calibration": {
            "kind": "deterministic-local-style-prior",
            "local_precalibration": True,
            "model_training": False,
            "external_ai_calls": 0,
        },
    }
    canonical = json.dumps(
        core,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return {
        **core,
        "profile_sha256": digest,
        "profile_ref": f"style:{digest[:12]}",
    }


def compile_style_profile(answers_value: Any) -> dict[str, Any]:
    """Compile client answers into deterministic local geometry constraints.

    This is local parameter pre-calibration, not model training. The profile is
    intentionally compact so later edits can refer to a short immutable digest.
    """
    return _compile_style_profile(answers_value, schema_version=2)


def load_style_profile(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanBriefError("invalid_style_profile", "Style profile must be one JSON file.")
    if path.stat().st_size > MAX_ANSWERS_BYTES:
        raise ArtisanBriefError("style_profile_too_large", "Style profile exceeds the local limit.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanBriefError(
            "invalid_style_profile", "Style profile is not valid UTF-8 JSON."
        ) from exc
    schema_version = value.get("schema_version") if isinstance(value, dict) else None
    if schema_version not in {1, 2}:
        raise ArtisanBriefError(
            "unsupported_style_profile", "Style profile schema is not supported."
        )
    expected = _compile_style_profile(
        value.get("answers"),
        schema_version=int(schema_version),
    )
    if value != expected:
        raise ArtisanBriefError(
            "style_profile_integrity_failed", "Style profile does not match its client answers."
        )
    return value


def _load_answers(path_value: str) -> Any:
    path = Path(path_value).expanduser()
    if not path.is_file() or path.suffix.lower() != ".json":
        raise ArtisanBriefError("invalid_brief_answers", "Answers must be one JSON file.")
    if path.stat().st_size > MAX_ANSWERS_BYTES:
        raise ArtisanBriefError("brief_answers_too_large", "Answers exceed the local limit.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtisanBriefError(
            "invalid_brief_answers", "Answers are not valid UTF-8 JSON."
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a compact local Artisan style prior.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("questions")
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--answers", required=True)
    compile_parser.add_argument("--output", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command == "questions":
            result = brief_questions()
        else:
            result = compile_style_profile(_load_answers(args.answers))
            output = Path(args.output).expanduser()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            result = {
                "ok": True,
                "profile_ref": result["profile_ref"],
                "profile_sha256": result["profile_sha256"],
                "external_ai_calls": 0,
            }
    except ArtisanBriefError as exc:
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
