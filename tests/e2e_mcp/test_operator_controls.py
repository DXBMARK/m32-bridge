from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.cli import audit_tail, doctor, health, operator_snapshot, verify_connection
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def _assert_operator_control_shape(result: dict[str, object], name: str) -> None:
    assert result["control"] == name
    assert isinstance(result["status"], str)
    assert result["structured"] is True
    assert result["proposal_created"] is False
    assert result["write_operations"] == []
    assert result["osc_writes_sent"] == 0
    assert result["raw_osc_available"] is False
    assert result["arbitrary_path_available"] is False
    assert result["approval_token_supported"] is False


def test_health_returns_structured_output_without_osc_writes():
    server = FakeM32Server().start()
    try:
        result = health()

        _assert_operator_control_shape(result, "health")
        assert result["checks"]["cli"] == "ok"
        assert result["checks"]["mcp_primary_transport"] == "stdio"
        assert result["hardware_verified"] is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_doctor_checks_config_schema_and_status_read_only():
    server = FakeM32Server().start()
    try:
        result = doctor(config_path=Path("config.example.yaml"))

        _assert_operator_control_shape(result, "doctor")
        assert result["checks"]["config_schema"]["status"] == "ok"
        assert result["checks"]["runtime_status"]["write_locked_on_startup"] is True
        assert result["checks"]["secondary_transport"]["status"] == "disabled"
        assert server.write_packets == []
    finally:
        server.stop()


def test_snapshot_captures_read_only_snapshot_without_hardware_verified_claim():
    server = FakeM32Server().start()
    try:
        result = operator_snapshot(_client(server), snapshot_id="snap_test")

        _assert_operator_control_shape(result, "snapshot")
        snapshot = result["snapshot"]
        assert snapshot["snapshot_id"] == "snap_test"
        assert snapshot["environment_label"] == "emulator"
        assert snapshot["identity"]["hardware_verified"] is False
        assert snapshot["hardware_verified"] is False
        assert {value["path"] for value in snapshot["state_values"]} == {"/ch/01/headamp/gain", "/rta/source"}
        assert server.write_packets == []
    finally:
        server.stop()


def test_verify_connection_uses_read_only_checks_only():
    server = FakeM32Server().start()
    try:
        result = verify_connection(_client(server))

        _assert_operator_control_shape(result, "verify-connection")
        assert result["connection"]["status"] == "reconciled"
        assert result["connection"]["reconciled"] is True
        assert result["connection"]["identity"]["hardware_verified"] is False
        assert result["read_only_checks"] == ["/info", "/ch/01/headamp/gain", "/rta/source"]
        assert server.write_packets == []
    finally:
        server.stop()


def test_audit_tail_reads_last_records_without_writing_new_audit(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    writer = AuditWriter(audit_path)
    writer.append({"audit_id": "one", "result": "old"})
    writer.append({"audit_id": "two", "result": "new"})
    before = audit_path.read_text(encoding="utf-8")

    result = audit_tail(audit_path, limit=1)

    _assert_operator_control_shape(result, "audit-tail")
    assert result["records"] == [{"audit_id": "two", "result": "new"}]
    assert audit_path.read_text(encoding="utf-8") == before


def test_operator_controls_expose_no_raw_osc_arbitrary_path_or_approval_token():
    for function in (health, doctor, operator_snapshot, verify_connection, audit_tail):
        signature = inspect.signature(function)
        assert "raw_osc" not in signature.parameters
        assert "path" not in signature.parameters
        assert "address" not in signature.parameters
        assert "approval_token" not in signature.parameters


def test_py_module_health_outputs_json_only():
    completed = subprocess.run(
        [sys.executable, "-m", "m32_bridge", "health"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    payload = json.loads(completed.stdout)
    assert payload["control"] == "health"
    assert payload["structured"] is True
