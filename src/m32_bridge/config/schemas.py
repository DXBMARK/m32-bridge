"""Contract schema loading and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = PROJECT_ROOT / "specs" / "001-m32-mcp-bridge" / "contracts"


def load_schema(name: str) -> dict[str, Any]:
    path = CONTRACTS_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        schema = json.load(fh)
    Draft202012Validator.check_schema(schema)
    return schema


def validate_with_schema(instance: Any, schema_name: str) -> None:
    Draft202012Validator(load_schema(schema_name)).validate(instance)

