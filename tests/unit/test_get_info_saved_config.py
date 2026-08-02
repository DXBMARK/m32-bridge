from __future__ import annotations

from m32_bridge import cli
from m32_bridge.config.runtime import (
    default_user_config_path,
    save_runtime_config,
)


def _timeout_probe() -> dict:
    return {
        "udp_info_probe_result": "NOT_CONNECTED",
        "attempted_path": "/info",
        "connected": False,
        "response_address": None,
        "latency_ms": None,
        "exception_type": "TimeoutError",
        "info_raw": None,
        "osc_writes_sent": 0,
    }


def test_get_info_uses_saved_user_config_without_cli_host(
    tmp_path,
):
    config = tmp_path / "runtime.yaml"

    save_runtime_config(
        path=config,
        host="10.0.0.20",
        port=11101,
        intended_target_type="unknown",
        label="console-test",
    )

    original = config.read_bytes()

    payload = cli.get_info_runtime(
        host=None,
        port=None,
        environ={},
        user_config_path=config,
        probe_result=_timeout_probe(),
    )

    assert payload["ok"] is False
    assert payload["status"] == "NOT_CONNECTED"
    assert payload["error_code"] == "NOT_CONNECTED"
    assert payload["configured_host"] == "10.0.0.20"
    assert payload["configured_port"] == 11101
    assert payload["attempted_path"] == "/info"
    assert payload["connected"] is False
    assert payload["scan_attempted"] is False
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False
    assert payload["config_path"] == str(config)
    assert config.read_bytes() == original


def test_get_info_environment_overrides_saved_endpoint(
    tmp_path,
):
    config = tmp_path / "runtime.yaml"

    save_runtime_config(
        path=config,
        host="10.0.0.20",
        port=11101,
        intended_target_type="unknown",
    )

    payload = cli.get_info_runtime(
        host=None,
        port=None,
        environ={
            "M32_CONSOLE_HOST": "192.0.2.55",
            "M32_CONSOLE_PORT": "12000",
        },
        user_config_path=config,
        probe_result=_timeout_probe(),
    )

    assert payload["configured_host"] == "192.0.2.55"
    assert payload["configured_port"] == 12000
    assert payload["status"] == "NOT_CONNECTED"
    assert payload["scan_attempted"] is False
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_get_info_cli_command_reads_default_saved_config(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))

    config = default_user_config_path()

    save_runtime_config(
        path=config,
        host="10.0.0.20",
        port=11101,
        intended_target_type="unknown",
        label="console-test",
    )

    calls: list[tuple[str, int, float]] = []

    def fake_probe(
        host: str,
        port: int,
        *,
        timeout: float,
    ) -> dict:
        calls.append((host, port, timeout))
        return _timeout_probe()

    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        fake_probe,
    )

    args = cli._build_parser().parse_args(
        ["get-info", "--json"]
    )

    payload = cli._run_command(args)

    assert calls == [("10.0.0.20", 11101, 0.5)]
    assert payload["status"] == "NOT_CONNECTED"
    assert payload["error_code"] == "NOT_CONNECTED"
    assert payload["configured_host"] == "10.0.0.20"
    assert payload["configured_port"] == 11101
    assert payload["attempted_path"] == "/info"
    assert payload["connected"] is False
    assert payload["scan_attempted"] is False
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_get_info_missing_config_does_not_probe(
    monkeypatch,
    tmp_path,
):
    calls: list[str] = []

    def forbidden_probe(*args, **kwargs):
        calls.append("probe")
        raise AssertionError("probe must not run")

    monkeypatch.setattr(
        cli,
        "setup_info_probe",
        forbidden_probe,
    )

    payload = cli.get_info_runtime(
        host=None,
        port=None,
        environ={},
        user_config_path=tmp_path / "missing.yaml",
    )

    assert payload["ok"] is False
    assert payload["status"] == "NO_CONSOLE_HOST"
    assert payload["error_code"] == "NO_CONSOLE_HOST"
    assert payload["configured_host"] is None
    assert payload["configured_port"] is None
    assert payload["scan_attempted"] is False
    assert payload["network_scan"] == "not_run"
    assert payload["osc_writes_sent"] == 0
    assert calls == []
