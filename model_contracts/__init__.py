"""Public KORYAO closed-model protocol boundary.

This package intentionally contains only versioned contracts, validation
helpers, and abstract interfaces. Model implementations, prompts, training
code, data, and weights belong outside the KORYAO Basic repository.
"""

from model_contracts.constants import CONTRACT_VERSION
from model_contracts.schema_registry import SCHEMA_NAMES, load_schema
from model_contracts.validation import (
    ModelContractValidationError,
    ensure_plan_response,
    validate_plan_response,
)

__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_NAMES",
    "ModelContractValidationError",
    "ensure_plan_response",
    "load_schema",
    "validate_plan_response",
]
