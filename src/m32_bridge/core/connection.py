"""Fail-closed connection health and reconnect reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, sleep as default_sleep
from typing import Callable

from m32_bridge.osc.client import OscClient


@dataclass(frozen=True)
class ConnectionHealthResult:
    status: str
    write_locked: bool
    reconciled: bool
    reason: str | None = None
    attempts: int = 1


@dataclass
class ConnectionController:
    client: OscClient
    required_paths: tuple[str, ...]
    freshness_seconds: float = 1.0
    write_locked: bool = True
    reconciled: bool = False
    connected: bool = False
    stale: bool = False
    identity: dict[str, object] = field(default_factory=dict)
    last_reconciled_at: float | None = None
    last_error: str | None = None

    def check_connection_health(self) -> ConnectionHealthResult:
        if self._is_stale():
            self._lock("STALE_STATE", connected=True, stale=True)
            return ConnectionHealthResult("stale", True, False, "STALE_STATE")
        try:
            self.client.transport.request("/info")
        except Exception:
            self._lock("HEARTBEAT_TIMEOUT", connected=False, stale=False)
            return ConnectionHealthResult("disconnected", True, False, "HEARTBEAT_TIMEOUT")
        self.connected = True
        if not self.reconciled:
            self.write_locked = True
            return ConnectionHealthResult("unreconciled", True, False, "RECONCILIATION_REQUIRED")
        self.write_locked = False
        return ConnectionHealthResult("connected", False, True, None)

    def reconcile_after_reconnect(self) -> ConnectionHealthResult:
        try:
            info = self.client.transport.request("/info").arguments
            for path in self.required_paths:
                self.client.read_value(path)
        except Exception:
            self._lock("RECONCILIATION_FAILED", connected=False, stale=False)
            return ConnectionHealthResult("disconnected", True, False, "RECONCILIATION_FAILED")

        self.identity = {
            "model": str(info[0]) if len(info) > 0 else None,
            "firmware": str(info[1]) if len(info) > 1 else None,
            "revision": int(info[2]) if len(info) > 2 else None,
            "hardware_verified": False,
        }
        self.connected = True
        self.reconciled = True
        self.stale = False
        self.write_locked = False
        self.last_error = None
        self.last_reconciled_at = monotonic()
        return ConnectionHealthResult("reconciled", False, True, None)

    def reconnect_with_backoff(
        self,
        *,
        max_attempts: int = 3,
        initial_backoff_seconds: float = 0.05,
        max_backoff_seconds: float = 0.2,
        sleep: Callable[[float], None] = default_sleep,
    ) -> ConnectionHealthResult:
        attempts = max(1, max_attempts)
        delay = initial_backoff_seconds
        for attempt in range(1, attempts + 1):
            result = self.reconcile_after_reconnect()
            if result.status == "reconciled":
                return ConnectionHealthResult("reconciled", False, True, None, attempts=attempt)
            if attempt < attempts:
                sleep(delay)
                delay = min(delay * 2, max_backoff_seconds)
        self._lock("RECONNECT_FAILED", connected=False, stale=False)
        return ConnectionHealthResult("disconnected", True, False, "RECONNECT_FAILED", attempts=attempts)

    def require_reconciled_for_writes(self) -> dict[str, object]:
        if self.last_reconciled_at is None:
            return {"allowed": False, "reason": "RECONCILIATION_REQUIRED"}
        if not self.connected:
            return {"allowed": False, "reason": "DISCONNECTED"}
        if self.stale:
            return {"allowed": False, "reason": "STALE_STATE"}
        if not self.reconciled or self.write_locked:
            return {"allowed": False, "reason": "RECONCILIATION_REQUIRED"}
        return {"allowed": True, "reason": None}

    def request_unlock(self) -> dict[str, object]:
        decision = self.require_reconciled_for_writes()
        if not decision["allowed"]:
            self.write_locked = True
            return {"unlocked": False, "write_locked": True, "reason": "RECONCILIATION_REQUIRED"}
        self.write_locked = False
        return {"unlocked": True, "write_locked": False, "reason": None}

    def run_guarded_write(self, write: Callable[[], object]) -> dict[str, object]:
        decision = self.require_reconciled_for_writes()
        if not decision["allowed"]:
            return {"status": "DENIED", "error_code": str(decision["reason"])}
        write()
        return {"status": "ALLOWED", "error_code": None}

    def mark_reconciliation_stale_for_test(self) -> None:
        self.last_reconciled_at = monotonic() - self.freshness_seconds - 0.001

    def _is_stale(self) -> bool:
        return self.last_reconciled_at is not None and monotonic() - self.last_reconciled_at > self.freshness_seconds

    def _lock(self, reason: str, *, connected: bool, stale: bool) -> None:
        self.connected = connected
        self.stale = stale
        self.reconciled = False
        self.write_locked = True
        self.last_error = reason
