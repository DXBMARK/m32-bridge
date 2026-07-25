import pytest

from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_host_confirmation_required_and_no_approval_token_parameter_is_accepted():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = m32_propose_changes(
            intent="Set fader",
            targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
            store=store,
        )
        client = OscClient(OscTransport(*server.address))
        with pytest.raises(TypeError):
            m32_execute_proposal(
                proposal_id=proposal["proposal_id"],
                proposal_digest=proposal["proposal_digest"],
                expected_operation_count=1,
                store=store,
                client=client,
                host_confirmed=True,
                approval_token="model-token",
            )
    finally:
        server.stop()

