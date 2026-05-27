from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


REQUIRED_RESULT_FIELDS = ("ok", "bridge", "action", "message", "details", "warnings", "next_steps")


@dataclass(frozen=True)
class BridgeResult:
    ok: bool
    bridge: str
    action: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bridge": self.bridge,
            "action": self.action,
            "message": self.message,
            "details": self.details,
            "warnings": self.warnings,
            "next_steps": self.next_steps,
        }


def make_result(
    *,
    ok: bool,
    bridge: str,
    action: str,
    message: str,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    return BridgeResult(
        ok=ok,
        bridge=bridge,
        action=action,
        message=message,
        details=details or {},
        warnings=warnings or [],
        next_steps=next_steps or [],
    ).to_dict()


def validate_result(result: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_RESULT_FIELDS if field not in result]
    if missing:
        raise ValueError(f"missing StarBridge result fields: {', '.join(missing)}")
    if not isinstance(result["ok"], bool):
        raise TypeError("ok must be bool")
    for field_name in ("bridge", "action", "message"):
        if not isinstance(result[field_name], str):
            raise TypeError(f"{field_name} must be str")
    if not isinstance(result["details"], dict):
        raise TypeError("details must be dict")
    if not isinstance(result["warnings"], list):
        raise TypeError("warnings must be list")
    if not isinstance(result["next_steps"], list):
        raise TypeError("next_steps must be list")
