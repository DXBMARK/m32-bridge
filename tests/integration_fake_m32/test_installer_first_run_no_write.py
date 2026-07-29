from __future__ import annotations

from m32_bridge.installer.first_run import run_setup_probe


def test_first_run_setup_uses_info_only_and_no_set(tmp_path):
    result = run_setup_probe(
        host="127.0.0.1",
        port=10023,
        target_type="emulator",
        config_path=tmp_path / "runtime.yaml",
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "response_address": ["127.0.0.1", 10023],
            "latency_ms": 1,
            "exception_type": None,
            "info_raw": ["V4.13", "X32"],
        },
    )

    assert result["attempted_path"] == "/info"
    assert result["osc_writes_sent"] == 0
    assert "/set" not in str(result)
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_first_run_without_host_does_not_scan_or_guess():
    result = run_setup_probe(host=None)

    assert result["status"] == "SETUP_INPUT_REQUIRED"
    assert result["guessed_host"] is None
    assert result["scan_attempted"] is False
    assert result["osc_writes_sent"] == 0
