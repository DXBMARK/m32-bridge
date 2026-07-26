from __future__ import annotations

import pytest

from m32_bridge.fake_m32.server import FakeM32Server


def test_shell_read_only_slash_commands_send_no_writes_to_fake_m32():
    from m32_bridge.interactive_shell import dispatch_slash_command

    try:
        server = FakeM32Server().start()
    except PermissionError as exc:
        pytest.skip(f"local UDP unavailable in this sandbox: {exc}")
    try:
        for command in ["/runsetup", "/getinfo", "/config", "/test", "/doctor", "/detect"]:
            payload = dispatch_slash_command(
                command,
                host=server.address[0],
                port=server.address[1],
                target_type="emulator",
            )
            assert payload["osc_writes_sent"] == 0
            assert payload["hardware_verified"] is False

        assert server.state.xremote_count == 0
        assert server.write_packets == []
    finally:
        server.stop()
