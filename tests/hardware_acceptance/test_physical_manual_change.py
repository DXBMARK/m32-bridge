from __future__ import annotations

from m32_bridge.core.status import manual_change_challenge_status


def test_manual_gain_fader_challenge_is_pending_without_real_hardware():
    result = manual_change_challenge_status()

    assert result["status"] == "pending"
    assert result["reason"] == "HARDWARE_EVIDENCE_NOT_AVAILABLE"
    assert result["hardware_verified"] is False
    assert result["ai_write_permitted"] is False
    assert result["write_operations"] == []
    assert result["required_steps"] == [
        "read_initial_value",
        "manual_console_change",
        "read_changed_value",
        "prove_revision_timestamp_source_changed",
    ]


def test_manual_change_requires_revision_timestamp_and_source_evidence():
    result = manual_change_challenge_status(
        {
            "target_kind": "hardware",
            "initial": {"value": 10.0, "revision": 1, "timestamp": "2026-07-26T00:00:00Z", "source": "console"},
            "changed": {"value": 6.0, "revision": 1, "timestamp": "2026-07-26T00:00:00Z", "source": "console"},
        }
    )

    assert result["status"] == "pending"
    assert result["reason"] == "MANUAL_CHANGE_EVIDENCE_INCOMPLETE"
    assert result["hardware_verified"] is False
    assert result["revision_changed"] is False
    assert result["timestamp_changed"] is False
    assert result["source_changed"] is False
    assert result["write_operations"] == []


def test_fake_or_external_emulator_manual_change_is_not_hardware_acceptance():
    for target_kind in ("fake_m32", "external_emulator"):
        result = manual_change_challenge_status(
            {
                "target_kind": target_kind,
                "initial": {"value": 10.0, "revision": 1, "timestamp": "a", "source": "console"},
                "changed": {"value": 6.0, "revision": 2, "timestamp": "b", "source": "manual"},
            }
        )

        assert result["status"] == "not_available"
        assert result["reason"] == "EMULATOR_NOT_HARDWARE"
        assert result["hardware_verified"] is False
        assert result["ai_write_permitted"] is False


def test_complete_manual_change_evidence_is_accepted_but_does_not_verify_hardware_alone():
    result = manual_change_challenge_status(
        {
            "target_kind": "hardware",
            "initial": {"value": 10.0, "revision": 1, "timestamp": "2026-07-26T00:00:00Z", "source": "console"},
            "changed": {"value": 6.0, "revision": 2, "timestamp": "2026-07-26T00:01:00Z", "source": "manual"},
        }
    )

    assert result["status"] == "accepted"
    assert result["reason"] == "MANUAL_CHANGE_EVIDENCE_COMPLETE"
    assert result["hardware_verified"] is False
    assert result["value_changed"] is True
    assert result["revision_changed"] is True
    assert result["timestamp_changed"] is True
    assert result["source_changed"] is True
    assert result["ai_write_permitted"] is False
