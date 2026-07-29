from __future__ import annotations

from m32_bridge.installer.first_run import run_setup_probe


def test_emulator_classification_is_honest_without_hardware_claim(tmp_path):
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

    assert result["classification"] == "EMULATOR_CONNECTED"
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
    assert result["osc_writes_sent"] == 0


def test_hardware_candidate_stays_unverified(tmp_path):
    result = run_setup_probe(
        host="192.0.2.10",
        port=10023,
        target_type="hardware",
        config_path=tmp_path / "runtime.yaml",
        probe_result={
            "udp_info_probe_result": "CONNECTED",
            "response_address": ["192.0.2.10", 10023],
            "latency_ms": 1,
            "exception_type": None,
            "info_raw": ["V4.13", "M32"],
        },
    )

    assert result["classification"] == "CONNECTED_UNVERIFIED"
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
