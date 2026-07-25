from datetime import UTC, datetime, timedelta

import pytest

from m32_bridge.core.models import Operation, Proposal, RiskClass, RuntimeMode
from m32_bridge.core.proposals import ProposalStore, proposal_digest


def _proposal():
    now = datetime.now(UTC)
    op = Operation("op_12345678", "fader_set", "/ch/01/mix/fader", "channel", -10, -6, -10, {"unit": "dB"}, RiskClass.R1, False)
    return Proposal(
        proposal_id="prop_12345678",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        created_by="claude_desktop",
        base_snapshot_id="snap_12345678",
        base_revisions={"/ch/01/mix/fader": 1},
        runtime_mode_at_creation=RuntimeMode.SOUNDCHECK,
        operations=[op],
        risk_summary={"max_risk": "R1", "computed_by": "bridge_server"},
        human_readable_summary="Set fader",
        rollback_candidates={"/ch/01/mix/fader": -10},
    )


def test_proposal_digest_is_stable_and_store_marks_used_once():
    proposal = _proposal()
    assert proposal_digest(proposal) == proposal_digest(proposal)
    store = ProposalStore()
    store.add(proposal)
    store.mark_used(proposal.proposal_id)
    with pytest.raises(ValueError):
        store.mark_used(proposal.proposal_id)

