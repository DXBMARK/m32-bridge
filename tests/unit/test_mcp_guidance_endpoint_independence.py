from __future__ import annotations

from pathlib import Path

from m32_bridge.installer.mcp_guidance import (
    render_mcp_guidance,
)


def test_guidance_declares_saved_config_default_when_config_is_absent(
    tmp_path: Path,
):
    guidance = render_mcp_guidance(
        environ={},
        home=tmp_path,
        os_family="linux",
    )

    assert (
        guidance["reads_saved_user_config_by_default"]
        is True
    )

    assert (
        guidance["runtime_config_inspection"]
        == "not_configured"
    )

    assert guidance["configured_host"] is None
    assert guidance["configured_port"] is None

    assert (
        guidance["embeds_host_port_by_default"]
        is False
    )

    assert all(
        not profile.get("environment")
        for profile in guidance["client_guidance"]
    )


def test_advanced_overrides_use_endpoint_placeholders(
    tmp_path: Path,
):
    guidance = render_mcp_guidance(
        environ={},
        home=tmp_path,
        os_family="linux",
    )

    examples = guidance[
        "advanced_override_examples"
    ]

    host_example = next(
        item
        for item in examples
        if "M32_CONSOLE_HOST" in item["env"]
    )

    port_example = next(
        item
        for item in examples
        if "M32_CONSOLE_PORT" in item["env"]
    )

    assert host_example["env"] == {
        "M32_CONSOLE_HOST": "<console-host>"
    }

    assert port_example["env"] == {
        "M32_CONSOLE_PORT": "<console-port>"
    }


def test_user_facing_guidance_has_no_fixed_endpoint_examples():
    root = Path(__file__).resolve().parents[2]

    source_paths = (
        root
        / "src/m32_bridge/installer/"
        "mcp_guidance.py",
        root
        / "src/m32_bridge/diagnostics/"
        "mcp_guidance.py",
        root
        / "src/m32_bridge/installer/"
        "script_runtime.py",
        root
        / "src/m32_bridge/installer/"
        "tty_app.py",
    )

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in source_paths
    )

    assert "192.168.8.120" not in combined

    assert (
        'M32_CONSOLE_PORT": "10023"'
        not in combined
    )

    assert (
        '"reads_saved_user_config_by_default": False'
        not in combined
    )
