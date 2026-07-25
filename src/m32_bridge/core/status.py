"""Console status service with verification labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from m32_bridge.core.models import ConsoleIdentity

EMULATOR_TARGETS = {"fake_m32", "external_emulator", "emulator"}
HARDWARE_TARGETS = {"hardware", "real_m32", "m32"}
READINESS_CHECKS = (
    "identity",
    "firmware",
    "expansion_card",
    "clock",
    "aes50",
    "card_sync",
    "routing",
    "network_isolation",
)
MANUAL_CHANGE_STEPS = (
    "read_initial_value",
    "manual_console_change",
    "read_changed_value",
    "prove_revision_timestamp_source_changed",
)
SAFE_WRITE_CHECKS = (
    "isolated_safe_write",
    "readback",
    "manual_conflict",
    "disconnect_reconnect",
    "targeted_rollback",
)


@dataclass(frozen=True)
class ConsoleStatus:
    connected: bool
    target_kind: str
    model: str
    firmware_status: str
    environment_label: str
    hardware_verified: bool
    write_ready: bool
    degraded_reasons: list[str]


def status_from_identity(identity: ConsoleIdentity, write_locked: bool = False) -> ConsoleStatus:
    reasons: list[str] = []
    if identity.firmware_status != "known":
        reasons.append("UNKNOWN_FIRMWARE")
    if write_locked:
        reasons.append("WRITE_LOCKED")
    hardware_verified = _hardware_verified_from_identity(identity)
    return ConsoleStatus(
        connected=True,
        target_kind=identity.source,
        model=identity.model,
        firmware_status=identity.firmware_status,
        environment_label=identity.environment_label,
        hardware_verified=hardware_verified,
        write_ready=not reasons and hardware_verified,
        degraded_reasons=reasons,
    )


def hardware_acceptance_readiness(evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _hardware_gate_result(evidence, required_checks=READINESS_CHECKS, gate="hardware_readiness")
    result["manual_change_status"] = "pending"
    result["safe_write_status"] = "pending"
    if evidence is None or result["status"] != "accepted":
        if result["status"] == "accepted":
            result["status"] = "pending"
            result["reason"] = "HARDWARE_EVIDENCE_INCOMPLETE"
        return result

    target_kind = _target_kind(evidence)
    manual_evidence = _nested_gate_evidence(evidence, "manual_change", target_kind)
    safe_write_evidence = _nested_gate_evidence(evidence, "safe_write", target_kind)
    manual_result = manual_change_challenge_status(manual_evidence)
    safe_write_result = hardware_safe_write_gate(safe_write_evidence)
    result["manual_change_status"] = manual_result["status"]
    result["safe_write_status"] = safe_write_result["status"]

    if manual_result["status"] == "accepted" and safe_write_result["status"] == "accepted":
        result["status"] = "accepted"
        result["reason"] = "HARDWARE_ACCEPTANCE_EVIDENCE_COMPLETE"
        result["hardware_verified"] = True
        result["production_live_ready"] = False
        result["ai_write_permitted"] = False
        return result

    result["status"] = "pending"
    result["reason"] = "HARDWARE_EVIDENCE_INCOMPLETE"
    result["hardware_verified"] = False
    result["production_live_ready"] = False
    result["ai_write_permitted"] = False
    return result


def manual_change_challenge_status(evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    base = _base_hardware_result("manual_change_challenge", evidence)
    base["required_steps"] = list(MANUAL_CHANGE_STEPS)
    if evidence is None:
        return base
    target_kind = _target_kind(evidence)
    if target_kind in EMULATOR_TARGETS:
        base["status"] = "not_available"
        base["reason"] = "EMULATOR_NOT_HARDWARE"
        base["target_kind"] = target_kind
        return base
    initial = evidence.get("initial") if isinstance(evidence.get("initial"), Mapping) else {}
    changed = evidence.get("changed") if isinstance(evidence.get("changed"), Mapping) else {}
    revision_changed = initial.get("revision") != changed.get("revision")
    timestamp_changed = initial.get("timestamp") != changed.get("timestamp")
    source_changed = initial.get("source") != changed.get("source")
    value_changed = initial.get("value") != changed.get("value")
    base.update(
        {
            "target_kind": target_kind,
            "revision_changed": revision_changed,
            "timestamp_changed": timestamp_changed,
            "source_changed": source_changed,
            "value_changed": value_changed,
        }
    )
    if target_kind not in HARDWARE_TARGETS or not all((revision_changed, timestamp_changed, source_changed, value_changed)):
        base["status"] = "pending"
        base["reason"] = "MANUAL_CHANGE_EVIDENCE_INCOMPLETE"
        return base
    base["status"] = "accepted"
    base["reason"] = "MANUAL_CHANGE_EVIDENCE_COMPLETE"
    return base


def hardware_safe_write_gate(evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _hardware_gate_result(evidence, required_checks=SAFE_WRITE_CHECKS, gate="hardware_safe_write")
    if result["status"] == "accepted":
        result["reason"] = "SAFE_WRITE_EVIDENCE_COMPLETE"
        result["ai_write_permitted"] = True
    else:
        result["ai_write_permitted"] = False
    result["hardware_verified"] = False
    result["production_live_ready"] = False
    return result


def _hardware_gate_result(evidence: Mapping[str, Any] | None, *, required_checks: tuple[str, ...], gate: str) -> dict[str, Any]:
    result = _base_hardware_result(gate, evidence)
    result["required_checks"] = list(required_checks)
    result["checklist"] = _checklist(evidence, required_checks)
    if evidence is None:
        return result
    target_kind = _target_kind(evidence)
    result["target_kind"] = target_kind
    if target_kind in EMULATOR_TARGETS:
        result["status"] = "not_available"
        result["reason"] = "EMULATOR_NOT_HARDWARE"
        return result
    checks = evidence.get("checks") if isinstance(evidence.get("checks"), Mapping) else {}
    passed = {check for check in required_checks if checks.get(check) is True}
    missing = sorted(set(required_checks) - passed)
    result["missing_checks"] = missing
    if target_kind not in HARDWARE_TARGETS or missing or not evidence.get("artifact_id"):
        result["status"] = "pending"
        result["reason"] = "HARDWARE_EVIDENCE_INCOMPLETE"
        return result
    result["status"] = "accepted"
    result["reason"] = "HARDWARE_EVIDENCE_COMPLETE"
    return result


def _base_hardware_result(gate: str, evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": "pending",
        "reason": "HARDWARE_EVIDENCE_NOT_AVAILABLE" if evidence is None else "HARDWARE_EVIDENCE_INCOMPLETE",
        "target_kind": str(evidence.get("target_kind", "not_configured")) if evidence else "not_configured",
        "hardware_verified": False,
        "production_live_ready": False,
        "ai_write_permitted": False,
        "write_operations": [],
        "osc_writes_sent": 0,
    }


def _checklist(evidence: Mapping[str, Any] | None, checks: tuple[str, ...]) -> list[dict[str, str]]:
    provided = evidence.get("checks") if evidence and isinstance(evidence.get("checks"), Mapping) else {}
    return [
        {"check": check, "status": "passed" if provided.get(check) is True else "not_available"}
        for check in checks
    ]


def _target_kind(evidence: Mapping[str, Any]) -> str:
    return str(evidence.get("target_kind", "unknown"))


def _nested_gate_evidence(evidence: Mapping[str, Any], key: str, target_kind: str) -> Mapping[str, Any] | None:
    nested = evidence.get(key)
    if not isinstance(nested, Mapping):
        return None
    merged = dict(nested)
    merged.setdefault("target_kind", target_kind)
    return merged


def _hardware_verified_from_identity(identity: ConsoleIdentity) -> bool:
    if identity.source in EMULATOR_TARGETS or identity.environment_label == "emulator":
        return False
    if identity.verification_state.value != "HARDWARE_VERIFIED":
        return False
    return bool(identity.hardware_verified)
