"""Event profile loading and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from m32_bridge.config.schemas import validate_with_schema


def load_event_profile(profile: Mapping[str, Any] | str | Path | None) -> dict[str, Any] | None:
    """Load and validate an event profile from an in-memory mapping or file path."""
    if profile is None:
        return None
    if isinstance(profile, Mapping):
        loaded = deepcopy(dict(profile))
    else:
        loaded = _load_profile_file(Path(profile))
    validate_with_schema(loaded, "event-profile.schema.json")
    return loaded


def _load_profile_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix.lower() in {".yaml", ".yml"}:
            loaded = yaml.safe_load(fh)
        else:
            loaded = json.load(fh)
    if not isinstance(loaded, dict):
        raise ValueError("event profile must be a JSON/YAML object")
    return loaded
