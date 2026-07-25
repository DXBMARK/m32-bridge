from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.discovery import discover_identity
from m32_bridge.osc.subscriptions import XRemoteSubscription
from m32_bridge.osc.transport import OscTransport
from m32_bridge.state.cache import StateCache
from m32_bridge.state.sync import reconcile_path


def test_connect_and_observe_manual_gain_change_from_10_to_6_db():
    server = FakeM32Server().start()
    try:
        host, port = server.address
        transport = OscTransport(host, port)
        discovery = discover_identity(transport)
        assert discovery.identity.model == "M32"
        assert discovery.identity.environment_label == "emulator"

        subscription = XRemoteSubscription(transport)
        subscription.renew()
        assert server.state.xremote_count == 1

        cache = StateCache()
        first = reconcile_path(cache, transport, "/ch/01/headamp/gain")
        assert cache.get("/ch/01/headamp/gain").native_value == 10.0
        assert first.manual_change_detected is False

        server.set_gain(6.0, source="manual")
        second = reconcile_path(cache, transport, "/ch/01/headamp/gain")
        cached = cache.get("/ch/01/headamp/gain")
        assert cached.native_value == 6.0
        assert cached.display_value == "+6.0 dB"
        assert second.revision > first.revision
        assert second.manual_change_detected is True
    finally:
        server.stop()

