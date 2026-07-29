from __future__ import annotations

from m32_bridge.cli import _build_parser, _run_command


CONNECTED_PROBE = {
    "udp_info_probe_result": "CONNECTED",
    "response_address": ["127.0.0.1", 10023],
    "latency_ms": 1,
    "exception_type": None,
    "info_raw": ["V4.13", "X32"],
}


def test_get_info_uses_info_only_and_sends_no_writes(monkeypatch):
    monkeypatch.setattr("m32_bridge.cli.setup_info_probe", lambda *args, **kwargs: CONNECTED_PROBE.copy())
    parser = _build_parser()
    args = parser.parse_args(["get-info", "--host", "127.0.0.1", "--port", "10023", "--json"])

    result = _run_command(args)

    assert result["attempted_path"] == "/info"
    assert "/set" not in str(result)
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_verification_setup_detect_and_doctor_runtime_keep_zero_write(monkeypatch, tmp_path):
    monkeypatch.setattr("m32_bridge.installer.first_run.setup_runtime", lambda **kwargs: {
        "ok": True,
        "status": "NOT_SAVED",
        "configured_host": kwargs["host"],
        "configured_port": kwargs["port"],
        "attempted_path": "/info",
        "saved": False,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    })
    monkeypatch.setattr("m32_bridge.cli.setup_info_probe", lambda *args, **kwargs: CONNECTED_PROBE.copy())
    monkeypatch.setattr("m32_bridge.diagnostics.runtime._probe_info", lambda *args, **kwargs: CONNECTED_PROBE.copy())
    parser = _build_parser()

    setup = _run_command(parser.parse_args(["setup", "--host", "127.0.0.1", "--port", "10023", "--json", "--no-save"]))
    detect = _run_command(parser.parse_args(["detect-device", "--host", "127.0.0.1", "--port", "10023", "--target-type", "emulator", "--json"]))
    doctor = _run_command(parser.parse_args(["doctor-runtime", "--host", "127.0.0.1", "--port", "10023"]))
    status = _run_command(parser.parse_args(["verify-install", "--json", "--home", str(tmp_path)]))

    for result in (setup, detect, doctor, status):
        assert "/set" not in str(result)
        assert result["osc_writes_sent"] == 0
        assert result["hardware_verified"] is False
        assert result.get("production_live_ready") is not True
