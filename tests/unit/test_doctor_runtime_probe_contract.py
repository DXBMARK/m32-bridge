from __future__ import annotations

from m32_bridge import cli
from m32_bridge.installer import runtime_manager


def _local_diagnostics() -> dict:
    return {
        "status": "ok",
        "healthy": True,
        "console_probe": "not_run",
        "network_scan": "not_run",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def test_doctor_runtime_does_not_probe_without_host(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_manager,
        "local_runtime_diagnostics",
        lambda **_kwargs: _local_diagnostics(),
    )

    calls: list[str] = []

    def forbidden_probe(*_args, **_kwargs):
        calls.append("probe")
        raise AssertionError("probe must not run")

    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        forbidden_probe,
    )

    payload = cli.doctor_runtime_command(
        host=None,
        port=None,
        timeout=0.5,
        environ={},
    )

    assert payload["status"] == "ok"
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["attempted_path"] is None
    assert payload["console_probe"] == "not_run"
    assert payload["connection_lifecycle"] == "not_checked"
    assert payload["network_scan"] == "not_run"
    assert payload["scan_attempted"] is False
    assert payload["osc_writes_sent"] == 0
    assert "udp_info_probe_result" not in payload
    assert calls == []


def test_doctor_runtime_probes_explicit_endpoint(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_manager,
        "local_runtime_diagnostics",
        lambda **_kwargs: _local_diagnostics(),
    )

    calls: list[tuple[str, int, float]] = []

    def connected_probe(
        host: str,
        port: int,
        *,
        timeout: float,
    ) -> dict:
        calls.append((host, port, timeout))
        return {
            "udp_info_probe_result": "CONNECTED",
            "attempted_path": "/info",
            "response_address": [host, port],
            "latency_ms": 4,
            "exception_type": None,
            "osc_writes_sent": 0,
        }

    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        connected_probe,
    )

    payload = cli.doctor_runtime_command(
        host="127.0.0.1",
        port=10023,
        timeout=0.25,
        environ={},
    )

    assert calls == [
        ("127.0.0.1", 10023, 0.25)
    ]
    assert payload["status"] == "ok"
    assert payload["configured_host"] == "127.0.0.1"
    assert payload["configured_port"] == 10023
    assert payload["attempted_path"] == "/info"
    assert payload["console_probe"] == "checked"
    assert payload["connection_lifecycle"] == "connected"
    assert payload["udp_info_probe_result"] == "CONNECTED"
    assert payload["response_address"] == [
        "127.0.0.1",
        10023,
    ]
    assert payload["latency_ms"] == 4
    assert payload["connected"] is True
    assert payload["network_scan"] == "not_run"
    assert payload["scan_attempted"] is False
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False


def test_doctor_runtime_reports_failed_read_only_probe(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_manager,
        "local_runtime_diagnostics",
        lambda **_kwargs: _local_diagnostics(),
    )

    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        lambda host, port, *, timeout: {
            "udp_info_probe_result": "NOT_CONNECTED",
            "attempted_path": "/info",
            "response_address": None,
            "latency_ms": None,
            "exception_type": "TimeoutError",
            "osc_writes_sent": 0,
        },
    )

    payload = cli.doctor_runtime_command(
        host="192.0.2.10",
        port=None,
        timeout=0.1,
        environ={},
    )

    assert payload["status"] == "ok"
    assert payload["configured_host"] == "192.0.2.10"
    assert payload["configured_port"] == 10023
    assert payload["udp_info_probe_result"] == "NOT_CONNECTED"
    assert payload["attempted_path"] == "/info"
    assert payload["connected"] is False
    assert payload["connection_lifecycle"] == "not_connected"
    assert payload["exception_type"] == "TimeoutError"
    assert payload["network_scan"] == "not_run"
    assert payload["scan_attempted"] is False
    assert payload["osc_writes_sent"] == 0
