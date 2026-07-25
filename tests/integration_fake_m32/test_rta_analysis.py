from __future__ import annotations

from m32_bridge.diagnostics.rta import analyze_rta
from m32_bridge.fake_m32 import server as fake_server
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def test_rta_analysis_reads_source_and_acquisition_settings_without_writes():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = analyze_rta(client, acquisition_settings={"window": "instant", "confidence": "caller_override"}).to_dict()

        assert result["source_identity"] == {
            "source": "main_st",
            "status": "known",
            "source_path": "/rta/source",
            "bands_path": "/rta/bands",
            "hardware_verified": False,
        }
        assert result["acquisition_settings"]["source"] == "main_st"
        assert result["acquisition_settings"]["source_path"] == "/rta/source"
        assert result["acquisition_settings"]["band_count"] == 100
        assert result["acquisition_settings"]["frequency_bins"] == 100
        assert result["acquisition_settings"]["freshness"] == "current_read"
        assert result["acquisition_settings"]["confidence"] == "normal"
        assert result["acquisition_settings"]["window"] == "instant"
        assert result["band_summary"]["count"] == 100
        assert result["confidence"] == "normal"
        assert result["no_per_channel_spectra"] is True
        assert "simultaneous per-channel spectra are not available" in result["limitations"]
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_rta_unknown_source_returns_limited_confidence_without_failure_or_writes(monkeypatch):
    monkeypatch.setattr(fake_server, "rta_source", lambda: "")
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = analyze_rta(client).to_dict()

        assert result["source_identity"]["source"] is None
        assert result["source_identity"]["status"] == "unknown"
        assert result["source_identity"]["hardware_verified"] is False
        assert result["confidence"] == "limited"
        assert result["acquisition_settings"]["confidence"] == "limited"
        assert any(f["category"] == "rta" and f["finding_id"] == "rta_source_unknown" for f in result["findings"])
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_rta_unsupported_source_returns_limited_confidence_without_failure_or_writes(monkeypatch):
    monkeypatch.setattr(fake_server, "rta_source", lambda: "UNSUPPORTED_PATH")
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = analyze_rta(client).to_dict()

        assert result["source_identity"]["source"] is None
        assert result["source_identity"]["status"] == "unknown"
        assert result["confidence"] == "limited"
        assert result["acquisition_settings"]["source"] is None
        assert result["acquisition_settings"]["frequency_bins"] == 100
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_rta_analysis_does_not_claim_per_channel_spectra_or_create_operations():
    server = FakeM32Server().start()
    try:
        client = OscClient(OscTransport(*server.address))
        result = analyze_rta(client).to_dict()

        assert result["no_per_channel_spectra"] is True
        assert result["acquisition_settings"]["simultaneous_per_channel_spectra"] is False
        assert result["source_identity"]["hardware_verified"] is False
        assert all("per-channel" not in f["summary"].lower() or "not available" in f["summary"].lower() for f in result["findings"])
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()
