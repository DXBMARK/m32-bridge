from __future__ import annotations


def test_claude_mcp_guidance_is_manual_copy_and_does_not_embed_host_or_port():
    from m32_bridge.diagnostics.mcp_guidance import build_mcp_launch_guidance

    guidance = build_mcp_launch_guidance(host_app="claude")

    assert guidance["manual_copy_required"] is True
    assert guidance["embeds_host_port"] is False
    assert guidance["command"] == "m32-bridge"
    assert guidance["args"] == ["mcp-server"]
    assert "host" not in guidance["snippet"]
    assert "port" not in guidance["snippet"]
    assert "M32_CONSOLE_HOST" not in guidance["snippet"]
    assert "py -m" not in guidance["snippet"]
    assert guidance["stdout_protocol_clean"] is True
    assert guidance["logs_to_stderr"] is True
    assert guidance["opens_network_port"] is False


def test_advanced_env_override_example_is_clearly_labelled_manual_only():
    from m32_bridge.diagnostics.mcp_guidance import build_mcp_launch_guidance

    guidance = build_mcp_launch_guidance(host_app="generic_ai", include_advanced_env_example=True)

    example = guidance["advanced_env_override_example"]
    assert example["label"].lower().startswith("advanced")
    assert example["manual_only"] is True
    assert "M32_CONSOLE_HOST" in example["env"]
    assert "M32_CONSOLE_PORT" in example["env"]
    assert guidance["embeds_host_port"] is False


def test_mcp_guidance_never_modifies_host_configuration_files(tmp_path):
    from m32_bridge.diagnostics.mcp_guidance import build_mcp_launch_guidance

    config_path = tmp_path / "claude_desktop_config.json"
    guidance = build_mcp_launch_guidance(host_app="claude", host_config_path=config_path)

    assert guidance["manual_copy_required"] is True
    assert config_path.exists() is False
    assert guidance["host_config_modified"] is False
