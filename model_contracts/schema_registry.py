from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

SCHEMA_NAMES = (
    "common.schema.json",
    "plan_request.schema.json",
    "plan_response.schema.json",
    "evaluate_request.schema.json",
    "evaluate_response.schema.json",
    "repair_request.schema.json",
    "repair_response.schema.json",
    "model_status.schema.json",
)


def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown KORYAO model contract schema: {name}")
    resource = files("model_contracts.schemas").joinpath(name)
    return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))
