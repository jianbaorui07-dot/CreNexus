from __future__ import annotations

from typing import Any, Protocol


class ModelContractClient(Protocol):
    """Transport-neutral client boundary implemented by KORYAO integrations."""

    def status(self) -> dict[str, Any]: ...

    def plan(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def repair(self, request: dict[str, Any]) -> dict[str, Any]: ...
