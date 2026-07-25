from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _proposal(store):
    return m32_propose_changes(
        intent="Set fader",
        targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
        store=store,
    )


def test_execute_denies_missing_host_confirmation_and_always_allow():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = _proposal(store)
        client = OscClient(OscTransport(*server.address))
        denied = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=False,
        )
        always = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            always_allow=True,
        )
        emergency = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
            runtime_mode=RuntimeMode.EMERGENCY,
        )
        assert denied["error_code"] == "CONFIRMATION_REQUIRED"
        assert always["error_code"] == "ALWAYS_ALLOW_FORBIDDEN"
        assert emergency["error_code"] == "EMERGENCY_LOCKED"
        assert server.write_packets == []
    finally:
        server.stop()

