from m32_bridge.core.proposals import ProposalStore
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_execute_proposal, m32_propose_changes
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_manual_change_conflict_blocks_execution_for_fader_mute_send_routing_paths():
    for path, before, after, action in [
        ("/ch/01/mix/fader", -10.0, -6.0, "fader_set"),
        ("/ch/01/mix/on", True, False, "mute_set"),
        ("/ch/01/mix/01/level", -20.0, -18.0, "send_level_set"),
        ("/routing/in/01", "local", "aes50", "routing_set"),
    ]:
        server = FakeM32Server().start()
        try:
            store = ProposalStore()
            proposal = m32_propose_changes(
                intent="Change path",
                targets=[{"semantic_action": action, "target_path": path, "target_kind": "routing" if "routing" in path else "channel", "before_value": before, "requested_value": after}],
                store=store,
            )
            server.set_value(path, after, source="manual")
            client = OscClient(OscTransport(*server.address))
            result = m32_execute_proposal(
                proposal_id=proposal["proposal_id"],
                proposal_digest=proposal["proposal_digest"],
                expected_operation_count=1,
                store=store,
                client=client,
                host_confirmed=True,
            )
            assert result["error_code"] == "PROPOSAL_CONFLICT"
            assert result["conflicts"][0]["path"] == path
            assert server.write_packets == []
        finally:
            server.stop()

