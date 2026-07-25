"""Remote-change subscription renewal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from m32_bridge.osc.transport import OscTransport


@dataclass
class XRemoteSubscription:
    transport: OscTransport
    renewal_seconds: int = 8
    last_renewed_at: datetime | None = None
    write_locked: bool = False

    def renew(self) -> None:
        self.transport.request("/xremote")
        self.last_renewed_at = datetime.now(UTC)
        self.write_locked = False

    def check_fail_safe(self, now: datetime | None = None) -> bool:
        if self.last_renewed_at is None:
            self.write_locked = True
        else:
            current = now or datetime.now(UTC)
            self.write_locked = current - self.last_renewed_at > timedelta(seconds=self.renewal_seconds)
        return self.write_locked

