from __future__ import annotations

import pytest

from m32_bridge.core.models import RuntimeMode
from m32_bridge.diagnostics.rta import scan_rta_sources
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _client(server: FakeM32Server) -> OscClient:
    return OscClient(OscTransport(*server.address))


@pytest.mark.parametrize("mode", [RuntimeMode.OBSERVE, RuntimeMode.LIVE, RuntimeMode.EMERGENCY])
def test_rta_scan_rejects_non_soundcheck_modes_without_any_osc_write(mode):
    server = FakeM32Server().start()
    try:
        result = scan_rta_sources(_client(server), sources=["main_st", "aux_8"], runtime_mode=mode).to_dict()

        assert result["status"] == "denied"
        assert result["reason"] in {"SOUNDCHECK_REQUIRED", "EMERGENCY_LOCKED"}
        assert result["scanned_sources"] == []
        assert result["restore_attempts"] == []
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_rta_scan_requires_explicit_configured_sources_without_guessing_or_writes():
    server = FakeM32Server().start()
    try:
        result = scan_rta_sources(_client(server), sources=[], runtime_mode=RuntimeMode.SOUNDCHECK).to_dict()

        assert result["status"] == "denied"
        assert result["reason"] == "CONFIGURED_SOURCES_REQUIRED"
        assert result["configured_sources"] == []
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.write_packets == []
    finally:
        server.stop()


def test_rta_scan_sequentially_scans_configured_sources_and_restores_original_after_success():
    server = FakeM32Server().start()
    try:
        result = scan_rta_sources(_client(server), sources=["main_st", "aux_8", "bus_1"], runtime_mode=RuntimeMode.SOUNDCHECK).to_dict()

        assert result["status"] == "success"
        assert result["original_source"] == "main_st"
        assert result["configured_sources"] == ["main_st", "aux_8", "bus_1"]
        assert [entry["source"] for entry in result["scanned_sources"]] == ["main_st", "aux_8", "bus_1"]
        assert all(entry["status"] == "scanned" for entry in result["scanned_sources"])
        assert result["restore_attempts"] == [{"source": "main_st", "status": "restored"}]
        assert result["hardware_verified"] is False
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert server.state.values["/rta/source"] == "main_st"
        assert server.write_packets == ["/rta/source", "/rta/source", "/rta/source", "/rta/source"]
    finally:
        server.stop()


def test_rta_scan_restores_original_after_scan_failure_and_reports_failure():
    server = FakeM32Server().start()
    server.rta_band_failure_sources.add("aux_8")
    try:
        result = scan_rta_sources(_client(server), sources=["main_st", "aux_8", "bus_1"], runtime_mode=RuntimeMode.SOUNDCHECK).to_dict()

        assert result["status"] == "failed"
        assert result["reason"] == "SCAN_FAILED"
        assert result["original_source"] == "main_st"
        assert [entry["source"] for entry in result["scanned_sources"]] == ["main_st", "aux_8"]
        assert result["scanned_sources"][-1]["status"] == "failed"
        assert result["restore_attempts"] == [{"source": "main_st", "status": "restored"}]
        assert server.state.values["/rta/source"] == "main_st"
        assert all(path == "/rta/source" for path in server.write_packets)
    finally:
        server.stop()


def test_rta_scan_restores_original_after_cancellation():
    server = FakeM32Server().start()
    calls = {"count": 0}

    def cancellation() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    try:
        result = scan_rta_sources(_client(server), sources=["main_st", "aux_8", "bus_1"], runtime_mode=RuntimeMode.SOUNDCHECK, cancellation=cancellation).to_dict()

        assert result["status"] == "cancelled"
        assert result["reason"] == "CANCELLED"
        assert [entry["source"] for entry in result["scanned_sources"]] == ["main_st"]
        assert result["restore_attempts"] == [{"source": "main_st", "status": "restored"}]
        assert server.state.values["/rta/source"] == "main_st"
        assert all(path == "/rta/source" for path in server.write_packets)
    finally:
        server.stop()


def test_rta_scan_reports_restore_failure_without_claiming_success():
    server = FakeM32Server().start()
    server.rta_restore_failure_sources.add("main_st")
    try:
        result = scan_rta_sources(_client(server), sources=["aux_8"], runtime_mode=RuntimeMode.SOUNDCHECK).to_dict()

        assert result["status"] == "failed"
        assert result["reason"] == "RESTORE_FAILED"
        assert result["restore_attempts"] == [{"source": "main_st", "status": "failed"}]
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
        assert all(path == "/rta/source" for path in server.write_packets)
    finally:
        server.stop()


def test_rta_scan_only_writes_rta_source_and_never_touches_protected_console_paths():
    server = FakeM32Server().start()
    try:
        before = {
            "gain": server.state.values["/ch/01/headamp/gain"],
            "fader": server.state.values["/ch/01/mix/fader"],
            "mute": server.state.values["/ch/01/mix/on"],
            "routing": server.state.values["/routing/in/01"],
        }

        result = scan_rta_sources(_client(server), sources=["aux_8"], runtime_mode=RuntimeMode.SOUNDCHECK).to_dict()

        assert result["status"] == "success"
        assert server.state.values["/ch/01/headamp/gain"] == before["gain"]
        assert server.state.values["/ch/01/mix/fader"] == before["fader"]
        assert server.state.values["/ch/01/mix/on"] == before["mute"]
        assert server.state.values["/routing/in/01"] == before["routing"]
        assert "/shutdown" not in server.write_packets
        assert all(path == "/rta/source" for path in server.write_packets)
        assert result["proposal_created"] is False
        assert result["write_operations"] == []
    finally:
        server.stop()
