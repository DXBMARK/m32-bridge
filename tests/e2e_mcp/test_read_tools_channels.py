from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.read_tools import get_channel, list_channels, register_read_tools
from m32_bridge.mcp.server import ToolRegistry
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_channel_read_tools_return_structured_state():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        registry = ToolRegistry()
        register_read_tools(registry)
        assert "m32_get_channel" in registry.names()
        listed = list_channels(client)
        channel = get_channel(client, 1)
        assert listed["data"][0]["headamp_gain"] == "+10.0 dB"
        assert channel["data"]["headamp_gain"] == 10.0
        assert channel["source"]["hardware_verified"] is False
    finally:
        server.stop()

