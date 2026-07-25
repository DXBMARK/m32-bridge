from m32_bridge.diagnostics.preflight import run_event_preflight
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_event_preflight_reports_sync_gain_rta_and_readiness_evidence():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = run_event_preflight(client)
        data = result.to_dict()
        assert data["write_ready"] is True
        assert any(f.category == "gain" for f in result.findings)
        assert data["proposal_created"] is False
    finally:
        server.stop()


def test_event_preflight_blocks_clock_aes50_or_card_sync_failure():
    server = FakeM32Server().start()
    try:
        server.state.values["/-stat/aes50_a"] = "unlocked"
        client = OscClient(OscTransport(*server.address))
        result = run_event_preflight(client)
        assert result.blockers
        assert result.to_dict()["write_ready"] is False
        assert result.blockers[0].affected_paths == ["/-stat/aes50_a"]
    finally:
        server.stop()

