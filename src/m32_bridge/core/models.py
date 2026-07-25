"""Core domain models for the bridge safety boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RuntimeMode(StrEnum):
    OBSERVE = "OBSERVE"
    SOUNDCHECK = "SOUNDCHECK"
    LIVE = "LIVE"
    EMERGENCY = "EMERGENCY"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class VerificationState(StrEnum):
    EMULATOR = "EMULATOR"
    HARDWARE_UNVERIFIED = "HARDWARE_UNVERIFIED"
    HARDWARE_VERIFIED = "HARDWARE_VERIFIED"


class ConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    IDENTIFYING = "IDENTIFYING"
    SYNCING = "SYNCING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    WRITE_LOCKED = "WRITE_LOCKED"
    EMERGENCY_LOCKED = "EMERGENCY_LOCKED"


@dataclass(frozen=True)
class ConsoleIdentity:
    identity_id: str
    model: str
    firmware_version: str | None
    firmware_status: str
    endpoint_host: str
    endpoint_port: int
    source: str
    observed_at: datetime
    environment_label: str
    verification_state: VerificationState
    hardware_verified: bool = False

    def __post_init__(self) -> None:
        if self.firmware_status not in {"known", "unknown", "unsupported"}:
            raise ValueError("firmware_status must be known, unknown, or unsupported")
        if self.environment_label not in {"emulator", "hardware-unverified", "hardware-verified"}:
            raise ValueError("invalid environment_label")
        if self.environment_label == "emulator" and self.hardware_verified:
            raise ValueError("emulator targets cannot be hardware_verified")


@dataclass(frozen=True)
class ConsoleCapability:
    capability_id: str
    identity_id: str
    path_family: str
    supported: bool
    risk_class: RiskClass
    read_supported: bool
    write_supported: bool
    verified_by: str
    verified_at: datetime

    def __post_init__(self) -> None:
        if self.risk_class is RiskClass.R4 and self.write_supported:
            raise ValueError("R4 capabilities must remain non-writable")


@dataclass(frozen=True)
class StateValue:
    path: str
    raw_value: Any
    native_value: Any
    display_value: str
    unit: str | None
    value_type: str
    source: str
    revision: int
    observed_at: datetime
    fresh_until: datetime
    confidence: float
    stale: bool
    partial: bool
    support_status: str
    environment_label: str
    capability_id: str | None = None

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError("state paths must start with /")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if self.source not in {"console", "fake_m32", "external_emulator", "snapshot"}:
            raise ValueError("invalid source")
        if self.support_status not in {"supported", "unsupported", "unknown", "partial"}:
            raise ValueError("invalid support_status")

    def is_fresh(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return not self.stale and not self.partial and current <= self.fresh_until


@dataclass(frozen=True)
class StateRevision:
    revision: int
    path: str
    previous_revision: int | None
    observed_at: datetime
    change_source: str
    transaction_id: str | None = None
    manual_change_detected: bool = False

    def advances(self, current_revision: int) -> bool:
        return self.revision > current_revision


@dataclass(frozen=True)
class Operation:
    operation_id: str
    semantic_action: str
    target_path: str
    target_kind: str
    before_value: Any
    requested_value: Any
    rollback_value: Any
    bounds: dict[str, Any]
    risk_class: RiskClass
    affects_main: bool
    requires_readback: bool = True
    requires_reconciliation: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.target_path.startswith("/"):
            raise ValueError("operation target_path must start with /")
        if self.risk_class is RiskClass.R4:
            raise ValueError("R4 operations must not be represented as executable")


@dataclass
class Proposal:
    proposal_id: str
    created_at: datetime
    expires_at: datetime
    created_by: str
    base_snapshot_id: str
    base_revisions: dict[str, int]
    runtime_mode_at_creation: RuntimeMode
    operations: list[Operation]
    risk_summary: dict[str, Any]
    human_readable_summary: str
    rollback_candidates: dict[str, Any]
    status: str = "DRAFTED"
    proposal_digest: str | None = None
    server_computed: bool = True

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk_class: RiskClass
    reasons: list[str] = field(default_factory=list)
    required_confirmation: str | None = None
    approval_source: str | None = None


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    timestamp: datetime
    actor_host: str
    tool_name: str
    runtime_mode: RuntimeMode
    connection_lifecycle: ConnectionState
    verification_state: VerificationState
    approval_source: str
    approval_reference: str | None
    result: str
    operations: list[dict[str, Any]]

