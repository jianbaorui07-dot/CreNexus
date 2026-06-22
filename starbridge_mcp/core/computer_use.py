from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from starbridge_mcp.core.security import sanitize

REPO_ROOT = Path(__file__).resolve().parents[2]
SAFE_OUTPUT_ROOTS = ("outputs", "examples", "tmp")
APPS = {"photoshop", "illustrator", "comfyui", "blender", "autocad", "capcut", "generic"}
EXECUTION_MODES = {"computer_use", "structured_tool", "hybrid"}
STRUCTURED_METHODS = {
    "jsx",
    "uxp",
    "python",
    "cli",
    "com",
    "api",
    "filesystem",
    "dxf",
    "svg",
    "none",
}
RISK_LEVELS = {"read", "write", "destructive"}


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def is_safe_output_path(path_text: str) -> bool:
    if not path_text:
        return False
    path = _resolve_repo_path(path_text)
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError:
        return False
    parts = relative.parts
    return bool(parts) and parts[0] in SAFE_OUTPUT_ROOTS


@dataclass
class GuiStep:
    step_id: str
    instruction: str
    target_app: str
    expected_screen_state: str
    fallback_if_failed: str = ""
    requires_confirmation: bool = False
    evidence_required: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GuiStep:
        return cls(
            step_id=str(data.get("step_id") or data.get("id") or ""),
            instruction=str(data.get("instruction") or ""),
            target_app=str(data.get("target_app") or data.get("app") or "generic"),
            expected_screen_state=str(data.get("expected_screen_state") or ""),
            fallback_if_failed=str(data.get("fallback_if_failed") or ""),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            evidence_required=bool(data.get("evidence_required", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionPlan:
    id: str
    app: str
    action: str
    goal: str
    params: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "structured_tool"
    structured_method: str = "none"
    gui_steps: list[GuiStep] = field(default_factory=list)
    expected_result: str = ""
    output_paths: list[str] = field(default_factory=list)
    needs_screenshot_evidence: bool = False
    risk_level: str = "read"
    dry_run: bool = True
    confirm_write: bool = False
    allow_computer_use: bool = False
    requires_user_presence: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionPlan:
        gui_steps = [
            GuiStep.from_dict(item)
            for item in _as_list(data.get("gui_steps"))
            if isinstance(item, dict)
        ]
        plan = cls(
            id=str(data.get("id") or f"plan-{_now_id()}"),
            app=str(data.get("app") or "generic"),
            action=str(data.get("action") or "unspecified"),
            goal=str(data.get("goal") or ""),
            params=dict(data.get("params") or {}),
            execution_mode=str(data.get("execution_mode") or "structured_tool"),
            structured_method=str(data.get("structured_method") or "none"),
            gui_steps=gui_steps,
            expected_result=str(data.get("expected_result") or ""),
            output_paths=[str(item) for item in _as_list(data.get("output_paths"))],
            needs_screenshot_evidence=bool(data.get("needs_screenshot_evidence", False)),
            risk_level=str(data.get("risk_level") or "read"),
            dry_run=bool(data.get("dry_run", True)),
            confirm_write=bool(data.get("confirm_write", False)),
            allow_computer_use=bool(data.get("allow_computer_use", False)),
            requires_user_presence=bool(data.get("requires_user_presence", False)),
        )
        plan.validate_shape()
        return plan

    @classmethod
    def load(cls, path: str | Path) -> ActionPlan:
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def validate_shape(self) -> None:
        if self.app not in APPS:
            raise ValueError(f"unsupported app: {self.app}")
        if self.execution_mode not in EXECUTION_MODES:
            raise ValueError(f"unsupported execution_mode: {self.execution_mode}")
        if self.structured_method not in STRUCTURED_METHODS:
            raise ValueError(f"unsupported structured_method: {self.structured_method}")
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(f"unsupported risk_level: {self.risk_level}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["gui_steps"] = [step.to_dict() for step in self.gui_steps]
        return payload


@dataclass
class SafetyDecision:
    allowed: bool
    reason: str
    required_flags: list[str] = field(default_factory=list)
    blocked_because: list[str] = field(default_factory=list)
    risk_level: str = "read"
    user_confirmation_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    ok: bool
    app: str
    action: str
    execution_mode: str
    performed_steps: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)
    message: str = ""
    next_recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_safety(
    plan: ActionPlan, *, confirm_write: bool | None = None, allow_computer_use: bool | None = None
) -> SafetyDecision:
    effective_confirm_write = plan.confirm_write if confirm_write is None else confirm_write
    effective_allow_computer_use = (
        plan.allow_computer_use if allow_computer_use is None else allow_computer_use
    )
    blocked: list[str] = []
    required_flags: list[str] = []

    if plan.execution_mode in {"computer_use", "hybrid"} and not effective_allow_computer_use:
        blocked.append("computer use requires explicit allow_computer_use")
        required_flags.append("--allow-computer-use")

    if (
        plan.risk_level in {"write", "destructive"}
        and not plan.dry_run
        and not effective_confirm_write
    ):
        blocked.append("real write requires confirm_write")
        required_flags.append("--confirm-write")

    if plan.risk_level == "destructive":
        blocked.append("destructive GUI or file operations require a separate human checkpoint")
        required_flags.append("human-destructive-confirmation")

    unsafe_paths = [path for path in plan.output_paths if not is_safe_output_path(path)]
    if unsafe_paths:
        blocked.append("output paths must stay under outputs, examples, or tmp")

    if blocked:
        return SafetyDecision(
            allowed=False,
            reason="blocked by StarBridge safety guard",
            required_flags=sorted(set(required_flags)),
            blocked_because=blocked,
            risk_level=plan.risk_level,
            user_confirmation_required=bool(required_flags) or plan.requires_user_presence,
        )

    return SafetyDecision(
        allowed=True,
        reason="allowed by StarBridge safety guard",
        required_flags=sorted(set(required_flags)),
        risk_level=plan.risk_level,
        user_confirmation_required=plan.requires_user_presence,
    )


class ComputerUseProtocol(Protocol):
    def plan_to_human_readable_steps(self, plan: ActionPlan) -> list[str]: ...

    def generate_codex_gui_instructions(self, plan: ActionPlan) -> str: ...

    def record_gui_result(
        self,
        plan: ActionPlan,
        *,
        ok: bool,
        screenshot_paths: list[str] | None = None,
        created_files: list[str] | None = None,
        notes: str = "",
    ) -> ExecutionResult: ...

    def validate_screen_evidence(
        self, plan: ActionPlan, screenshot_paths: list[str]
    ) -> SafetyDecision: ...


class CodexComputerUseAdapter:
    def plan_to_human_readable_steps(self, plan: ActionPlan) -> list[str]:
        return [
            f"{step.step_id}. {step.instruction} Expected: {step.expected_screen_state}"
            for step in plan.gui_steps
        ]

    def generate_codex_gui_instructions(self, plan: ActionPlan) -> str:
        safety = evaluate_safety(plan)
        lines = [
            f"StarBridge GUI instructions for plan {plan.id}",
            f"Target app: {plan.app}",
            f"Goal: {plan.goal}",
            f"Risk level: {plan.risk_level}",
            f"Safety status: {'allowed' if safety.allowed else 'blocked'} - {safety.reason}",
        ]
        if safety.required_flags:
            lines.append(
                f"Required flags before real GUI execution: {', '.join(safety.required_flags)}"
            )
        lines.extend(
            [
                "Before starting, confirm the foreground window is the target app and no private file is open.",
                "Do not enter passwords, tokens, payment data, or account credentials.",
                "Do not overwrite user files. Use only the output paths listed below.",
                "Output paths:",
            ]
        )
        lines.extend([f"- {path}" for path in plan.output_paths] or ["- none"])
        lines.append("Steps:")
        for step in plan.gui_steps:
            lines.append(f"{step.step_id}. {step.instruction}")
            lines.append(f"   Check: {step.expected_screen_state}")
            if step.evidence_required:
                lines.append("   Evidence: take a screenshot after this step.")
            if step.requires_confirmation:
                lines.append("   Confirmation: wait for user confirmation before continuing.")
            if step.fallback_if_failed:
                lines.append(f"   Fallback: {step.fallback_if_failed}")
        lines.append(
            "When finished, record the result with starbridge gui-record and include screenshot paths."
        )
        return "\n".join(lines)

    def record_gui_result(
        self,
        plan: ActionPlan,
        *,
        ok: bool,
        screenshot_paths: list[str] | None = None,
        created_files: list[str] | None = None,
        notes: str = "",
    ) -> ExecutionResult:
        performed = [step.step_id for step in plan.gui_steps]
        return ExecutionResult(
            ok=ok,
            app=plan.app,
            action=plan.action,
            execution_mode=plan.execution_mode,
            performed_steps=performed if ok else [],
            created_files=created_files or [],
            skipped_steps=[] if ok else performed,
            evidence=[notes] if notes else [],
            screenshot_paths=screenshot_paths or [],
            message="GUI execution recorded" if ok else "GUI execution recorded as failed",
            next_recommended_action="verify output files"
            if ok
            else "review screenshots and rerun the failed step",
        )

    def validate_screen_evidence(
        self, plan: ActionPlan, screenshot_paths: list[str]
    ) -> SafetyDecision:
        if plan.needs_screenshot_evidence and not screenshot_paths:
            return SafetyDecision(
                allowed=False,
                reason="missing required screenshot evidence",
                blocked_because=["plan needs screenshot evidence"],
                risk_level=plan.risk_level,
                user_confirmation_required=False,
            )
        unsafe = [path for path in screenshot_paths if not is_safe_output_path(path)]
        if unsafe:
            return SafetyDecision(
                allowed=False,
                reason="screenshot evidence path is outside safe output roots",
                blocked_because=unsafe,
                risk_level=plan.risk_level,
                user_confirmation_required=False,
            )
        return SafetyDecision(
            True, "screen evidence paths are acceptable", risk_level=plan.risk_level
        )


class MockComputerUseAdapter(CodexComputerUseAdapter):
    def record_gui_result(
        self,
        plan: ActionPlan,
        *,
        ok: bool = True,
        screenshot_paths: list[str] | None = None,
        created_files: list[str] | None = None,
        notes: str = "mock execution",
    ) -> ExecutionResult:
        return super().record_gui_result(
            plan,
            ok=ok,
            screenshot_paths=screenshot_paths or ["outputs/evidence/mock.png"],
            created_files=created_files or [],
            notes=notes,
        )


class LocalScreenshotEvidenceStore:
    def __init__(self, root: str | Path = "outputs/logs") -> None:
        self.root = _resolve_repo_path(str(root))
        if not is_safe_output_path(_repo_relative(self.root)):
            raise ValueError("evidence store root must stay under outputs, examples, or tmp")
        self.root.mkdir(parents=True, exist_ok=True)

    def save_result(self, plan_id: str, result: ExecutionResult) -> Path:
        safe_plan_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in plan_id)
        path = self.root / f"{safe_plan_id}-{_now_id()}.json"
        path.write_text(
            json.dumps(sanitize(result.to_dict()), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path


def render_plan_summary(
    plan: ActionPlan, *, confirm_write: bool = False, allow_computer_use: bool = False
) -> dict[str, Any]:
    decision = evaluate_safety(
        plan, confirm_write=confirm_write, allow_computer_use=allow_computer_use
    )
    return sanitize(
        {
            "ok": decision.allowed,
            "plan": plan.to_dict(),
            "safety_decision": decision.to_dict(),
            "recommended_execution_mode": plan.execution_mode,
            "needs_allow_computer_use": plan.execution_mode in {"computer_use", "hybrid"},
            "needs_confirm_write": plan.risk_level in {"write", "destructive"} and not plan.dry_run,
            "gui_step_summary": [f"{step.step_id}: {step.instruction}" for step in plan.gui_steps],
        }
    )
