"""Proposal digest and lifecycle primitives."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from m32_bridge.core.models import Proposal

TERMINAL_STATUSES = {
    "EXPIRED",
    "CONFLICTED",
    "POLICY_DENIED",
    "READBACK_FAILED",
    "ROLLED_BACK",
    "ROLLBACK_FAILED",
    "CANCELLED_BY_EMERGENCY",
    "USED",
}


def canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def digest_payload(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_payload(payload).encode("utf-8")).hexdigest()


def proposal_digest(proposal: Proposal) -> str:
    payload = {
        "proposal_id": proposal.proposal_id,
        "base_snapshot_id": proposal.base_snapshot_id,
        "base_revisions": proposal.base_revisions,
        "operations": [
            {
                "operation_id": op.operation_id,
                "semantic_action": op.semantic_action,
                "target_path": op.target_path,
                "requested_value": op.requested_value,
                "rollback_value": op.rollback_value,
                "risk_class": op.risk_class.value,
            }
            for op in proposal.operations
        ],
        "expires_at": proposal.expires_at.isoformat(),
    }
    return digest_payload(payload)


class ProposalStore:
    def __init__(self) -> None:
        self._proposals: dict[str, Proposal] = {}

    def add(self, proposal: Proposal) -> Proposal:
        if proposal.proposal_id in self._proposals:
            raise ValueError("proposal_id already exists")
        proposal.proposal_digest = proposal_digest(proposal)
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Proposal | None:
        proposal = self._proposals.get(proposal_id)
        if proposal and proposal.is_expired(datetime.now(UTC)):
            proposal.status = "EXPIRED"
        return proposal

    def mark_used(self, proposal_id: str) -> None:
        proposal = self._proposals[proposal_id]
        if proposal.status in TERMINAL_STATUSES:
            raise ValueError("proposal is already terminal")
        proposal.status = "USED"

    def mark_status(self, proposal_id: str, status: str) -> None:
        self._proposals[proposal_id].status = status

    def cancel_pending_by_emergency(self) -> list[str]:
        cancelled: list[str] = []
        for proposal_id, proposal in self._proposals.items():
            if proposal.status == "PENDING_APPROVAL":
                proposal.status = "CANCELLED_BY_EMERGENCY"
                cancelled.append(proposal_id)
        return cancelled
