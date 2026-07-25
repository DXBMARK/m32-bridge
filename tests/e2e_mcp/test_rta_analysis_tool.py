from __future__ import annotations

import inspect

from m32_bridge.core.models import RuntimeMode
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp.analysis_tools import m32_analyze_rta, register_analysis_tools
from m32_bridge.mcp.server import ToolRegistry
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address))


def test_m32_analyze_rta_current_mode_returns_structured_analysis_without_writes():
    server = FakeM32Server().start()
    try:
        result = m32_analyze_rta(_client(server))

        assert result["source_identity"]["source"] == "main_st"
        assert result["source_identity"]["hardware_verified"] is False
        assert result["acquisition_settings"]["band_count"] == 100
        assert result["no_per_channel_spectra"] is True
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_m32_analyze_rta_scan_mode_outside_soundcheck_is_denied_without_writes():
    server = FakeM32Server().start()
    try:
        result = m32_analyze_rta(_client(server), mode="scan", runtime_mode=RuntimeMode.LIVE, sources=["main_st", "aux_8"])

        assert result["status"] == "denied"
        assert result["reason"] == "SOUNDCHECK_REQUIRED"
        assert result["scanned_sources"] == []
        assert result["restore_attempts"] == []
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_m32_analyze_rta_scan_mode_requires_explicit_sources_without_guessing():
    server = FakeM32Server().start()
    try:
        result = m32_analyze_rta(_client(server), mode="scan", runtime_mode=RuntimeMode.SOUNDCHECK)

        assert result["status"] == "denied"
        assert result["reason"] == "CONFIGURED_SOURCES_REQUIRED"
        assert result["configured_sources"] == []
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_m32_analyze_rta_scan_mode_soundcheck_scans_and_restores_rta_source_only():
    server = FakeM32Server().start()
    try:
        result = m32_analyze_rta(_client(server), mode="scan", runtime_mode="SOUNDCHECK", sources=["main_st", "aux_8"])

        assert result["status"] == "success"
        assert result["original_source"] == "main_st"
        assert [entry["source"] for entry in result["scanned_sources"]] == ["main_st", "aux_8"]
        assert result["restore_attempts"] == [{"source": "main_st", "status": "restored"}]
        assert result["hardware_verified"] is False
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.state.values["/rta/source"] == "main_st"
        assert server.write_packets == ["/rta/source", "/rta/source", "/rta/source"]
    finally:
        server.stop()


def test_m32_analyze_rta_tool_metadata_is_conservative_for_scan_capability():
    registry = ToolRegistry()
    register_analysis_tools(registry)

    spec = registry.get("m32_analyze_rta")
    assert spec.read_only is False
    assert spec.sends_osc_writes is True
    assert "m32_analyze_rta" in registry.names()


def test_m32_analyze_rta_signature_exposes_no_raw_osc_arbitrary_path_or_approval_token():
    signature = inspect.signature(m32_analyze_rta)

    assert "approval_token" not in signature.parameters
    assert "raw_osc" not in signature.parameters
    assert "path" not in signature.parameters
    assert "address" not in signature.parameters
