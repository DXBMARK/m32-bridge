"""Rate-limit and per-resource serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class RateLimiter:
    min_interval_ms: int
    _last_by_resource: dict[str, datetime] = field(default_factory=dict)

    def allow(self, resource: str, now: datetime) -> bool:
        last = self._last_by_resource.get(resource)
        if last is not None and now - last < timedelta(milliseconds=self.min_interval_ms):
            return False
        self._last_by_resource[resource] = now
        return True


def live_fader_delta_allowed(before_db: float, requested_db: float, limit_db: float = 3.0) -> bool:
    return abs(requested_db - before_db) <= limit_db

