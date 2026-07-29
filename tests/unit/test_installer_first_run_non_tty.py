from __future__ import annotations

import json
import socket

from m32_bridge.cli import _run_command, _build_parser
from m32_bridge.installer.first_run import check_github_install_source, check_internet_connectivity, non_tty_setup_response


def test_non_tty_setup_returns_structured_json_without_prompt(tmp_path):
    result = non_tty_setup_response(
        environ={"SHELL": "/bin/bash"},
        home=tmp_path,
        internet_checker=lambda host, port, timeout: True,
        github_checker=lambda host, port, timeout: False,
    )

    encoded = json.dumps(result)
    assert "required_actions" in encoded
    assert result["structured"] is True
    assert result["environment"]["internet_status"] == "ONLINE"
    assert result["environment"]["github_install_source"] == "OFFLINE"
    assert result["osc_writes_sent"] == 0
    assert result["hardware_verified"] is False
    assert result["production_live_ready"] is False


def test_cli_setup_without_host_does_not_hang_or_guess():
    parser = _build_parser()
    args = parser.parse_args(["setup", "--json"])

    result = _run_command(args)

    assert result["status"] in {"RUNTIME_SETUP_REQUIRED", "SETUP_INPUT_REQUIRED", "NO_CONSOLE_HOST"}
    assert result["guessed_host"] is None
    assert result["scan_attempted"] is False
    assert result["osc_writes_sent"] == 0


def test_connectivity_checks_return_mocked_online_offline_and_timeout():
    assert check_internet_connectivity(checker=lambda host, port, timeout: True) == "ONLINE"
    assert check_github_install_source(checker=lambda host, port, timeout: False) == "OFFLINE"

    def timeout_checker(host: str, port: int, timeout: float) -> bool:
        raise socket.timeout("timed out")

    assert check_github_install_source(checker=timeout_checker) == "TIMEOUT"


def test_windows_non_tty_missing_uv_uses_powershell_irm_action(monkeypatch, tmp_path):
    monkeypatch.setattr("m32_bridge.installer.first_run.detect_uv_status", lambda: type("State", (), {"uv_status": "manual_action_required"})())
    result = non_tty_setup_response(environ={"PSModulePath": "Modules", "LOCALAPPDATA": str(tmp_path)}, home=tmp_path)

    action = result["required_actions"][0]
    assert result["environment"]["surface"] == "windows"
    assert "irm" in action["command_preview"].lower()
    assert "powershell" in action["download_guidance"].lower()
    assert "curl" not in action["command_preview"].lower()


def test_posix_non_tty_missing_uv_uses_curl_wget_manual_guidance(monkeypatch, tmp_path):
    monkeypatch.setattr("m32_bridge.installer.first_run.detect_uv_status", lambda: type("State", (), {"uv_status": "manual_action_required"})())
    result = non_tty_setup_response(environ={"SHELL": "/bin/bash"}, home=tmp_path)

    action = result["required_actions"][0]
    assert result["environment"]["surface"] == "posix"
    assert "curl" in action["command_preview"].lower()
    assert "wget" in action["download_guidance"].lower()
    assert "manual" in action["download_guidance"].lower()
