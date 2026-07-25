from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes, m32_rollback_proposal
from m32_bridge.osc.client import OscClient


class RecordingClient:
    def __init__(self, *, value=-8.0, revision=1, fail_write: bool = False) -> None:
        self.value = value
        self.revision = revision
        self.fail_write = fail_write
        self.writes: list[tuple[str, object, str]] = []

    def read_value(self, _path: str):
        return [self.value, self.revision]

    def write_value(self, *_args, **_kwargs):
        raise AssertionError("direct write_value must not be used")

    def write_operation(self, operation, value: object):
        self.writes.append((operation.target_path, value, operation.semantic_action))
        if self.fail_write:
            raise TimeoutError("write failed")
        self.value = value
        return [value, self.revision]


class RejectingTransport:
    def request(self, *_args):
        raise AssertionError("transport must not be reached")


class RecordingTransport:
    def __init__(self) -> None:
        self.requests = []

    def request(self, *args):
        self.requests.append(args)
        return type("Message", (), {"arguments": [args[1] if len(args) > 1 else None, 1]})()


def _proposal(store: ProposalStore, *, before=-10.0, requested=-8.0, runtime_mode=RuntimeMode.SOUNDCHECK):
    return m32_propose_changes(
        intent="Set fader",
        runtime_mode=runtime_mode,
        targets=[
            {
                "semantic_action": "fader_set",
                "target_path": "/ch/01/mix/fader",
                "before_value": before,
                "requested_value": requested,
            }
        ],
        store=store,
    )


def _execute(proposal, store, client, **kwargs):
    return m32_execute_proposal(
        proposal_id=proposal["proposal_id"],
        proposal_digest=proposal["proposal_digest"],
        expected_operation_count=1,
        store=store,
        client=client,
        host_confirmed=True,
        **kwargs,
    )


def test_proposal_and_snapshot_ids_are_unique_and_store_rejects_overwrite():
    store = ProposalStore()
    first = _proposal(store)
    second = _proposal(store)

    assert first["proposal_id"] != second["proposal_id"]
    assert store.get(first["proposal_id"]).base_snapshot_id != store.get(second["proposal_id"]).base_snapshot_id
    with pytest.raises(ValueError):
        store.add(store.get(first["proposal_id"]))


@pytest.mark.parametrize(
    "status",
    ["EXPIRED", "CONFLICTED", "POLICY_DENIED", "READBACK_FAILED", "ROLLED_BACK", "ROLLBACK_FAILED", "CANCELLED_BY_EMERGENCY", "USED"],
)
def test_terminal_or_expired_proposal_cannot_execute_before_write(status):
    store = ProposalStore()
    proposal = _proposal(store)
    stored = store.get(proposal["proposal_id"])
    stored.status = status
    if status == "EXPIRED":
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    client = RecordingClient()

    result = _execute(proposal, store, client)

    assert result["status"] == "DENIED"
    assert result["error_code"] == "PROPOSAL_TERMINAL"
    assert client.writes == []


def test_runtime_policy_is_rechecked_at_execution_before_write():
    store = ProposalStore()
    proposal = _proposal(store)
    client = RecordingClient()

    result = _execute(proposal, store, client, runtime_mode=RuntimeMode.OBSERVE)

    assert result["status"] == "DENIED"
    assert result["error_code"] == "POLICY_DENIED"
    assert client.writes == []


def test_live_delta_is_rechecked_at_execution_before_write():
    store = ProposalStore()
    proposal = _proposal(store, before=-10.0, requested=-6.0)
    client = RecordingClient()

    result = _execute(proposal, store, client, runtime_mode=RuntimeMode.LIVE)

    assert result["status"] == "DENIED"
    assert result["error_code"] == "POLICY_DENIED"
    assert client.writes == []


@pytest.mark.parametrize(
    ("semantic_action", "target_path", "before", "requested"),
    [
        ("fader_set", "/ch/01/mix/fader", -10.0, -99.0),
        ("fader_set", "/ch/01/mix/fader", -10.0, 10.25),
        ("headamp_set", "/headamp/001/gain", 10.0, 99.0),
        ("headamp_set", "/headamp/001/gain", 10.0, 10.25),
    ],
)
def test_bounds_are_enforced_when_building_operations(semantic_action, target_path, before, requested):
    with pytest.raises(ValueError):
        m32_propose_changes(
            intent="unsafe bounds",
            targets=[{"semantic_action": semantic_action, "target_path": target_path, "target_kind": "channel", "before_value": before, "requested_value": requested}],
        )


@pytest.mark.parametrize(
    "path",
    ["/ch/99/unknown", "/config/foo", "/-prefs/example", "/main/st/mix/fader", "/ch/01/config/phantom", "/shutdown/console", "/format_sd/card"],
)
def test_osc_client_rejects_arbitrary_or_prohibited_write_paths(path):
    client = OscClient(RejectingTransport())

    with pytest.raises(ValueError):
        client.write_value(path, 1, semantic_action="fader_set")


def test_osc_client_rejects_direct_write_without_semantic_action():
    client = OscClient(RejectingTransport())

    with pytest.raises(ValueError):
        client.write_value("/ch/01/mix/on", False)


def test_osc_client_rejects_direct_write_even_with_semantic_action_string():
    client = OscClient(RejectingTransport())

    with pytest.raises(ValueError):
        client.write_value("/ch/01/mix/on", False, semantic_action="mute_set")


def test_direct_operation_write_from_ordinary_caller_is_rejected():
    store = ProposalStore()
    proposal = _proposal(store)
    operation = store.get(proposal["proposal_id"]).operations[0]
    transport = RecordingTransport()
    client = OscClient(transport)

    with pytest.raises(ValueError):
        client.write_operation(operation, -8.0)

    assert transport.requests == []


def test_unknown_semantic_action_is_rejected():
    with pytest.raises(ValueError):
        m32_propose_changes(
            intent="unknown",
            targets=[{"semantic_action": "unknown_action", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
        )


@pytest.mark.parametrize(
    ("semantic_action", "target_path", "before", "requested"),
    [
        ("fader_set", "/ch/01/unknown/fader", -10.0, -8.0),
        ("routing_set", "/routing/in/01/extra", "local", "aes50"),
        ("routing_set", "/routing/user/01", "local", "aes50"),
        ("eq_adjust", "/ch/01/eq/unknown", 0.0, 1.0),
        ("dynamics_adjust", "/ch/01/dyn/unknown", 0.0, 1.0),
        ("bulk_update", "/bulk/anything", 0.0, 1.0),
    ],
)
def test_unsupported_path_templates_and_broad_suffixes_are_rejected(semantic_action, target_path, before, requested):
    with pytest.raises(ValueError):
        m32_propose_changes(
            intent="unsupported",
            targets=[{"semantic_action": semantic_action, "target_path": target_path, "target_kind": "channel", "before_value": before, "requested_value": requested}],
        )


def test_denied_attempts_write_audit_when_writer_is_present(tmp_path):
    store = ProposalStore()
    proposal = _proposal(store)
    writer = AuditWriter(tmp_path / "audit.jsonl")
    client = RecordingClient()

    result = m32_execute_proposal(
        proposal_id=proposal["proposal_id"],
        proposal_digest=proposal["proposal_digest"],
        expected_operation_count=1,
        store=store,
        client=client,
        host_confirmed=False,
        audit_writer=writer,
    )
    row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])

    assert result["audit_written"] is True
    assert row["result"] == "denied"
    assert row["error_code"] == "CONFIRMATION_REQUIRED"
    assert row["approval"]["source"] == "mcp_host_confirmation"
    assert row["approval"]["reference"] == "host-confirmed"


def test_readback_mismatch_fails_closed_terminalizes_and_audits(tmp_path):
    store = ProposalStore()
    proposal = _proposal(store)
    writer = AuditWriter(tmp_path / "audit.jsonl")
    client = RecordingClient(value=-7.0)

    def stale_read(_path: str):
        return [-7.0, 1]

    client.read_value = stale_read
    result = _execute(proposal, store, client, audit_writer=writer)
    row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])

    assert result["status"] == "READBACK_MISMATCH"
    assert result["error_code"] == "READBACK_MISMATCH"
    assert store.get(proposal["proposal_id"]).status == "READBACK_FAILED"
    assert row["operations"][0]["status"] == "readback_mismatch"
    assert row["operations"][0]["error_code"] == "READBACK_MISMATCH"
    assert row["operations"][0]["readback_value"] == -7.0


def test_write_exception_fails_closed_terminalizes_and_audits(tmp_path):
    store = ProposalStore()
    proposal = _proposal(store)
    writer = AuditWriter(tmp_path / "audit.jsonl")
    client = RecordingClient(fail_write=True)

    result = _execute(proposal, store, client, audit_writer=writer)
    row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])

    assert result["status"] == "FAILED"
    assert result["error_code"] == "TimeoutError"
    assert store.get(proposal["proposal_id"]).status == "READBACK_FAILED"
    assert len(client.writes) == 1
    assert row["operations"][0]["status"] == "failed"
    assert row["operations"][0]["path"] == "/ch/01/mix/fader"
    assert row["operations"][0]["old_value"] == -10.0
    assert row["operations"][0]["requested_value"] == -8.0
    assert row["operations"][0]["rollback_value"] == -10.0


def test_rollback_rejects_candidate_mismatch_without_write_and_audits(tmp_path):
    store = ProposalStore()
    proposal = _proposal(store)
    stored = store.get(proposal["proposal_id"])
    stored.rollback_candidates = {"/ch/01/mix/fader": -12.0}
    writer = AuditWriter(tmp_path / "audit.jsonl")
    client = RecordingClient()

    result = m32_rollback_proposal(proposal_id=proposal["proposal_id"], store=store, client=client, audit_writer=writer)
    row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[0])

    assert result["allowed"] is False
    assert result["status"] == "ROLLBACK_CANDIDATE_MISMATCH"
    assert client.writes == []
    assert row["error_code"] == "ROLLBACK_CANDIDATE_MISMATCH"


def test_emergency_execute_and_rollback_send_zero_writes():
    store = ProposalStore()
    proposal = _proposal(store)
    client = RecordingClient()

    executed = _execute(proposal, store, client, runtime_mode=RuntimeMode.EMERGENCY)
    rolled = m32_rollback_proposal(proposal_id=proposal["proposal_id"], store=store, client=client, runtime_mode=RuntimeMode.EMERGENCY)

    assert executed["error_code"] == "EMERGENCY_LOCKED"
    assert rolled["status"] == "EMERGENCY_LOCKED"
    assert client.writes == []
