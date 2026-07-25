"""Read synchronization and reconciliation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.osc.discovery import read_state_value
from m32_bridge.osc.transport import OscTransport
from m32_bridge.state.cache import StateCache


@dataclass
class ReconciliationResult:
    path: str
    revision: int
    manual_change_detected: bool
    source: str


def reconcile_path(cache: StateCache, transport: OscTransport, path: str) -> ReconciliationResult:
    value = read_state_value(transport, path)
    revision = cache.apply(value, change_source="console")
    return ReconciliationResult(
        path=path,
        revision=revision.revision,
        manual_change_detected=revision.manual_change_detected,
        source=value.source,
    )

