"""Semantic write allowlist for console write operations."""

from __future__ import annotations

import re
from functools import lru_cache


_CHANNEL = r"(?:[0-2][1-9]|3[0-2]|[1-9])"
_BUS = r"(?:0?[1-9]|1[0-6])"
_HEADAMP = r"(?:[0-9]{1,3})"

_ACTION_PATTERNS = {
    "label_set": [
        rf"^/ch/{_CHANNEL}/config/name$",
        rf"^/bus/{_BUS}/config/name$",
    ],
    "fader_set": [
        rf"^/ch/{_CHANNEL}/mix/fader$",
        rf"^/bus/{_BUS}/mix/fader$",
    ],
    "mute_set": [
        rf"^/ch/{_CHANNEL}/mix/on$",
        rf"^/bus/{_BUS}/mix/on$",
    ],
    "send_level_set": [
        rf"^/ch/{_CHANNEL}/mix/{_BUS}/level$",
    ],
    "eq_adjust": [
    ],
    "dynamics_adjust": [
    ],
    "talkback_momentary": [
        r"^/talkback/on$",
    ],
    "talkback_configure": [
        r"^/talkback/(?:source|level|dim|destination)$",
    ],
    "headamp_set": [
        rf"^/headamp/{_HEADAMP}/gain$",
        rf"^/ch/{_CHANNEL}/headamp/gain$",
    ],
    "routing_set": [
        rf"^/routing/(?:in|out|aux|card)/{_CHANNEL}$",
    ],
    "recall_scene": [
        r"^/scene/recall$",
    ],
    "bulk_update": [
    ],
}


@lru_cache(maxsize=None)
def _compiled(action: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in _ACTION_PATTERNS.get(action, ()))


def is_semantic_write_allowed(action: str, path: str) -> bool:
    if not path.startswith("/") or path.startswith("/raw"):
        return False
    return any(pattern.fullmatch(path) for pattern in _compiled(action))
