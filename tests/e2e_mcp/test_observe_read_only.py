from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.read_tools import get_channel, get_meters, get_rta
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_observe_read_tools_send_no_state_changing_osc_packets():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        get_channel(client, 1)
        get_meters(client)
        get_rta(client)
        assert server.write_packets == []
    finally:
        server.stop()

