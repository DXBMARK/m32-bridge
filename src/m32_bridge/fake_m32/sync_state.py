"""Clock, AES50, and expansion-card sync seed state for Fake M32."""

from __future__ import annotations


def sync_state() -> dict[str, str]:
    return {
        "clock_rate": "48k",
        "clock_source": "internal",
        "clock_mode": "master",
        "aes50_a": "locked",
        "aes50_b": "not_connected",
        "expansion_card_sync": "locked",
    }

