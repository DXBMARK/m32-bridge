"""Failure injection controls for Fake M32."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FailureProfile:
    drop_next: bool = False
    malformed_next: bool = False
    duplicate_next: bool = False
    out_of_order_next: bool = False
    out_of_order_delay_ms: int = 75
    delayed_ms: int = 0
    disconnect: bool = False

    def consume_drop(self) -> bool:
        value = self.drop_next
        self.drop_next = False
        return value

    def consume_malformed(self) -> bool:
        value = self.malformed_next
        self.malformed_next = False
        return value

    def consume_duplicate(self) -> bool:
        value = self.duplicate_next
        self.duplicate_next = False
        return value

    def consume_out_of_order(self) -> bool:
        value = self.out_of_order_next
        self.out_of_order_next = False
        return value
