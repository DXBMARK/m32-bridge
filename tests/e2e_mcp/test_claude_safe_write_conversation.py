from __future__ import annotations

import inspect
from pathlib import Path

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.cli import audit_tail, health, verify_connection
from m32_bridge.core.connection import ConnectionController
from m32_bridge.core.emergency import EmergencyController
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import ToolRegistry, invoke_tool, register_mvp_tools
from m32_bridge.mcp.write_tools import m32_execute_proposal
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def _propose(registry: ToolRegistry, store: ProposalStore, before: float = -10.0, requested: float = -9.0) -> dict[str, object]:
    return invoke_tool(
        registry,
        "m32_propose_changes",
        runtime_mode=RuntimeMode.SOUNDCHECK,
        intent="Scripted safe fader change",
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


def _execute(
    registry: ToolRegistry,
    proposal: dict[str, object],
    store: ProposalStore,
    client: OscClient,
    *,
    host_confirmed: bool,
    audit_writer: AuditWriter | None = None,
    always_allow: bool = False,
) -> dict[str, object]:
    return invoke_tool(
        registry,
        "m32_execute_proposal",
        runtime_mode=RuntimeMode.SOUNDCHECK,
        proposal_id=str(proposal["proposal_id"]),
        proposal_digest=str(proposal["proposal_digest"]),
        expected_operation_count=1,
        store=store,
        client=client,
        host_confirmed=host_confirmed,
        audit_writer=audit_writer,
        always_allow=always_allow,
    )


def test_scripted_safe_write_conversation_requires_host_confirmation_and_rejects_always_allow(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        store = ProposalStore()
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        proposal = _propose(registry, store)["result"]

        missing_confirmation = _execute(registry, proposal, store, client, host_confirmed=False, audit_writer=audit_writer)
        always_allow = _execute(registry, proposal, store, client, host_confirmed=True, audit_writer=audit_writer, always_allow=True)
        approval_token = invoke_tool(
            registry,
            "m32_execute_proposal",
            proposal_id=str(proposal["proposal_id"]),
            proposal_digest=str(proposal["proposal_digest"]),
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            approval_token="model-token",
        )

        assert missing_confirmation["error_code"] == "CONFIRMATION_REQUIRED"
        assert always_allow["result"]["error_code"] == "ALWAYS_ALLOW_FORBIDDEN"
        assert approval_token["error_code"] == "VALIDATION_ERROR"
        assert "approval_token" not in inspect.signature(m32_execute_proposal).parameters
        assert server.write_packets == []
    finally:
        server.stop()


def test_scripted_safe_write_execute_readback_rollback_audit_and_operator_controls(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        store = ProposalStore()
        audit_path = tmp_path / "audit.jsonl"
        audit_writer = AuditWriter(audit_path)
        proposal = _propose(registry, store)["result"]

        executed = _execute(registry, proposal, store, client, host_confirmed=True, audit_writer=audit_writer)
        readback = invoke_tool(registry, "m32_get_channel", client=client, channel=1)
        rolled_back = invoke_tool(
            registry,
            "m32_rollback_proposal",
            runtime_mode=RuntimeMode.SOUNDCHECK,
            proposal_id=str(proposal["proposal_id"]),
            store=store,
            client=client,
            audit_writer=audit_writer,
        )
        audit = audit_tail(audit_path, limit=5)

        assert executed["result"]["status"] == "VERIFIED"
        assert executed["result"]["audit_written"] is True
        assert readback["ok"] is True
        assert rolled_back["result"]["status"] == "ROLLED_BACK"
        assert rolled_back["result"]["audit_written"] is True
        assert audit["records_returned"] >= 2
        assert health()["hardware_verified"] is False
        assert verify_connection(client)["hardware_verified"] is False
        assert server.write_packets == ["/ch/01/mix/fader", "/ch/01/mix/fader"]
    finally:
        server.stop()


def test_scripted_safe_write_conflict_denial_does_not_write(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        store = ProposalStore()
        proposal = _propose(registry, store)["result"]
        server.set_value("/ch/01/mix/fader", -7.0, source="manual")

        conflict = _execute(registry, proposal, store, client, host_confirmed=True, audit_writer=AuditWriter(tmp_path / "audit.jsonl"))

        assert conflict["result"]["error_code"] == "PROPOSAL_CONFLICT"
        assert conflict["result"]["conflicts"][0]["path"] == "/ch/01/mix/fader"
        assert server.write_packets == []
    finally:
        server.stop()


def test_scripted_safe_write_emergency_and_unlock_denials_send_no_console_writes(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        store = ProposalStore()
        controller = EmergencyController()
        connection = ConnectionController(client, required_paths=("/ch/01/headamp/gain", "/rta/source"))
        proposal = _propose(registry, store)["result"]

        entered = invoke_tool(registry, "m32_enter_emergency", store=store, controller=controller, reason="scripted test")
        emergency_execute = invoke_tool(
            registry,
            "m32_execute_proposal",
            runtime_mode=RuntimeMode.EMERGENCY,
            proposal_id=str(proposal["proposal_id"]),
            proposal_digest=str(proposal["proposal_digest"]),
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            audit_writer=AuditWriter(tmp_path / "audit.jsonl"),
        )
        emergency_rollback = invoke_tool(
            registry,
            "m32_rollback_proposal",
            runtime_mode=RuntimeMode.EMERGENCY,
            proposal_id=str(proposal["proposal_id"]),
            store=store,
            client=client,
        )
        unlock_wrong_mode = invoke_tool(
            registry,
            "m32_unlock_writes",
            controller=controller,
            connection=connection,
            runtime_mode=RuntimeMode.SOUNDCHECK,
        )
        exited = invoke_tool(registry, "m32_exit_emergency_to_observe", controller=controller)
        unlock_without_reconcile = invoke_tool(
            registry,
            "m32_unlock_writes",
            controller=controller,
            connection=connection,
            runtime_mode=RuntimeMode.OBSERVE,
        )

        assert entered["result"]["status"] == "EMERGENCY_LOCKED"
        assert emergency_execute["result"]["error_code"] == "EMERGENCY_LOCKED"
        assert emergency_rollback["result"]["status"] == "EMERGENCY_LOCKED"
        assert unlock_wrong_mode["result"]["reason"] == "OBSERVE_REQUIRED"
        assert exited["result"]["runtime_mode"] == "OBSERVE"
        assert unlock_without_reconcile["result"]["reason"] == "RECONCILIATION_REQUIRED"
        assert server.write_packets == []
    finally:
        server.stop()


def test_scripted_safe_write_surface_has_no_raw_osc_arbitrary_path_or_approval_token():
    registry = _registry()
    names = " ".join(registry.names()).lower()

    assert "raw_osc" not in names
    assert "arbitrary_path" not in names
    assert "approval_token" not in names
    assert "shell" not in names
