"""In-memory authoritative state cache with monotonic revisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from m32_bridge.core.models import StateRevision, StateValue


@dataclass
class StateCache:
    values: dict[str, StateValue] = field(default_factory=dict)
    revisions: dict[str, int] = field(default_factory=dict)

    def apply(self, value: StateValue, change_source: str = "console", transaction_id: str | None = None) -> StateRevision:
        current = self.revisions.get(value.path, -1)
        manual = change_source == "console" and transaction_id is None and value.path in self.values
        if value.revision <= current:
            return StateRevision(
                revision=current,
                path=value.path,
                previous_revision=current,
                observed_at=value.observed_at,
                change_source="duplicate_or_out_of_order",
                transaction_id=transaction_id,
                manual_change_detected=False,
            )
        previous = current if current >= 0 else None
        self.values[value.path] = value
        self.revisions[value.path] = value.revision
        return StateRevision(
            revision=value.revision,
            path=value.path,
            previous_revision=previous,
            observed_at=value.observed_at,
            change_source=change_source,
            transaction_id=transaction_id,
            manual_change_detected=manual,
        )

    def get(self, path: str) -> StateValue | None:
        return self.values.get(path)

    def stale_paths(self, now: datetime) -> list[str]:
        return [path for path, value in self.values.items() if not value.is_fresh(now)]

