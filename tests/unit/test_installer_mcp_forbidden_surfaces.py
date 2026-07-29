from __future__ import annotations


def test_installer_mcp_guidance_excludes_forbidden_surfaces(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")

    assert guidance["raw_osc_available"] is False
    assert guidance["arbitrary_path_available"] is False
    assert guidance["shell_execution_available"] is False
    assert guidance["remote_mcp_available"] is False
    assert "chatgpt_tunnel_started" not in guidance
    assert guidance["background_service_started"] is False
    assert "approval_token_supported" not in guidance
    assert guidance["opens_network_port"] is False
    assert guidance["osc_writes_sent"] == 0
    assert guidance["hardware_verified"] is False
    assert guidance["production_live_ready"] is False


def test_installer_mcp_guidance_output_omits_dangerous_commands(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")
    text = str(guidance).lower()

    assert "send_raw_osc" not in text
    assert "execute_shell" not in text
    assert "approval_token" not in text
    assert "remote mcp" not in text
    assert "tunnel" not in text
    assert "/set" not in text
