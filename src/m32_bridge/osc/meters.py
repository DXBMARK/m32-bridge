"""Meter decoding helpers."""

from __future__ import annotations


def parse_meter_summary(payload: str) -> dict[str, float]:
    if not payload:
        return {}
    result: dict[str, float] = {}
    for item in payload.split(","):
        if not item:
            continue
        path, value = item.split("=", 1)
        result[path] = float(value)
    return result


def meter_position(path: str) -> str:
    if "/pre" in path:
        return "pre"
    if "/post" in path:
        return "post"
    return "summary"

