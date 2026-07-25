from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.write_tools import m32_propose_changes


def test_propose_changes_creates_proposal_without_osc_writes():
    server = FakeM32Server().start()
    try:
        result = m32_propose_changes(
            intent="Set channel 1 fader",
            targets=[{"semantic_action": "fader_set", "target_path": "/ch/01/mix/fader", "before_value": -10.0, "requested_value": -8.0}],
        )
        assert result["proposal_id"].startswith("prop_")
        assert result["proposal_digest"].startswith("sha256:")
        assert result["osc_writes_sent"] == 0
        assert server.write_packets == []
    finally:
        server.stop()

