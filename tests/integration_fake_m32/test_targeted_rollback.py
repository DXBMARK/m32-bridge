from m32_bridge.core.models import RuntimeMode
from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes, m32_rollback_proposal
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_targeted_rollback_restores_only_proposal_paths_and_is_denied_in_emergency():
    server = FakeM32Server().start()
    try:
        store = ProposalStore()
        proposal = m32_propose_changes(
            intent="Set fader",
            targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
            store=store,
        )
        client = OscClient(OscTransport(*server.address))
        m32_execute_proposal(proposal_id=proposal["proposal_id"], proposal_digest=proposal["proposal_digest"], expected_operation_count=1, store=store, client=client, host_confirmed=True)
        emergency = m32_rollback_proposal(proposal_id=proposal["proposal_id"], store=store, client=client, runtime_mode=RuntimeMode.EMERGENCY)
        rolled = m32_rollback_proposal(proposal_id=proposal["proposal_id"], store=store, client=client)
        assert emergency["status"] == "EMERGENCY_LOCKED"
        assert rolled["status"] == "ROLLED_BACK"
        assert rolled["operations"][0]["rollback_value"] == -10.0
    finally:
        server.stop()

