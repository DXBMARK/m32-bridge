from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_safe_write_executes_after_confirmation_and_readback_matches():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = m32_propose_changes(
            intent="Set fader",
            targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
            store=store,
        )
        client = OscClient(OscTransport(*server.address))
        result = m32_execute_proposal(
            proposal_id=proposal["proposal_id"],
            proposal_digest=proposal["proposal_digest"],
            expected_operation_count=1,
            store=store,
            client=client,
            host_confirmed=True,
        )
        assert result["status"] == "VERIFIED"
        assert result["operations"][0]["readback_value"] == -8.0
        assert server.write_packets == ["/ch/01/mix/fader"]
    finally:
        server.stop()
