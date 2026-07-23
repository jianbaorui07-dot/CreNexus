from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseModelProvider(ABC):
    """Public provider surface; concrete model logic stays in a private repository."""

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @abstractmethod
    def status(self) -> dict[str, Any]: ...

    @abstractmethod
    def plan(self, request: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def repair(self, request: dict[str, Any]) -> dict[str, Any]: ...
