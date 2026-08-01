from __future__ import annotations


def test_advanced_host_and_port_overrides_are_labelled_manual_only(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")
    launcher = str(tmp_path / ".local" / "bin" / "m32-bridge")

    examples = guidance["advanced_override_examples"]
    assert examples
    assert all(example["label"].lower().startswith("advanced manual") for example in examples)
    assert all(example["manual_only"] is True for example in examples)
    assert all(example["default"] is False for example in examples)
    assert all(example["config_mode"] == "manual_copy" for example in examples)

    env_keys = {key for example in examples for key in example["env"]}
    assert {"M32_CONSOLE_HOST", "M32_CONSOLE_PORT"}.issubset(env_keys)
    assert guidance["default_snippet"] == {"command": launcher, "args": ["mcp-server"]}
    assert guidance["embeds_host_port_by_default"] is False


def test_advanced_overrides_do_not_embed_host_or_port_in_default_client_guidance(tmp_path):
    from m32_bridge.installer.mcp_guidance import render_mcp_guidance

    guidance = render_mcp_guidance(home=tmp_path, environ={}, os_family="linux")
    launcher = str(tmp_path / ".local" / "bin" / "m32-bridge")

    for client in guidance["client_guidance"]:
        if client["client_id"] == "chatgpt":
            assert client["command"] == ""
            assert client["args"] == []
        else:
            assert client["command"] == launcher
            assert client["args"] == ["mcp-server"]
        assert client["embeds_host_port"] is False
        assert "host" not in client
        assert "port" not in client
