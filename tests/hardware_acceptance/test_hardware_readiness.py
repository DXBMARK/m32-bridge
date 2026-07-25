from __future__ import annotations

from m32_bridge.core.status import hardware_acceptance_readiness


REQUIRED_READINESS_CHECKS = {
    "identity",
    "firmware",
    "expansion_card",
    "clock",
    "aes50",
    "card_sync",
    "routing",
    "network_isolation",
}


def test_hardware_readiness_checklist_is_structured_pending_without_real_hardware_evidence():
    result = hardware_acceptance_readiness()

    assert result["status"] == "pending"
    assert result["reason"] == "HARDWARE_EVIDENCE_NOT_AVAILABLE"
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["write_operations"] == []
    assert result["osc_writes_sent"] == 0
    assert set(result["required_checks"]) == REQUIRED_READINESS_CHECKS
    assert all(entry["status"] == "not_available" for entry in result["checklist"])


def test_emulator_targets_never_grant_hardware_verification():
    for target_kind in ("fake_m32", "external_emulator", "emulator"):
        result = hardware_acceptance_readiness({"target_kind": target_kind, "checks": {check: True for check in REQUIRED_READINESS_CHECKS}})

        assert result["status"] == "not_available"
        assert result["reason"] == "EMULATOR_NOT_HARDWARE"
        assert result["target_kind"] == target_kind
        assert result["hardware_verified"] is False
        assert result["production_live_ready"] is False
        assert result["write_operations"] == []


def test_partial_or_unsigned_hardware_evidence_remains_pending_and_read_only():
    partial = hardware_acceptance_readiness(
        {
            "target_kind": "hardware",
            "artifact_id": "manual-session-001",
            "checks": {"identity": True, "firmware": True},
        }
    )

    assert partial["status"] == "pending"
    assert partial["reason"] == "HARDWARE_EVIDENCE_INCOMPLETE"
    assert partial["hardware_verified"] is False
    assert partial["missing_checks"] == sorted(REQUIRED_READINESS_CHECKS - {"identity", "firmware"})
    assert partial["write_operations"] == []
    assert partial["osc_writes_sent"] == 0


def test_complete_hardware_acceptance_evidence_can_verify_hardware_only_when_all_gates_pass():
    result = hardware_acceptance_readiness(
        {
            "target_kind": "hardware",
            "artifact_id": "hardware-acceptance-001",
            "checks": {check: True for check in REQUIRED_READINESS_CHECKS},
            "manual_change": {
                "initial": {"value": 10.0, "revision": 1, "timestamp": "2026-07-26T00:00:00Z", "source": "console"},
                "changed": {"value": 6.0, "revision": 2, "timestamp": "2026-07-26T00:01:00Z", "source": "manual"},
            },
            "safe_write": {
                "artifact_id": "safe-write-001",
                "checks": {
                    "isolated_safe_write": True,
                    "readback": True,
                    "manual_conflict": True,
                    "disconnect_reconnect": True,
                    "targeted_rollback": True,
                },
            },
        }
    )

    assert result["status"] == "accepted"
    assert result["reason"] == "HARDWARE_ACCEPTANCE_EVIDENCE_COMPLETE"
    assert result["hardware_verified"] is True
    assert result["production_live_ready"] is False
    assert result["ai_write_permitted"] is False
    assert result["missing_checks"] == []


def test_readiness_checks_alone_do_not_verify_hardware_without_manual_and_safe_write_evidence():
    result = hardware_acceptance_readiness(
        {
            "target_kind": "hardware",
            "artifact_id": "readiness-only-001",
            "checks": {check: True for check in REQUIRED_READINESS_CHECKS},
        }
    )

    assert result["status"] == "pending"
    assert result["reason"] == "HARDWARE_EVIDENCE_INCOMPLETE"
    assert result["hardware_verified"] is False
    assert result["manual_change_status"] == "pending"
    assert result["safe_write_status"] == "pending"
