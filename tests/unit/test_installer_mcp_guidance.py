from __future__ import annotations

import json

import m32_bridge.cli as cli_module


def test_installer_mcp_guidance_uses_manual_copy_stdio_snippet(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")
    launcher = str(tmp_path / ".local" / "bin" / "m32-bridge")

    assert guidance["manual_copy_only"] is True
    assert guidance["transport"] == "stdio"
    assert guidance["product"] == "X32-Bridge MCP"
    assert guidance["server_name"] == "x32-bridge-mcp"
    assert guidance["command"] == launcher
    assert guidance["launcher_path"] == launcher
    assert guidance["args"] == ["mcp-server"]
    assert guidance["default_snippet"] == {"command": launcher, "args": ["mcp-server"]}
    assert ".venv" not in guidance["command"]
    assert "python -m" not in guidance["command"]
    assert guidance["embeds_host_port_by_default"] is False
    assert "host" not in guidance["default_snippet"]
    assert "port" not in guidance["default_snippet"]
    assert guidance["environment_required"] == {}
    assert guidance["environment_overrides_present"] == []
    assert guidance["config_written"] is False
    assert guidance["app_opened"] is False
    assert guidance["osc_writes_sent"] == 0
    assert guidance["network_scan"] is False
    assert guidance["console_probe"] == "not_run"
    assert guidance["hardware_verified"] is False
    assert guidance["production_live_ready"] is False


def test_installer_mcp_guidance_returns_client_entries_with_status(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    (tmp_path / ".codex").mkdir()
    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")
    launcher = str(tmp_path / ".local" / "bin" / "m32-bridge")

    client_ids = {client["client_id"] for client in guidance["client_guidance"]}
    assert {"claude", "codex", "gemini", "antigravity", "chatgpt", "generic"} == client_ids

    codex = next(client for client in guidance["client_guidance"] if client["client_id"] == "codex")
    assert codex["config_mode"] == "manual_copy"
    assert codex["command"] == launcher
    assert codex["args"] == ["mcp-server"]
    assert codex["embeds_host_port"] is False
    assert codex["config_written"] is False
    assert codex["app_opened"] is False
    assert codex["next_steps"]

    claude = next(client for client in guidance["client_guidance"] if client["client_id"] == "claude")
    assert claude["generated_snippet"]["mcpServers"]["x32-bridge-mcp"]["command"] == launcher
    assert claude["generated_snippet"]["mcpServers"]["x32-bridge-mcp"]["args"] == ["mcp-server"]
    assert claude["environment"] == {}

    gemini = next(client for client in guidance["client_guidance"] if client["client_id"] == "gemini")
    assert "httpUrl" not in str(gemini["generated_snippet"])

    chatgpt = next(client for client in guidance["client_guidance"] if client["client_id"] == "chatgpt")
    assert chatgpt["args"] == []
    assert chatgpt["generated_snippet"] is None
    assert chatgpt["transport"] == "remote MCP required"
    assert "direct local stdio not available" in chatgpt["official_support_status"]


def test_mcp_guidance_reports_environment_overrides_without_duplicating_endpoint_env(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(
        home=tmp_path,
        environ={"M32_CONSOLE_HOST": "192.0.2.10", "M32_CONSOLE_PORT": "10023", "M32_CONFIG": "/tmp/runtime.yaml"},
        os_family="linux",
    )

    assert guidance["environment_required"] == {}
    assert len(guidance["environment_overrides_present"]) == 3
    assert all(client["environment_required"] == {} for client in guidance["client_guidance"])
    assert all(client["environment"] == {} for client in guidance["client_guidance"])


def test_post_install_verification_includes_mcp_guidance(tmp_path, monkeypatch):
    from m32_bridge.installer import verification
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    monkeypatch.setattr(verification, "detect_uv_status", lambda: RuntimeManagerState(uv_status="present"))

    output = verification.render_post_install_verification(environ={}, home=tmp_path)

    assert output["mcp_guidance"]["command"] == str(tmp_path / ".local" / "bin" / "m32-bridge")
    assert output["mcp_guidance"]["args"] == ["mcp-server"]
    assert output["mcp_guidance"]["manual_copy_only"] is True


def test_mcp_config_plain_cli_renders_selected_claude_profile(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    return_code = cli_module.main(["mcp-config", "--client", "claude"])
    captured = capsys.readouterr()

    assert return_code == 0
    assert captured.err == ""
    assert captured.out.startswith("MCP CLIENT SETUP\n")
    assert not captured.out.lstrip().startswith("{")
    for expected in (
        "Product",
        "Version",
        str(tmp_path / ".local" / "bin" / "m32-bridge"),
        "Runtime configuration",
        "Transport",
        "Environment variables",
        "CLAUDE DESKTOP",
        "Server name",
        "mcp-server",
        "Generated snippet",
        "Verification steps",
        "Warnings / limitations",
    ):
        assert expected in captured.out
    assert "GEMINI CLI" not in captured.out
    assert "\x1b[" not in captured.out


def test_mcp_config_json_cli_is_json_only_and_filters_selected_client(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    return_code = cli_module.main(["mcp-config", "--client", "claude", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert return_code == 0
    assert captured.err == ""
    assert "\x1b[" not in captured.out
    assert captured.out.strip().startswith("{") and captured.out.strip().endswith("}")
    assert list(payload["clients"]) == ["claude"]
    assert [client["client_id"] for client in payload["client_guidance"]] == ["claude"]
    assert payload["config_written"] is False
    assert payload["network_scan"] is False
    assert payload["console_probe"] == "not_run"
    assert payload["osc_writes_sent"] == 0


def test_mcp_config_default_plain_cli_lists_all_clients(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    return_code = cli_module.main(["mcp-config"])
    output = capsys.readouterr().out

    assert return_code == 0
    for client in ("CLAUDE DESKTOP", "CODEX", "GEMINI CLI", "ANTIGRAVITY", "CHATGPT", "GENERIC MCP CLIENT"):
        assert client in output
    assert "Direct local stdio connection" not in output
    assert "direct local stdio not available" in output
    assert "remote MCP required" in output
    assert "\x1b[" not in output


def test_mcp_config_chatgpt_plain_has_no_local_json_profile(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))

    return_code = cli_module.main(["mcp-config", "--client", "chatgpt"])
    output = capsys.readouterr().out

    assert return_code == 0
    assert "CHATGPT" in output
    assert "direct local stdio not available" in output
    assert "remote MCP required" in output
    assert "Generated snippet" not in output
    assert "{" not in output and "}" not in output
