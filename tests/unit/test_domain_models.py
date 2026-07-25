from datetime import UTC, datetime, timedelta

import pytest

from m32_bridge.core.models import (
    AuditRecord,
    ConnectionState,
    ConsoleCapability,
    ConsoleIdentity,
    Operation,
    RiskClass,
    RuntimeMode,
    StateValue,
    VerificationState,
)


def test_console_identity_rejects_hardware_verified_emulator():
    with pytest.raises(ValueError):
        ConsoleIdentity(
            identity_id="id",
            model="M32",
            firmware_version="4.13",
            firmware_status="known",
            endpoint_host="127.0.0.1",
            endpoint_port=10023,
            source="fake_m32",
            observed_at=datetime.now(UTC),
            environment_label="emulator",
            verification_state=VerificationState.EMULATOR,
            hardware_verified=True,
        )


def test_r4_capability_cannot_be_writable():
    with pytest.raises(ValueError):
        ConsoleCapability("cap", "id", "firmware", True, RiskClass.R4, True, True, "test", datetime.now(UTC))


def test_state_value_freshness_and_required_labels():
    now = datetime.now(UTC)
    value = StateValue(
        path="/ch/01/mix/fader",
        raw_value=0.5,
        native_value=-6.0,
        display_value="-6.0 dB",
        unit="dB",
        value_type="float",
        source="fake_m32",
        revision=1,
        observed_at=now,
        fresh_until=now + timedelta(seconds=1),
        confidence=1.0,
        stale=False,
        partial=False,
        support_status="supported",
        environment_label="emulator",
    )
    assert value.is_fresh(now)


def test_operation_rejects_r4():
    with pytest.raises(ValueError):
        Operation("op_12345678", "firmware_update", "/firmware", "other", None, "x", None, {}, RiskClass.R4, False)


def test_audit_record_carries_approval_source_and_latency():
    record = AuditRecord(
        audit_id="audit_12345678",
        timestamp=datetime.now(UTC),
        actor_host="claude_desktop",
        tool_name="m32_execute_proposal",
        runtime_mode=RuntimeMode.SOUNDCHECK,
        connection_lifecycle=ConnectionState.READY,
        verification_state=VerificationState.EMULATOR,
        approval_source="mcp_host_confirmation",
        approval_reference="host-ref",
        result="executed",
        operations=[{"path": "/ch/01/mix/fader", "latency_ms": 12}],
    )
    assert record.approval_source == "mcp_host_confirmation"
    assert record.operations[0]["latency_ms"] == 12

