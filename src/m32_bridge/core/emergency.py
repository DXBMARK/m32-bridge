"""Emergency write-lock state machine."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.core.connection import ConnectionController
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore


@dataclass
class EmergencyController:
    runtime_mode: RuntimeMode = RuntimeMode.OBSERVE
    write_locked: bool = True
    automation_stopped: bool = False
    emergency_active: bool = False
    reconciliation_required: bool = True

    def lock_writes(self, reason: str = "operator_lock") -> dict[str, object]:
        self.write_locked = True
        return {
            "status": "WRITE_LOCKED",
            "reason": reason,
            "runtime_mode": self.runtime_mode.value,
            "write_locked": True,
            "osc_writes_sent": 0,
        }

    def enter_emergency(self, *, store: ProposalStore, reason: str) -> dict[str, object]:
        cancelled = store.cancel_pending_by_emergency()
        self.runtime_mode = RuntimeMode.EMERGENCY
        self.write_locked = True
        self.automation_stopped = True
        self.emergency_active = True
        self.reconciliation_required = True
        return {
            "status": "EMERGENCY_LOCKED",
            "reason": reason,
            "runtime_mode": self.runtime_mode.value,
            "write_locked": True,
            "automation_stopped": True,
            "emergency_active": True,
            "cancelled_proposals": cancelled,
            "osc_writes_sent": 0,
        }

    def exit_emergency_to_observe(self) -> dict[str, object]:
        self.runtime_mode = RuntimeMode.OBSERVE
        self.write_locked = True
        self.automation_stopped = False
        self.emergency_active = False
        self.reconciliation_required = True
        return {
            "status": "OBSERVE",
            "runtime_mode": RuntimeMode.OBSERVE.value,
            "write_locked": True,
            "automation_stopped": False,
            "emergency_active": False,
            "reconciliation_required": True,
            "osc_writes_sent": 0,
        }

    def unlock_writes_after_reconciliation(self, connection: ConnectionController) -> dict[str, object]:
        if self.runtime_mode is not RuntimeMode.OBSERVE:
            self.write_locked = True
            return {"unlocked": False, "write_locked": True, "runtime_mode": self.runtime_mode.value, "reason": "OBSERVE_REQUIRED"}
        if self.reconciliation_required:
            self.reconciliation_required = False
            self.write_locked = True
            return {"unlocked": False, "write_locked": True, "runtime_mode": RuntimeMode.OBSERVE.value, "reason": "RECONCILIATION_REQUIRED"}
        decision = connection.require_reconciled_for_writes()
        if not decision["allowed"]:
            self.write_locked = True
            return {"unlocked": False, "write_locked": True, "runtime_mode": RuntimeMode.OBSERVE.value, "reason": decision["reason"]}
        self.write_locked = False
        return {"unlocked": True, "write_locked": False, "runtime_mode": RuntimeMode.OBSERVE.value, "reason": None}
