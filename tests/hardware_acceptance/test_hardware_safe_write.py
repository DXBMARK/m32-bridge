from __future__ import annotations

from m32_bridge.core.status import hardware_safe_write_gate


REQUIRED_SAFE_WRITE_CHECKS = {
    "isolated_safe_write",
    "readback",
    "manual_conflict",
    "disconnect_reconnect",
    "targeted_rollback",
}


def test_safe_write_hardware_gate_is_structured_pending_without_explicit_evidence():
    result = hardware_safe_write_gate()

    assert result["status"] == "pending"
    assert result["reason"] == "HARDWARE_EVIDENCE_NOT_AVAILABLE"
    assert result["hardware_verified"] is False
    assert result["ai_write_permitted"] is False
    assert result["production_live_ready"] is False
    assert result["write_operations"] == []
    assert set(result["required_checks"]) == REQUIRED_SAFE_WRITE_CHECKS


def test_safe_write_gate_rejects_fake_and_external_emulator_as_hardware():
    for target_kind in ("fake_m32", "external_emulator"):
        result = hardware_safe_write_gate({"target_kind": target_kind, "checks": {check: True for check in REQUIRED_SAFE_WRITE_CHECKS}})

        assert result["status"] == "not_available"
        assert result["reason"] == "EMULATOR_NOT_HARDWARE"
        assert result["hardware_verified"] is False
        assert result["ai_write_permitted"] is False
        assert result["write_operations"] == []


def test_safe_write_gate_requires_all_manual_evidence_entries():
    result = hardware_safe_write_gate(
        {
            "target_kind": "hardware",
            "artifact_id": "manual-safe-write-001",
            "operator": "engineer",
            "checks": {"isolated_safe_write": True, "readback": True},
        }
    )

    assert result["status"] == "pending"
    assert result["reason"] == "HARDWARE_EVIDENCE_INCOMPLETE"
    assert result["hardware_verified"] is False
    assert result["missing_checks"] == sorted(REQUIRED_SAFE_WRITE_CHECKS - {"isolated_safe_write", "readback"})
    assert result["write_operations"] == []


def test_complete_safe_write_gate_accepts_write_readiness_without_hardware_verified_claim():
    result = hardware_safe_write_gate(
        {
            "target_kind": "hardware",
            "artifact_id": "manual-safe-write-accepted",
            "operator": "engineer",
            "checks": {check: True for check in REQUIRED_SAFE_WRITE_CHECKS},
        }
    )

    assert result["status"] == "accepted"
    assert result["reason"] == "SAFE_WRITE_EVIDENCE_COMPLETE"
    assert result["hardware_verified"] is False
    assert result["ai_write_permitted"] is True
    assert result["production_live_ready"] is False
    assert result["missing_checks"] == []
