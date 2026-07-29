from __future__ import annotations

from m32_bridge.cli import _build_parser, _run_command
from m32_bridge.installer.first_run import run_setup_probe


EMULATOR_PROBE = {
    "udp_info_probe_result": "CONNECTED",
    "response_address": ["127.0.0.1", 10023],
    "latency_ms": 1,
    "exception_type": None,
    "info_raw": ["V4.13", "X32 Emulator"],
}


def test_detect_device_emulator_never_claims_hardware_or_production(monkeypatch):
    monkeypatch.setattr("m32_bridge.cli.setup_info_probe", lambda *args, **kwargs: EMULATOR_PROBE.copy())
    parser = _build_parser()
    args = parser.parse_args(["detect-device", "--host", "127.0.0.1", "--port", "10023", "--target-type", "emulator", "--json"])

    result = _run_command(args)

    assert result["classification"] == "EMULATOR_CONNECTED"
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["osc_writes_sent"] == 0


def test_setup_linked_emulator_output_never_claims_hardware_or_production(tmp_path):
    result = run_setup_probe(
        host="127.0.0.1",
        port=10023,
        target_type="emulator",
        config_path=tmp_path / "runtime.yaml",
        probe_result=EMULATOR_PROBE,
    )

    assert result["classification"] == "EMULATOR_CONNECTED"
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["osc_writes_sent"] == 0
