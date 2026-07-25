from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.analysis_tools import m32_recommend_event_setup
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_recommendations_do_not_create_writes_or_executable_proposals():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = m32_recommend_event_setup(client)
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()

