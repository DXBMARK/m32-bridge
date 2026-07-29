from __future__ import annotations

from m32_bridge.cli import _build_parser, _run_command
from m32_bridge.installer.verification import render_post_install_verification


def test_missing_host_verification_guidance_is_structured_without_guess_or_scan(tmp_path):
    result = render_post_install_verification(environ={"SHELL": "/bin/zsh"}, home=tmp_path)

    assert result["configured_host"] is None
    assert result["configured_port"] is None
    assert result["config_present"] is False
    assert result["error_code"] in {None, "NO_CONSOLE_HOST"}
    assert result["scan_attempted"] is False
    assert result["guessed_host"] is None
    assert result["attempted_path"] is None
    assert result["osc_writes_sent"] == 0


def test_get_info_missing_host_returns_structured_no_console_host_without_probe(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr("m32_bridge.cli.setup_info_probe", lambda *args, **kwargs: calls.append("probe"))
    parser = _build_parser()
    args = parser.parse_args(["get-info", "--json"])

    result = _run_command(args)

    assert result["ok"] is False
    assert result["error_code"] == "NO_CONSOLE_HOST"
    assert result["configured_host"] is None
    assert result["configured_port"] is None
    assert result["scan_attempted"] is False
    assert result["guessed_host"] is None
    assert result["osc_writes_sent"] == 0
    assert calls == []
