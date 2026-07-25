"""Proposal conflict reporting."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.core.models import Proposal
from m32_bridge.osc.client import OscClient


@dataclass(frozen=True)
class ProposalConflict:
    path: str
    baseline_revision: int
    current_revision: int
    current_value: object
    source: str = "console"

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def detect_conflicts(proposal: Proposal, client: OscClient) -> list[ProposalConflict]:
    conflicts: list[ProposalConflict] = []
    for op in proposal.operations:
        args = client.read_value(op.target_path)
        if len(args) < 2:
            continue
        current_revision = int(args[1])
        baseline_revision = proposal.base_revisions.get(op.target_path, -1)
        if current_revision != baseline_revision:
            conflicts.append(
                ProposalConflict(
                    path=op.target_path,
                    baseline_revision=baseline_revision,
                    current_revision=current_revision,
                    current_value=args[0],
                )
            )
    return conflicts
