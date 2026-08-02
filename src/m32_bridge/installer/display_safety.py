"""Terminal-safe rendering for values outside the renderer's trust boundary."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_ESCAPED_SEQUENCE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)?"  # OSC
    r"|[P_^][^\x1b]*(?:\x1b\\)?"  # DCS, APC, PM
    r"|[@-_]"  # single-character escape
    r")"
)
_WHITESPACE = re.compile(r"\s+")


def sanitize_display_value(value: Any, *, max_length: int = 256) -> str:
    """Return a bounded, single-line value that cannot control a terminal."""

    text = str(value)
    text = _ESCAPED_SEQUENCE.sub("", text)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = "".join(
        character
        for character in text
        if character != "\x1b"
        and unicodedata.category(character) not in {"Cc", "Cf", "Cs"}
    )
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) > max_length:
        text = text[: max(max_length - 1, 0)].rstrip() + "…"
    return text
