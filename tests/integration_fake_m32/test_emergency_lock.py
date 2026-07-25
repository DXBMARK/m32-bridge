from __future__ import annotations

import inspect
import json

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.core.connection import ConnectionController
from m32_bridge.core.emergency import EmergencyController
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import ToolRegistry
from m32_bridge.mcp.write_tools import (
    m32_enter_emergency,
    m32_execute_proposal,
    m32_exit_emergency_to_observe,
    m32_lock_writes,
    m32_propose_changes,
    m32_rollback_proposal,
    m32_unlock_writes,
    register_write_tools,
)
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def _connection(server: FakeM32Server) -> ConnectionController:
    return ConnectionController(_client(server), required_paths=("/ch/01/headamp/gain", "/rta/source"))


def _proposal(store: ProposalStore, *, action: str = "fader_set", path: str = "/ch/01/mix/fader", before=-10.0, requested=-8.0):
    return m32_propose_changes(
        intent=f"{action} during emergency test",
        targets=[{"semantic_action": action, "target_path": path, "before_value": before, "requested_value": requested}],
        store=store,
    )


def test_enter_emergency_cancels_pending_proposals_and_locks_ai_writes_without_console_write():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        first = _proposal(store)
        second = _proposal(store, before=-20.0, requested=-18.0)
        controller = EmergencyController()

        result = controller.enter_emergency(store=store, reason="operator pressed emergency")

        assert result["runtime_mode"] == "EMERGENCY"
        assert result["write_locked"] is True
        assert result["automation_stopped"] is True
        assert set(result["cancelled_proposals"]) == {first["proposal_id"], second["proposal_id"]}
        assert store.get(first["proposal_id"]).status == "CANCELLED_BY_EMERGENCY"
        assert store.get(second["proposal_id"]).status == "CANCELLED_BY_EMERGENCY"
        assert server.write_packets == []
    finally:
        server.stop()


def test_emergency_denies_ai_mute_execute_and_rollback_without_console_writes(tmp_path):
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        mute = _proposal(store, action="mute_set", path="/ch/01/mix/on", before=True, requested=False)
        fader = _proposal(store)
        controller = EmergencyController()
        controller.enter_emergency(store=store, reason="lock all ai writes")
        writer = AuditWriter(tmp_path / "audit.jsonl")
        client = _client(server)

        muted = m32_execute_proposal(
            proposal_id=mute["proposal_id"],
            proposal_digest=mute["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            runtime_mode=RuntimeMode.EMERGENCY,
            audit_writer=writer,
        )
        executed = m32_execute_proposal(
            proposal_id=fader["proposal_id"],
            proposal_digest=fader["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            runtime_mode=RuntimeMode.EMERGENCY,
            audit_writer=writer,
        )
        rolled = m32_rollback_proposal(
            proposal_id=fader["proposal_id"],
            store=store,
            client=client,
            runtime_mode=RuntimeMode.EMERGENCY,
            audit_writer=writer,
        )
        audit_rows = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]

        assert muted["error_code"] == "EMERGENCY_LOCKED"
        assert executed["error_code"] == "EMERGENCY_LOCKED"
        assert rolled["status"] == "EMERGENCY_LOCKED"
        assert all(row["result"] == "denied" for row in audit_rows)
        assert all(row["error_code"] == "EMERGENCY_LOCKED" for row in audit_rows)
        assert server.write_packets == []
    finally:
        server.stop()


def test_exit_emergency_returns_observe_only_and_does_not_unlock_until_reconciled():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        emergency = EmergencyController()
        connection = _connection(server)
        assert connection.reconcile_after_reconnect().status == "reconciled"
        emergency.enter_emergency(store=store, reason="test")

        exited = emergency.exit_emergency_to_observe()
        unlock_before_reconcile = emergency.unlock_writes_after_reconciliation(connection)
        refreshed = connection.reconcile_after_reconnect()
        unlock_after_reconcile = emergency.unlock_writes_after_reconciliation(connection)

        assert exited["runtime_mode"] == "OBSERVE"
        assert exited["write_locked"] is True
        assert exited["emergency_active"] is False
        assert unlock_before_reconcile["unlocked"] is False
        assert unlock_before_reconcile["reason"] == "RECONCILIATION_REQUIRED"
        assert refreshed.status == "reconciled"
        assert unlock_after_reconcile == {"unlocked": True, "write_locked": False, "runtime_mode": "OBSERVE", "reason": None}
        assert server.write_packets == []
    finally:
        server.stop()


def test_mcp_emergency_lock_unlock_tools_send_no_osc_writes_and_enforce_observe_reconciliation():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = _proposal(store)
        emergency = EmergencyController()
        connection = _connection(server)
        registry = ToolRegistry()
        register_write_tools(registry)

        locked = m32_lock_writes(controller=emergency, reason="manual lock")
        entered = m32_enter_emergency(store=store, controller=emergency, reason="emergency")
        exited = m32_exit_emergency_to_observe(controller=emergency)
        unlock_live = m32_unlock_writes(controller=emergency, connection=connection, runtime_mode=RuntimeMode.LIVE)
        unlock_unreconciled = m32_unlock_writes(controller=emergency, connection=connection, runtime_mode=RuntimeMode.OBSERVE)
        assert connection.reconcile_after_reconnect().status == "reconciled"
        unlock_reconciled = m32_unlock_writes(controller=emergency, connection=connection, runtime_mode=RuntimeMode.OBSERVE)

        assert locked["write_locked"] is True
        assert proposal["proposal_id"] in entered["cancelled_proposals"]
        assert exited["runtime_mode"] == "OBSERVE"
        assert locked["osc_writes_sent"] == 0
        assert entered["osc_writes_sent"] == 0
        assert exited["osc_writes_sent"] == 0
        assert unlock_live["reason"] == "OBSERVE_REQUIRED"
        assert unlock_unreconciled["reason"] == "RECONCILIATION_REQUIRED"
        assert unlock_reconciled["unlocked"] is True
        assert emergency.runtime_mode is RuntimeMode.OBSERVE
        assert emergency.write_locked is False
        assert registry.get("m32_enter_emergency").sends_osc_writes is False
        assert registry.get("m32_exit_emergency_to_observe").sends_osc_writes is False
        assert registry.get("m32_lock_writes").sends_osc_writes is False
        assert registry.get("m32_unlock_writes").sends_osc_writes is False
        assert server.write_packets == []
    finally:
        server.stop()


def test_emergency_mcp_tool_signatures_expose_no_approval_token_raw_osc_or_arbitrary_path():
    for tool in [m32_lock_writes, m32_unlock_writes, m32_enter_emergency, m32_exit_emergency_to_observe]:
        params = inspect.signature(tool).parameters
        assert "approval_token" not in params
        assert "raw_osc" not in params
        assert "path" not in params
        assert "address" not in params
