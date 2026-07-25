"""Deterministic RTA fixtures for Fake M32."""

from __future__ import annotations


def rta_source() -> str:
    return "main_st"


def rta_bands() -> list[float]:
    return [-60.0 + (index % 8) for index in range(100)]

