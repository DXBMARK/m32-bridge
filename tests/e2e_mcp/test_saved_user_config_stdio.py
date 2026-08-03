from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    stdio_client,
)

from m32_bridge.config.runtime import (
    DEFAULT_CONSOLE_PORT,
    save_runtime_config,
)
from m32_bridge.fake_m32.server import FakeM32Server


def _start_dynamic_non_default_server():
    while True:
        server = FakeM32Server().start()

        if (
            server.address[1]
            != DEFAULT_CONSOLE_PORT
        ):
            return server

        server.stop()


@pytest.mark.asyncio
async def test_stdio_uses_saved_dynamic_user_endpoint(
    tmp_path: Path,
):
    server = _start_dynamic_non_default_server()

    try:
        runtime_path = (
            tmp_path
            / ".m32-bridge"
            / "runtime.yaml"
        )

        save_runtime_config(
            path=runtime_path,
            host=server.address[0],
            port=server.address[1],
            intended_target_type="emulator",
            label="dynamic-user-endpoint",
        )

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        env["M32_LAUNCHED_FROM"] = (
            "installed_runtime_test"
        )
        env.setdefault(
            "UV_CACHE_DIR",
            "/private/tmp/uv-cache",
        )

        for key in (
            "M32_CONFIG",
            "M32_CONSOLE_HOST",
            "M32_CONSOLE_PORT",
        ):
            env.pop(key, None)

        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "m32_bridge",
                "mcp-server",
            ],
            env=env,
            cwd=Path.cwd(),
        )

        async with stdio_client(params) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:
                await session.initialize()

                result = await session.call_tool(
                    "m32_runtime_diagnostics",
                    {},
                    read_timeout_seconds=timedelta(
                        seconds=3
                    ),
                )

        payload = result.structuredContent

        assert payload["ok"] is True

        diagnostics = payload["result"]

        assert diagnostics["status"] == "ok"

        assert (
            diagnostics[
                "udp_info_probe_result"
            ]
            == "CONNECTED"
        )

        assert (
            diagnostics["configured_host"],
            diagnostics["configured_port"],
        ) == server.address

        assert (
            diagnostics["configured_port"]
            != DEFAULT_CONSOLE_PORT
        )

        assert (
            diagnostics["response_address"]
            == [
                server.address[0],
                server.address[1],
            ]
        )

        assert (
            diagnostics["attempted_path"]
            == "/info"
        )

        assert (
            diagnostics["osc_writes_sent"]
            == 0
        )

        assert (
            diagnostics["hardware_verified"]
            is False
        )

        assert server.write_packets == []

    finally:
        server.stop()
