from __future__ import annotations


def test_installer_mcp_guidance_uses_manual_copy_stdio_snippet(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")

    assert guidance["manual_copy_only"] is True
    assert guidance["transport"] == "stdio"
    assert guidance["command"] == "m32-bridge"
    assert guidance["args"] == ["mcp-server"]
    assert guidance["default_snippet"] == {"command": "m32-bridge", "args": ["mcp-server"]}
    assert guidance["embeds_host_port_by_default"] is False
    assert "host" not in guidance["default_snippet"]
    assert "port" not in guidance["default_snippet"]
    assert guidance["config_written"] is False
    assert guidance["app_opened"] is False
    assert guidance["osc_writes_sent"] == 0
    assert guidance["hardware_verified"] is False
    assert guidance["production_live_ready"] is False


def test_installer_mcp_guidance_returns_client_entries_with_status(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    (tmp_path / ".codex").mkdir()
    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")

    client_ids = {client["client_id"] for client in guidance["client_guidance"]}
    assert {"claude_desktop", "codex", "gemini", "antigravity", "chatgpt_desktop", "vscode"}.issubset(client_ids)

    codex = next(client for client in guidance["client_guidance"] if client["client_id"] == "codex")
    assert codex["status"] == "detected"
    assert codex["status_indicator"] == "active_green"
    assert codex["config_mode"] == "manual_copy"
    assert codex["command"] == "m32-bridge"
    assert codex["args"] == ["mcp-server"]
    assert codex["embeds_host_port"] is False
    assert codex["config_written"] is False
    assert codex["app_opened"] is False
    assert codex["next_steps"]

    claude = next(client for client in guidance["client_guidance"] if client["client_id"] == "claude_desktop")
    assert claude["status"] == "not_detected"
    assert claude["status_indicator"] == "inactive_grey"


def test_post_install_verification_includes_mcp_guidance(tmp_path, monkeypatch):
    from m32_bridge.installer import verification
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    monkeypatch.setattr(verification, "detect_uv_status", lambda: RuntimeManagerState(uv_status="present"))

    output = verification.render_post_install_verification(environ={}, home=tmp_path)

    assert output["mcp_guidance"]["command"] == "m32-bridge"
    assert output["mcp_guidance"]["args"] == ["mcp-server"]
    assert output["mcp_guidance"]["manual_copy_only"] is True
