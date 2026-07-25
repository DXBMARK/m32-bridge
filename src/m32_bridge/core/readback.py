"""Readback verification."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.osc.client import OscClient


@dataclass(frozen=True)
class ReadbackResult:
    matched: bool
    expected: object
    actual: object
    path: str


def verify_readback(client: OscClient, path: str, expected: object) -> ReadbackResult:
    args = client.read_value(path)
    actual = args[0] if args else None
    return ReadbackResult(matched=actual == expected, expected=expected, actual=actual, path=path)

