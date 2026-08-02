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


def test_get_info_missing_host_returns_setup_required_without_probe(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    for name in (
        "M32_CONFIG",
        "M32_CONSOLE_HOST",
        "M32_CONSOLE_PORT",
    ):
        monkeypatch.delenv(name, raising=False)

    calls: list[str] = []

    def forbidden_get_info_runtime(**_kwargs):
        calls.append("get_info_runtime")
        raise AssertionError(
            "get_info_runtime must not run before setup"
        )

    monkeypatch.setattr(
        "m32_bridge.cli.get_info_runtime",
        forbidden_get_info_runtime,
    )

    parser = _build_parser()
    args = parser.parse_args(["get-info", "--json"])

    result = _run_command(args)

    assert result["ok"] is False
    assert result["status"] == "SETUP_REQUIRED"
    assert result["error_code"] == "SETUP_REQUIRED"
    assert result["precondition_state"] == "setup_required"
    assert result["console_configured"] is False
    assert result["configured_host"] is None
    assert result["configured_port"] is None
    assert result["required_action"] == "m32-bridge setup"
    assert result["attempted_path"] == "not_attempted"
    assert result["console_probe"] == "not_run"
    assert result["network_scan"] == "not_run"
    assert result["osc_writes_sent"] == 0
    assert calls == []
