"""Proposal and write-tool MCP surface.

Only proposal creation is implemented at this stage. Execution tasks are later.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from m32_bridge.core.connection import ConnectionController
from m32_bridge.core.emergency import EmergencyController
from m32_bridge.core.models import Proposal, RuntimeMode
from m32_bridge.core.executor import ExecutionContext, execute_proposal
from m32_bridge.core.operations import OperationIntent, build_operation
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.core.rollback import rollback_proposal
from m32_bridge.mcp.server import ToolRegistry, ToolSpec
from m32_bridge.osc.client import OscClient


def m32_propose_changes(
    *,
    intent: str,
    targets: list[dict[str, Any]],
    runtime_mode: RuntimeMode = RuntimeMode.SOUNDCHECK,
    base_snapshot_id: str | None = None,
    base_revisions: dict[str, int] | None = None,
    store: ProposalStore | None = None,
) -> dict[str, Any]:
    operations = [
        build_operation(
            OperationIntent(
                semantic_action=target["semantic_action"],
                target_path=target["target_path"],
                target_kind=target.get("target_kind", "channel"),
                before_value=target.get("before_value"),
                requested_value=target.get("requested_value"),
                reason=intent,
                operation_id=target.get("operation_id", f"op_{index:08d}"),
                affects_main=target.get("affects_main", False),
            ),
            runtime_mode,
            has_snapshot=True,
        )
        for index, target in enumerate(targets, start=1)
    ]
    now = datetime.now(UTC)
    proposal = Proposal(
        proposal_id=f"prop_{uuid4().hex}",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        created_by="claude_desktop",
        base_snapshot_id=base_snapshot_id or f"snap_{uuid4().hex}",
        base_revisions=base_revisions or {op.target_path: 1 for op in operations},
        runtime_mode_at_creation=runtime_mode,
        operations=operations,
        risk_summary={
            "max_risk": max((op.risk_class.value for op in operations), default="R1"),
            "computed_by": "bridge_server",
            "contains_r3": any(op.risk_class.value == "R3" for op in operations),
            "contains_r4": False,
            "affects_main": any(op.affects_main for op in operations),
        },
        human_readable_summary=intent,
        rollback_candidates={op.target_path: op.rollback_value for op in operations},
        status="PENDING_APPROVAL",
    )
    active_store = store or ProposalStore()
    proposal = active_store.add(proposal)
    return {
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.proposal_digest,
        "operations": [op.__dict__ | {"risk_class": op.risk_class.value} for op in proposal.operations],
        "risk_summary": proposal.risk_summary,
        "expires_at": proposal.expires_at.isoformat(),
        "osc_writes_sent": 0,
    }


def register_write_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec("m32_propose_changes", read_only=False, sends_osc_writes=False, handler=m32_propose_changes))
    registry.register(ToolSpec("m32_execute_proposal", read_only=False, sends_osc_writes=True, handler=m32_execute_proposal))
    registry.register(ToolSpec("m32_verify_proposal", read_only=True, sends_osc_writes=False, handler=m32_verify_proposal))
    registry.register(ToolSpec("m32_rollback_proposal", read_only=False, sends_osc_writes=True, handler=m32_rollback_proposal))
    registry.register(ToolSpec("m32_lock_writes", read_only=False, sends_osc_writes=False, handler=m32_lock_writes))
    registry.register(ToolSpec("m32_unlock_writes", read_only=False, sends_osc_writes=False, handler=m32_unlock_writes))
    registry.register(ToolSpec("m32_enter_emergency", read_only=False, sends_osc_writes=False, handler=m32_enter_emergency))
    registry.register(ToolSpec("m32_exit_emergency_to_observe", read_only=False, sends_osc_writes=False, handler=m32_exit_emergency_to_observe))


def m32_execute_proposal(
    *,
    proposal_id: str,
    proposal_digest: str,
    expected_operation_count: int,
    store: ProposalStore,
    client: OscClient,
    host_confirmed: bool,
    runtime_mode: RuntimeMode = RuntimeMode.SOUNDCHECK,
    audit_writer=None,
    always_allow: bool = False,
) -> dict[str, object]:
    return execute_proposal(
        proposal_id,
        proposal_digest,
        expected_operation_count,
        store,
        client,
        ExecutionContext(host_confirmed=host_confirmed, runtime_mode=runtime_mode, audit_writer=audit_writer, always_allow=always_allow),
    )


def m32_verify_proposal(*, proposal_id: str, store: ProposalStore) -> dict[str, object]:
    proposal = store.get(proposal_id)
    return {"proposal_id": proposal_id, "found": proposal is not None, "status": proposal.status if proposal else "missing"}


def m32_rollback_proposal(*, proposal_id: str, store: ProposalStore, client: OscClient, runtime_mode: RuntimeMode = RuntimeMode.SOUNDCHECK, audit_writer=None) -> dict[str, object]:
    result = rollback_proposal(proposal_id, store, client, runtime_mode, audit_writer=audit_writer)
    if audit_writer is not None and result.get("allowed") is True and "audit_written" not in result:
        proposal = store.get(proposal_id)
        operation_rows = []
        for operation in proposal.operations if proposal else []:
            rollback_result = next((item for item in result.get("operations", []) if item.get("path") == operation.target_path), {})
            readback_value = operation.rollback_value if rollback_result.get("readback_matched") is True else None
            operation_rows.append(
                {
                    "operation_id": operation.operation_id,
                    "path": operation.target_path,
                    "old_value": operation.requested_value,
                    "requested_value": operation.rollback_value,
                    "readback_value": readback_value,
                    "rollback_value": operation.requested_value,
                    "old": operation.requested_value,
                    "requested": operation.rollback_value,
                    "readback": readback_value,
                    "rollback": operation.requested_value,
                    "status": "rolled_back" if rollback_result.get("readback_matched") is True else "rollback_failed",
                    "latency_ms": int(rollback_result.get("latency_ms", 0)) if isinstance(rollback_result, dict) else 0,
                }
            )
        audit_writer.append(
            {
                "audit_id": f"audit_{uuid4().hex}",
                "approval": {"source": "mcp_host_confirmation", "reference": "host-confirmed"},
                "proposal_id": proposal_id,
                "operations": operation_rows,
                "result": "rolled_back",
            }
        )
        result["audit_written"] = True
    return result


def m32_lock_writes(*, controller: EmergencyController, reason: str = "operator_lock") -> dict[str, object]:
    return controller.lock_writes(reason=reason)


def m32_unlock_writes(
    *,
    controller: EmergencyController,
    connection: ConnectionController,
    runtime_mode: RuntimeMode = RuntimeMode.OBSERVE,
) -> dict[str, object]:
    if runtime_mode is not RuntimeMode.OBSERVE:
        controller.write_locked = True
        return {"unlocked": False, "write_locked": True, "runtime_mode": runtime_mode.value, "reason": "OBSERVE_REQUIRED"}
    return controller.unlock_writes_after_reconciliation(connection)


def m32_enter_emergency(*, store: ProposalStore, controller: EmergencyController, reason: str) -> dict[str, object]:
    return controller.enter_emergency(store=store, reason=reason)


def m32_exit_emergency_to_observe(*, controller: EmergencyController) -> dict[str, object]:
    return controller.exit_emergency_to_observe()
