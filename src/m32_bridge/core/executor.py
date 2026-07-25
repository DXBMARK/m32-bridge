"""Serialized transaction executor for approved proposals."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

from m32_bridge.audit.writer import AuditWriter
from m32_bridge.core.conflicts import detect_conflicts
from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.operations import validate_operation_bounds
from m32_bridge.core.policy import PolicyRequest, evaluate_policy
from m32_bridge.core.proposals import ProposalStore, TERMINAL_STATUSES
from m32_bridge.core.readback import verify_readback
from m32_bridge.osc.client import OscClient


@dataclass(frozen=True)
class ExecutionContext:
    host_confirmed: bool
    runtime_mode: RuntimeMode
    audit_writer: AuditWriter | None = None
    always_allow: bool = False


def _operation_audit(op, *, status: str, latency_ms: int | None = None, readback_value=None, error_code: str | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "operation_id": op.operation_id,
        "path": op.target_path,
        "old_value": op.before_value,
        "requested_value": op.requested_value,
        "readback_value": readback_value,
        "rollback_value": op.rollback_value,
        "old": op.before_value,
        "requested": op.requested_value,
        "readback": readback_value,
        "rollback": op.rollback_value,
        "status": status,
        "latency_ms": 0 if latency_ms is None else latency_ms,
    }
    if error_code is not None:
        row["error_code"] = error_code
    return row


def _proposal_operation_audits(proposal, *, status: str, error_code: str | None = None) -> list[dict[str, object]]:
    if proposal is None:
        return []
    return [_operation_audit(op, status=status, latency_ms=0, error_code=error_code) for op in proposal.operations]


def _append_audit(
    writer: AuditWriter | None,
    *,
    proposal_id: str,
    proposal_digest: str | None,
    operations: list[dict[str, object]],
    result: str,
    error_code: str | None = None,
) -> bool:
    if writer is None:
        return False
    record = {
        "audit_id": f"audit_{uuid4().hex}",
        "approval": {"source": "mcp_host_confirmation", "reference": "host-confirmed"},
        "proposal_id": proposal_id,
        "proposal_digest": proposal_digest,
        "operations": operations,
        "result": result,
    }
    if error_code is not None:
        record["error_code"] = error_code
    writer.append(record)
    return True


def _deny(context: ExecutionContext, proposal_id: str, proposal_digest: str | None, error_code: str, operations: list[dict[str, object]] | None = None) -> dict[str, object]:
    audit_written = _append_audit(
        context.audit_writer,
        proposal_id=proposal_id,
        proposal_digest=proposal_digest,
        operations=operations or [],
        result="denied",
        error_code=error_code,
    )
    return {"status": "DENIED", "error_code": error_code, "operations": operations or [], "audit_written": audit_written}


def execute_proposal(
    proposal_id: str,
    proposal_digest: str,
    expected_operation_count: int,
    store: ProposalStore,
    client: OscClient,
    context: ExecutionContext,
) -> dict[str, object]:
    proposal = store.get(proposal_id)
    if context.always_allow:
        return _deny(context, proposal_id, proposal_digest, "ALWAYS_ALLOW_FORBIDDEN", _proposal_operation_audits(proposal, status="denied", error_code="ALWAYS_ALLOW_FORBIDDEN"))
    if not context.host_confirmed:
        return _deny(context, proposal_id, proposal_digest, "CONFIRMATION_REQUIRED", _proposal_operation_audits(proposal, status="denied", error_code="CONFIRMATION_REQUIRED"))
    if context.runtime_mode is RuntimeMode.EMERGENCY:
        if proposal is not None:
            proposal.status = "CANCELLED_BY_EMERGENCY"
        return _deny(context, proposal_id, proposal_digest, "EMERGENCY_LOCKED", _proposal_operation_audits(proposal, status="denied", error_code="EMERGENCY_LOCKED"))
    if proposal is None:
        return _deny(context, proposal_id, proposal_digest, "PROPOSAL_NOT_FOUND")
    if proposal.proposal_digest != proposal_digest or len(proposal.operations) != expected_operation_count:
        return _deny(context, proposal_id, proposal_digest, "VALIDATION_ERROR", _proposal_operation_audits(proposal, status="denied", error_code="VALIDATION_ERROR"))
    if proposal.status in TERMINAL_STATUSES:
        return _deny(context, proposal_id, proposal_digest, "PROPOSAL_TERMINAL", _proposal_operation_audits(proposal, status="denied", error_code="PROPOSAL_TERMINAL"))
    conflicts = detect_conflicts(proposal, client)
    if conflicts:
        proposal.status = "CONFLICTED"
        denied = _deny(context, proposal_id, proposal_digest, "PROPOSAL_CONFLICT", _proposal_operation_audits(proposal, status="denied", error_code="PROPOSAL_CONFLICT"))
        denied["conflicts"] = [c.to_dict() for c in conflicts]
        return denied

    policy_denials = []
    for op in proposal.operations:
        try:
            validate_operation_bounds(op.semantic_action, op.before_value, op.requested_value, context.runtime_mode)
        except ValueError as exc:
            policy_denials.append(_operation_audit(op, status="policy_denied", latency_ms=0, error_code=str(exc)))
            continue
        decision = evaluate_policy(
            PolicyRequest(
                runtime_mode=context.runtime_mode,
                risk_class=op.risk_class,
                semantic_action=op.semantic_action,
                target_path=op.target_path,
                affects_main=op.affects_main,
                has_snapshot=True,
                live_delta_db=float(op.requested_value) - float(op.before_value) if op.semantic_action == "fader_set" else None,
            )
        )
        if not decision.allowed:
            policy_denials.append(_operation_audit(op, status="policy_denied", latency_ms=0, error_code=",".join(decision.reasons)))
    if policy_denials:
        proposal.status = "POLICY_DENIED"
        return _deny(context, proposal_id, proposal_digest, "POLICY_DENIED", policy_denials)

    operation_results = []
    overall = "VERIFIED"
    for op in proposal.operations:
        start = monotonic()
        try:
            client.write_operation(op, op.requested_value)
            readback = verify_readback(client, op.target_path, op.requested_value)
        except Exception as exc:
            proposal.status = "READBACK_FAILED"
            latency_ms = int((monotonic() - start) * 1000)
            operation_results.append(_operation_audit(op, status="failed", latency_ms=latency_ms, error_code=type(exc).__name__))
            _append_audit(
                context.audit_writer,
                proposal_id=proposal_id,
                proposal_digest=proposal_digest,
                operations=operation_results,
                result="failed",
                error_code=type(exc).__name__,
            )
            return {"status": "FAILED", "error_code": type(exc).__name__, "operations": operation_results, "audit_written": context.audit_writer is not None}
        latency_ms = int((monotonic() - start) * 1000)
        if not readback.matched:
            proposal.status = "READBACK_FAILED"
            operation_results.append(_operation_audit(op, status="readback_mismatch", latency_ms=latency_ms, readback_value=readback.actual, error_code="READBACK_MISMATCH"))
            _append_audit(
                context.audit_writer,
                proposal_id=proposal_id,
                proposal_digest=proposal_digest,
                operations=operation_results,
                result="failed",
                error_code="READBACK_MISMATCH",
            )
            return {"status": "READBACK_MISMATCH", "error_code": "READBACK_MISMATCH", "operations": operation_results, "audit_written": context.audit_writer is not None}
        operation_results.append(_operation_audit(op, status="readback_matched", latency_ms=latency_ms, readback_value=readback.actual))
    if overall == "VERIFIED":
        store.mark_used(proposal_id)
    audit_written = _append_audit(
        context.audit_writer,
        proposal_id=proposal_id,
        proposal_digest=proposal_digest,
        operations=operation_results,
        result="verified" if overall == "VERIFIED" else "failed",
    )
    return {"status": overall, "operations": operation_results, "audit_written": audit_written}
