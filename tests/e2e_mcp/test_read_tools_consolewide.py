from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.read_tools import (
    capture_snapshot,
    get_clock_sync,
    get_meters,
    get_routing,
    get_rta,
    overview,
    trace_signal,
)
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_consolewide_read_tools_cover_routing_clock_meters_rta_snapshots_and_trace():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        assert "/ch" in overview(client)["data"]["nodes"]
        assert get_clock_sync(client)["data"]["aes50_a"] == "locked"
        assert get_meters(client)["data"]["not_per_channel_spectra"] is True
        assert get_rta(client)["data"]["source"] == "main_st"
        assert "inputs" in get_routing(client)["data"]
        assert capture_snapshot(client)["data"]["scope"] == "critical"
        assert trace_signal(client)["data"]["confidence"] == "limited"
    finally:
        server.stop()

