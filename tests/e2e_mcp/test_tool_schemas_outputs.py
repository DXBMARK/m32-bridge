from __future__ import annotations

from pathlib import Path

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.cli import audit_tail, doctor, health
from m32_bridge.core.connection import ConnectionController
from m32_bridge.core.emergency import EmergencyController
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.server import RuntimeContext, RuntimeTarget, ToolRegistry, invoke_tool, register_mvp_tools
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mvp_tools(registry)
    return registry


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address, timeout=0.05))


def _runtime_context(server: FakeM32Server) -> RuntimeContext:
    host, port = server.address
    return RuntimeContext(RuntimeTarget(host=host, port=port, timeout=0.05, target_kind="fake_m32"))


def _assert_envelope(output: dict[str, object], tool: str) -> None:
    assert output["tool"] == tool
    assert isinstance(output["ok"], bool)
    assert "runtime_mode" in output
    assert "connection_lifecycle" in output
    assert "verification_state" in output
    assert "source" in output
    assert output["hardware_verified"] is False
    assert "result" in output


def test_status_read_snapshot_compare_and_verify_outputs_are_structured():
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        context = _runtime_context(server)
        store = ProposalStore()
        cases = [
            ("m32_console_status", {"runtime_context": context}),
            ("m32_get_channel", {"runtime_context": context, "channel": 1}),
            ("m32_capture_snapshot", {"runtime_context": context}),
            ("m32_compare_snapshots", {"client": client}),
            ("m32_verify_proposal", {"proposal_id": "missing", "store": store}),
        ]

        for tool, kwargs in cases:
            _assert_envelope(invoke_tool(registry, tool, **kwargs), tool)
        assert server.write_packets == []
    finally:
        server.stop()


def test_write_execution_tool_does_not_receive_runtime_client_implicitly():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = invoke_tool(
            _registry(),
            "m32_propose_changes",
            intent="Set fader",
            targets=[
                {
                    "semantic_action": "fader_set",
                    "target_path": "/ch/01/mix/fader",
                    "before_value": -10.0,
                    "requested_value": -9.0,
                }
            ],
            store=store,
        )["result"]

        result = invoke_tool(
            _registry(),
            "m32_execute_proposal",
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            host_confirmed=True,
            runtime_context=_runtime_context(server),
        )

        assert result["ok"] is False
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "client" in result["result"]["exception"]
        assert server.write_packets == []
    finally:
        server.stop()


def test_preflight_propose_execute_rollback_emergency_lock_unlock_and_rta_outputs_are_structured(tmp_path: Path):
    server = FakeM32Server().start()
    try:
        registry = _registry()
        client = _client(server)
        store = ProposalStore()
        controller = EmergencyController()
        connection = ConnectionController(client, required_paths=("/ch/01/headamp/gain", "/rta/source"))
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        proposal = invoke_tool(
            registry,
            "m32_propose_changes",
            intent="Set fader",
            targets=[
                {
                    "semantic_action": "fader_set",
                    "target_path": "/ch/01/mix/fader",
                    "before_value": -10.0,
                    "requested_value": -9.0,
                }
            ],
            store=store,
        )
        proposal_result = proposal["result"]
        cases = [
            ("m32_event_preflight", {"client": client}),
            ("m32_propose_changes", {"intent": "Label only", "targets": [], "store": store}),
            (
                "m32_execute_proposal",
                {
                    "proposal_id": proposal_result["proposal_id"],
                    "proposal_digest": proposal_result["proposal_digest"],
                    "expected_operation_count": 1,
                    "store": store,
                    "client": client,
                    "host_confirmed": False,
                    "audit_writer": audit_writer,
                },
            ),
            ("m32_rollback_proposal", {"proposal_id": proposal_result["proposal_id"], "store": store, "client": client, "runtime_mode": RuntimeMode.EMERGENCY}),
            ("m32_lock_writes", {"controller": controller, "reason": "test"}),
            ("m32_unlock_writes", {"controller": controller, "connection": connection, "runtime_mode": RuntimeMode.OBSERVE}),
            ("m32_enter_emergency", {"store": store, "controller": controller, "reason": "test"}),
            ("m32_exit_emergency_to_observe", {"controller": controller}),
            ("m32_analyze_rta", {"client": client}),
        ]

        _assert_envelope(proposal, "m32_propose_changes")
        for tool, kwargs in cases:
            _assert_envelope(invoke_tool(registry, tool, **kwargs), tool)
        assert server.write_packets == []
    finally:
        server.stop()


def test_audit_tail_and_operator_controls_outputs_are_structured(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    AuditWriter(audit_path).append({"audit_id": "one", "result": "ok"})

    for result in (health(), doctor(config_path=Path("config.example.yaml")), audit_tail(audit_path, limit=1)):
        assert result["structured"] is True
        assert result["hardware_verified"] is False
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert result["osc_writes_sent"] == 0
