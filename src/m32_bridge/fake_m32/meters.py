"""Deterministic meter fixtures for Fake M32."""

from __future__ import annotations


def meter_fixture() -> dict[str, float]:
    return {
        "/meters/ch/01/pre": -18.0,
        "/meters/ch/01/post": -20.0,
        "/meters/main/st": -12.0,
    }

