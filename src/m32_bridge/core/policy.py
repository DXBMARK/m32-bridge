"""Server-side policy enforcement for proposal and write eligibility."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.core.models import PolicyDecision, RiskClass, RuntimeMode

PROHIBITED_ACTIONS = {
    "phantom_enable",
    "sample_rate_change",
    "clock_change",
    "firmware_update",
    "shutdown_console",
    "format_sd",
    "raw_osc",
    "arbitrary_path",
}

R3_ACTIONS = {"headamp_set", "routing_set", "recall_scene", "bulk_update", "talkback_configure"}


@dataclass(frozen=True)
class PolicyRequest:
    runtime_mode: RuntimeMode
    risk_class: RiskClass
    semantic_action: str
    target_path: str
    write_lock: bool = False
    stale_state: bool = False
    unsupported_capability: bool = False
    unknown_firmware: bool = False
    manual_conflict: bool = False
    affects_main: bool = False
    live_delta_db: float | None = None
    has_snapshot: bool = False


def evaluate_policy(request: PolicyRequest) -> PolicyDecision:
    reasons: list[str] = []
    if request.runtime_mode is RuntimeMode.EMERGENCY:
        reasons.append("EMERGENCY_LOCKED")
    if request.runtime_mode is RuntimeMode.OBSERVE:
        reasons.append("OBSERVE_READ_ONLY")
    if request.write_lock:
        reasons.append("WRITE_LOCKED")
    if request.stale_state:
        reasons.append("STALE_STATE")
    if request.unsupported_capability:
        reasons.append("CAPABILITY_MISMATCH")
    if request.unknown_firmware:
        reasons.append("UNKNOWN_FIRMWARE")
    if request.manual_conflict:
        reasons.append("PROPOSAL_CONFLICT")
    if request.risk_class is RiskClass.R4 or request.semantic_action in PROHIBITED_ACTIONS:
        reasons.append("R4_BLOCKED")
    if request.semantic_action in R3_ACTIONS and request.risk_class is not RiskClass.R3:
        reasons.append("RISK_CLASS_MISMATCH")
    if request.risk_class is RiskClass.R3 and request.runtime_mode is not RuntimeMode.SOUNDCHECK:
        reasons.append("R3_MODE_DENIED")
    if request.risk_class is RiskClass.R3 and not request.has_snapshot:
        reasons.append("SNAPSHOT_REQUIRED")
    if request.affects_main:
        reasons.append("MAIN_PROTECTED")
    if request.runtime_mode is RuntimeMode.LIVE and request.live_delta_db is not None and abs(request.live_delta_db) > 3:
        reasons.append("LIVE_DELTA_EXCEEDED")
    return PolicyDecision(
        allowed=not reasons,
        risk_class=request.risk_class,
        reasons=reasons,
        required_confirmation="mcp_host_confirmation",
        approval_source="mcp_host_confirmation",
    )

