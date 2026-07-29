from __future__ import annotations

from m32_bridge.cli import _build_parser, _run_command
from m32_bridge.installer.first_run import run_setup_probe


PROBE = {
    "udp_info_probe_result": "CONNECTED",
    "response_address": ["192.0.2.10", 10023],
    "latency_ms": 1,
    "exception_type": None,
    "info_raw": ["V4.13", "M32"],
}


def test_config_save_requires_confirmation(tmp_path):
    config_path = tmp_path / "runtime.yaml"

    result = run_setup_probe(host="192.0.2.10", config_path=config_path, probe_result=PROBE)

    assert result["saved"] is False
    assert not config_path.exists()


def test_confirmed_save_writes_user_config_and_summary(tmp_path):
    config_path = tmp_path / "runtime.yaml"

    result = run_setup_probe(
        host="192.0.2.10",
        port=None,
        label="soundcheck",
        target_type="hardware",
        confirm_save=True,
        config_path=config_path,
        probe_result=PROBE,
    )

    assert result["saved"] is True
    assert config_path.exists()
    assert result["configured_host"] == "192.0.2.10"
    assert result["configured_port"] == 10023
    assert result["config_path"] == str(config_path)
    assert "m32-bridge health" in result["next_commands"]
    assert "m32-bridge mcp-server" in result["next_commands"]


def test_cli_setup_host_json_returns_first_run_summary_fields(monkeypatch, tmp_path):
    def fake_setup_runtime(**kwargs):
        return {
            "ok": True,
            "status": "NOT_SAVED",
            "configured_host": kwargs["host"],
            "configured_port": kwargs["port"],
            "attempted_path": "/info",
            "saved": False,
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        }

    monkeypatch.setattr("m32_bridge.installer.first_run.setup_runtime", fake_setup_runtime)
    parser = _build_parser()
    args = parser.parse_args(["setup", "--host", "192.0.2.10", "--json", "--no-save", "--config-path", str(tmp_path / "runtime.yaml")])

    result = _run_command(args)

    assert result["configured_host"] == "192.0.2.10"
    assert result["configured_port"] == 10023
    assert result["attempted_path"] == "/info"
    assert result["config_path"] == str(tmp_path / "runtime.yaml")
    assert result["next_commands"]
    assert result["detected_clients"]
    assert result["install_path"]
    assert result["launcher_path"]
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False
