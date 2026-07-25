import json

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes, m32_rollback_proposal
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _proposal(store: ProposalStore, *, before=-10.0, requested=-8.0):
    return m32_propose_changes(
        intent="Set fader",
        targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": before, "requested_value": requested}],
        store=store,
    )


def _rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _assert_operation_audit_shape(operation):
    assert operation["path"] == "/ch/01/mix/fader"
    assert "old_value" in operation
    assert "requested_value" in operation
    assert "readback_value" in operation
    assert "rollback_value" in operation
    assert "old" in operation
    assert "requested" in operation
    assert "readback" in operation
    assert "rollback" in operation
    assert "status" in operation
    assert isinstance(operation["latency_ms"], int)


def test_write_audit_records_approval_source_reference_and_latency_per_operation(tmp_path):
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = _proposal(store)
        writer = AuditWriter(tmp_path / "audit.jsonl")
        client = OscClient(OscTransport(*server.address))
        result = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            audit_writer=writer,
        )
        row = _rows(tmp_path / "audit.jsonl")[0]
        assert result["audit_written"] is True
        assert row["approval"]["source"] == "mcp_host_confirmation"
        assert row["approval"]["reference"] == "host-confirmed"
        assert "approval_token" not in json.dumps(row)
        _assert_operation_audit_shape(row["operations"][0])
    finally:
        server.stop()


def test_denied_write_attempt_has_audit_coverage_when_writer_is_available(tmp_path):
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = _proposal(store)
        writer = AuditWriter(tmp_path / "audit.jsonl")
        client = OscClient(OscTransport(*server.address))

        result = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=False,
            audit_writer=writer,
        )
        row = _rows(tmp_path / "audit.jsonl")[0]

        assert result["status"] == "DENIED"
        assert result["audit_written"] is True
        assert row["result"] == "denied"
        assert row["error_code"] == "CONFIRMATION_REQUIRED"
        assert row["approval"]["source"] == "mcp_host_confirmation"
        assert row["approval"]["reference"] == "host-confirmed"
        _assert_operation_audit_shape(row["operations"][0])
        assert server.write_packets == []
    finally:
        server.stop()


def test_successful_write_and_rollback_have_append_only_audit_records(tmp_path):
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = _proposal(store, before=-10.0, requested=-7.0)
        writer = AuditWriter(tmp_path / "audit.jsonl")
        client = OscClient(OscTransport(*server.address))

        executed = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            audit_writer=writer,
        )
        before_rollback_rows = _rows(tmp_path / "audit.jsonl")
        rolled_back = m32_rollback_proposal(
            proposal_id=proposal["proposal_id"],
            store=store,
            client=client,
            audit_writer=writer,
        )
        rows = _rows(tmp_path / "audit.jsonl")

        assert executed["status"] == "VERIFIED"
        assert rolled_back["status"] == "ROLLED_BACK"
        assert len(before_rollback_rows) == 1
        assert len(rows) == 2
        assert rows[0]["result"] == "verified"
        assert rows[1]["result"] == "rolled_back"
        for row in rows:
            assert row["approval"]["source"] == "mcp_host_confirmation"
            assert row["approval"]["reference"] == "host-confirmed"
            assert "approval_token" not in json.dumps(row)
            _assert_operation_audit_shape(row["operations"][0])
    finally:
        server.stop()


def test_audit_jsonl_redacts_secrets_and_appends_without_rewriting_existing_rows(tmp_path):
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(path)

    writer.append({"audit_id": "first", "password": "secret-value", "operations": []})
    original = path.read_text(encoding="utf-8")
    writer.append({"audit_id": "second", "nested": {"api_token": "token-value"}, "operations": []})
    rows = _rows(path)

    assert path.read_text(encoding="utf-8").startswith(original)
    assert len(rows) == 2
    assert rows[0]["password"] == "[REDACTED]"
    assert rows[1]["nested"]["api_token"] == "[REDACTED]"
