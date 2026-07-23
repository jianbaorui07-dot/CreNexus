from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from model_contracts.constants import CONTRACT_VERSION

_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_COMMAND_MARKERS = (
    "powershell",
    "cmd.exe",
    "bash -c",
    "/bin/sh",
    "python -c",
    "subprocess",
    "os.system",
)
_FORBIDDEN_STEP_KEYS = frozenset(
    {
        "absolutePath",
        "code",
        "command",
        "executable",
        "filePath",
        "path",
        "powershell",
        "python",
        "script",
        "shell",
        "url",
    }
)


class ModelContractValidationError(ValueError):
    """A model response violates the public KORYAO execution boundary."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def _dangerous_string(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(
        _ABSOLUTE_PATH.match(value)
        or _URI.match(value)
        or ".." in value.replace("\\", "/").split("/")
        or any(marker in normalized for marker in _COMMAND_MARKERS)
        or "\x00" in value
    )


def _scan_step_value(value: Any, location: str, errors: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_STEP_KEYS:
                errors.append(f"{location}.{key_text} is forbidden")
            _scan_step_value(child, f"{location}.{key_text}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_step_value(child, f"{location}[{index}]", errors)
    elif isinstance(value, str) and _dangerous_string(value):
        errors.append(f"{location} contains a command, URI, or filesystem path")


def _has_dependency_cycle(steps: list[Mapping[str, Any]]) -> bool:
    graph = {
        str(step.get("stepId", "")): tuple(str(item) for item in step.get("dependsOn", []))
        for step in steps
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> bool:
        if step_id in visiting:
            return True
        if step_id in visited:
            return False
        visiting.add(step_id)
        if any(visit(dependency) for dependency in graph.get(step_id, ())):
            return True
        visiting.remove(step_id)
        visited.add(step_id)
        return False

    return any(visit(step_id) for step_id in graph)


def validate_plan_response(
    request: Mapping[str, Any],
    response: Mapping[str, Any],
) -> list[str]:
    """Apply cross-document safety rules that JSON Schema cannot express alone."""

    errors: list[str] = []
    if request.get("schema") != CONTRACT_VERSION:
        errors.append("request schema version is unsupported")
    if response.get("schema") != CONTRACT_VERSION:
        errors.append("response schema version is unsupported")
    if response.get("requestId") != request.get("requestId"):
        errors.append("response requestId does not match the request")

    adapter_actions: dict[tuple[str, str], Mapping[str, Any]] = {}
    for adapter in request.get("availableAdapters", []):
        if not isinstance(adapter, Mapping):
            continue
        adapter_id = str(adapter.get("adapterId", ""))
        for action in adapter.get("actions", []):
            if isinstance(action, Mapping):
                adapter_actions[(adapter_id, str(action.get("action", "")))] = action

    constraints = request.get("constraints")
    if not isinstance(constraints, Mapping):
        constraints = {}
    max_steps = int(constraints.get("maxSteps", 0) or 0)
    safe_roots = {str(item) for item in constraints.get("safeRootRefs", [])}

    raw_steps = response.get("steps")
    steps = (
        [step for step in raw_steps if isinstance(step, Mapping)]
        if isinstance(raw_steps, list)
        else []
    )
    if not steps:
        errors.append("response must contain at least one structured step")
    if max_steps and len(steps) > max_steps:
        errors.append("response exceeds constraints.maxSteps")

    step_ids = [str(step.get("stepId", "")) for step in steps]
    known_step_ids = set(step_ids)
    if len(known_step_ids) != len(step_ids):
        errors.append("stepId values must be unique")

    write_present = False
    for index, step in enumerate(steps):
        location = f"steps[{index}]"
        adapter_id = str(step.get("adapterId", ""))
        action_id = str(step.get("action", ""))
        action = adapter_actions.get((adapter_id, action_id))
        if action is None:
            errors.append(f"{location} selects an adapter action outside the request allowlist")
        else:
            is_write = action.get("sideEffect") == "write"
            write_present = write_present or is_write
            if bool(action.get("requiresConfirmation")) and not bool(
                step.get("requiresConfirmation")
            ):
                errors.append(f"{location} removed the required confirmation gate")

        dependencies = [str(item) for item in step.get("dependsOn", [])]
        if str(step.get("stepId", "")) in dependencies:
            errors.append(f"{location} cannot depend on itself")
        for dependency in dependencies:
            if dependency not in known_step_ids:
                errors.append(f"{location} references an unknown dependency")

        safe_root_ref = step.get("safeRootRef")
        if safe_root_ref is not None and str(safe_root_ref) not in safe_roots:
            errors.append(f"{location}.safeRootRef is outside the request allowlist")
        _scan_step_value(step, location, errors)

    if _has_dependency_cycle(steps):
        errors.append("step dependencies must be acyclic")
    if write_present and not bool(response.get("requiresConfirmation")):
        errors.append("a plan containing writes must require confirmation")

    safety = response.get("safety")
    if not isinstance(safety, Mapping):
        errors.append("response safety declaration is missing")
    else:
        required_false = (
            "confirmationGateBypass",
            "directExecution",
            "directFileAccess",
            "shellCommandsIncluded",
        )
        for field in required_false:
            if safety.get(field) is not False:
                errors.append(f"safety.{field} must be false")
    return errors


def ensure_plan_response(
    request: Mapping[str, Any],
    response: Mapping[str, Any],
) -> None:
    errors = validate_plan_response(request, response)
    if errors:
        raise ModelContractValidationError(errors)
