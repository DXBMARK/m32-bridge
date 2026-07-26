from __future__ import annotations


def test_shell_help_documents_slash_commands_as_shell_only():
    from m32_bridge.interactive_shell import shell_help

    payload = shell_help()
    text = payload["text"]

    assert payload["ok"] is True
    assert payload["status"] == "HELP"
    assert "inside the m32-bridge interactive shell" in text
    assert "standalone OS terminal commands" in text
    for command in ["/help", "/runsetup", "/getinfo", "/config", "/detect", "/lock", "/unlock", "/exit"]:
        assert command in text
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False


def test_exit_command_returns_shell_exit_without_writes():
    from m32_bridge.interactive_shell import dispatch_slash_command

    payload = dispatch_slash_command("/exit")

    assert payload["ok"] is True
    assert payload["status"] == "EXIT"
    assert payload["exit"] is True
    assert payload["osc_writes_sent"] == 0
