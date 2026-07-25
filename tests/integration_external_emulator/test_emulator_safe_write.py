"""External Patrick-Gilles Maillot X32 Emulator safe-write gate.

These tests require a running external emulator. They use the bridge proposal,
executor, readback, and rollback path only. No direct OSC writes are used.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes, m32_rollback_proposal
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


LABEL_PATH = "/ch/01/config/name"


def _target() -> tuple[str, int]:
    host = os.environ.get("M32_EXTERNAL_EMULATOR_HOST")
    port = os.environ.get("M32_EXTERNAL_EMULATOR_PORT")
    if not host or not port:
        pytest.fail("M32_EXTERNAL_EMULATOR_HOST and M32_EXTERNAL_EMULATOR_PORT are required for T086")
    return host, int(port)


def _client() -> OscClient:
    host, port = _target()
    return OscClient(OscTransport(host, port, timeout=1.0))


def _proposal(store: ProposalStore, before_value: str, requested_value: str) -> dict[str, object]:
    return m32_propose_changes(
        intent="External emulator safe label write",
        targets=[
            {
                "semantic_action": "label_set",
                "target_path": LABEL_PATH,
                "target_kind": "channel",
                "before_value": before_value,
                "requested_value": requested_value,
            }
        ],
        runtime_mode=RuntimeMode.SOUNDCHECK,
        store=store,
    )


def test_external_emulator_safe_proposal_execute_readback_and_targeted_rollback():
    client = _client()
    original = str(client.read_value(LABEL_PATH)[0])
    requested = f"T086_{uuid4().hex[:8]}"
    store = ProposalStore()
    proposal = _proposal(store, original, requested)

    try:
        executed = m32_execute_proposal(
            proposal_id=str(proposal["proposal_id"]),
            proposal_digest=str(proposal["proposal_digest"]),
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
        )
        assert executed["status"] == "VERIFIED"
        assert executed["operations"][0]["path"] == LABEL_PATH
        assert executed["operations"][0]["readback_value"] == requested
        assert client.read_value(LABEL_PATH)[0] == requested

        rolled = m32_rollback_proposal(proposal_id=str(proposal["proposal_id"]), store=store, client=client)
        assert rolled["status"] == "ROLLED_BACK"
        assert rolled["operations"] == [{"path": LABEL_PATH, "rollback_value": original, "readback_matched": True}]
        assert client.read_value(LABEL_PATH)[0] == original
    finally:
        if client.read_value(LABEL_PATH)[0] != original:
            restore_store = ProposalStore()
            restore = _proposal(restore_store, str(client.read_value(LABEL_PATH)[0]), original)
            m32_execute_proposal(
                proposal_id=str(restore["proposal_id"]),
                proposal_digest=str(restore["proposal_digest"]),
                expected_operation_count=1,
                store=restore_store,
                client=client,
                host_confirmed=True,
            )


def test_external_emulator_conflicted_proposal_is_denied_without_write():
    client = _client()
    original = str(client.read_value(LABEL_PATH)[0])
    requested = f"DENY_{uuid4().hex[:8]}"
    store = ProposalStore()
    proposal = _proposal(store, original, requested)
    stored = store.get(str(proposal["proposal_id"]))
    assert stored is not None
    stored.status = "CONFLICTED"

    result = m32_execute_proposal(
        proposal_id=str(proposal["proposal_id"]),
        proposal_digest=str(proposal["proposal_digest"]),
        expected_operation_count=1,
        store=store,
        client=client,
        host_confirmed=True,
    )

    assert result["status"] == "DENIED"
    assert result["error_code"] == "PROPOSAL_TERMINAL"
    assert client.read_value(LABEL_PATH)[0] == original


def test_external_emulator_leaf_reads_do_not_expose_revision_conflict_metadata():
    client = _client()
    label_read = client.read_value(LABEL_PATH)

    assert len(label_read) == 1
