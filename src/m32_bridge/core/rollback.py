"""Targeted rollback service."""

from __future__ import annotations

from uuid import uuid4

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.core.readback import verify_readback
from m32_bridge.osc.client import OscClient


def _append_rollback_audit(audit_writer: AuditWriter | None, proposal_id: str, result: str, error_code: str, operations: list[dict[str, object]]) -> bool:
    if audit_writer is None:
        return False
    audit_writer.append(
        {
            "audit_id": f"audit_{uuid4().hex}",
            "approval": {"source": "mcp_host_confirmation", "reference": "host-confirmed"},
            "proposal_id": proposal_id,
            "operations": operations,
            "result": result,
            "error_code": error_code,
        }
    )
    return True


def rollback_proposal(proposal_id: str, store: ProposalStore, client: OscClient, runtime_mode: RuntimeMode, audit_writer: AuditWriter | None = None) -> dict[str, object]:
    if runtime_mode is RuntimeMode.EMERGENCY:
        audit_written = _append_rollback_audit(audit_writer, proposal_id, "denied", "EMERGENCY_LOCKED", [])
        return {"allowed": False, "status": "EMERGENCY_LOCKED", "operations": [], "audit_written": audit_written}
    proposal = store.get(proposal_id)
    if proposal is None:
        audit_written = _append_rollback_audit(audit_writer, proposal_id, "denied", "PROPOSAL_NOT_FOUND", [])
        return {"allowed": False, "status": "PROPOSAL_NOT_FOUND", "operations": [], "audit_written": audit_written}
    expected_candidates = {op.target_path: op.rollback_value for op in proposal.operations}
    if proposal.rollback_candidates != expected_candidates:
        operations = [
            {"path": op.target_path, "rollback_value": op.rollback_value, "status": "candidate_mismatch"}
            for op in proposal.operations
        ]
        audit_written = _append_rollback_audit(audit_writer, proposal_id, "denied", "ROLLBACK_CANDIDATE_MISMATCH", operations)
        return {"allowed": False, "status": "ROLLBACK_CANDIDATE_MISMATCH", "operations": operations, "audit_written": audit_written}
    operations = []
    for op in proposal.operations:
        client.write_operation(op, op.rollback_value)
        readback = verify_readback(client, op.target_path, op.rollback_value)
        operations.append({"path": op.target_path, "rollback_value": op.rollback_value, "readback_matched": readback.matched})
    return {"allowed": True, "status": "ROLLED_BACK", "operations": operations}
