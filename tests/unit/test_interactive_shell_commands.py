from __future__ import annotations


def test_slash_command_parser_maps_shell_commands_to_cli_equivalents():
    from m32_bridge.interactive_shell import parse_slash_command

    expected = {
        "/help": "m32-bridge help",
        "/runsetup": "m32-bridge setup",
        "/getinfo": "m32-bridge get-info",
        "/config": "m32-bridge config show",
        "/test": "m32-bridge get-info",
        "/doctor": "m32-bridge doctor-runtime",
        "/detect": "m32-bridge detect-device",
        "/mcp": "m32-bridge mcp-server --help",
        "/claude": "m32-bridge mcp guidance",
        "/mode": "m32-bridge mode",
        "/lock": "m32-bridge lock",
        "/unlock": "m32-bridge unlock",
        "/exit": "exit",
    }
    for command, equivalent in expected.items():
        parsed = parse_slash_command(command)
        assert parsed["slash_command"] == command
        assert parsed["mapped_cli_equivalent"] == equivalent
        assert parsed["osc_writes_sent"] == 0


def test_config_set_slash_commands_parse_host_and_port_without_raw_paths():
    from m32_bridge.interactive_shell import parse_slash_command

    host = parse_slash_command("/config set host 192.0.2.10")
    port = parse_slash_command("/config set port 10023")

    assert host["mapped_cli_equivalent"] == "m32-bridge config set --host 192.0.2.10"
    assert port["mapped_cli_equivalent"] == "m32-bridge config set --port 10023"
    assert host["raw_osc_available"] is False
    assert port["arbitrary_path_available"] is False


def test_unknown_or_raw_osc_like_slash_command_is_rejected():
    from m32_bridge.interactive_shell import parse_slash_command

    payload = parse_slash_command("/osc /ch/01/mix/fader 0")

    assert payload["ok"] is False
    assert payload["error_code"] == "UNKNOWN_SHELL_COMMAND"
    assert payload["raw_osc_available"] is False
    assert payload["arbitrary_path_available"] is False
    assert payload["osc_writes_sent"] == 0
