from __future__ import annotations

import yaml

from m32_bridge.config.runtime import (
    save_runtime_config,
)
from m32_bridge.fake_m32.server import FakeM32Server
from m32_bridge.mcp import read_tools
from m32_bridge.mcp.server import RuntimeContext
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.transport import OscTransport


def _save_user_config(
    home,
    endpoint: tuple[str, int],
    *,
    target_type: str = "emulator",
):
    path = (
        home
        / ".m32-bridge"
        / "runtime.yaml"
    )

    save_runtime_config(
        path=path,
        host=endpoint[0],
        port=endpoint[1],
        intended_target_type=target_type,
        label="dynamic-test-endpoint",
    )

    return path


def test_runtime_context_uses_saved_dynamic_endpoint(
    monkeypatch,
    tmp_path,
):
    server = FakeM32Server().start()

    try:
        monkeypatch.setenv(
            "HOME",
            str(tmp_path),
        )

        _save_user_config(
            tmp_path,
            server.address,
        )

        context = RuntimeContext.from_env({})

        assert context.target.configured is True
        assert (
            context.target.host,
            context.target.port,
        ) == server.address
        assert (
            context.target.target_kind
            == "fake_m32"
        )

    finally:
        server.stop()


def test_environment_dynamic_endpoint_overrides_saved_endpoint(
    monkeypatch,
    tmp_path,
):
    saved_server = FakeM32Server().start()
    override_server = FakeM32Server().start()

    try:
        monkeypatch.setenv(
            "HOME",
            str(tmp_path),
        )

        _save_user_config(
            tmp_path,
            saved_server.address,
        )

        context = RuntimeContext.from_env(
            {
                "M32_CONSOLE_HOST": (
                    override_server.address[0]
                ),
                "M32_CONSOLE_PORT": str(
                    override_server.address[1]
                ),
            }
        )

        assert context.target.configured is True
        assert (
            context.target.host,
            context.target.port,
        ) == override_server.address
        assert (
            context.target.host,
            context.target.port,
        ) != saved_server.address

    finally:
        override_server.stop()
        saved_server.stop()


def test_explicit_legacy_config_uses_its_dynamic_endpoint(
    monkeypatch,
    tmp_path,
):
    saved_server = FakeM32Server().start()
    legacy_server = FakeM32Server().start()

    try:
        monkeypatch.setenv(
            "HOME",
            str(tmp_path),
        )

        _save_user_config(
            tmp_path,
            saved_server.address,
        )

        legacy_path = (
            tmp_path
            / "legacy-runtime.yaml"
        )

        legacy_path.write_text(
            yaml.safe_dump(
                {
                    "target": {
                        "kind": "fake_m32",
                        "osc_host": (
                            legacy_server.address[0]
                        ),
                        "osc_port": (
                            legacy_server.address[1]
                        ),
                    },
                    "transports": {
                        "stdio": {
                            "enabled": True,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        context = RuntimeContext.from_env(
            {
                "M32_CONFIG": str(
                    legacy_path
                ),
            }
        )

        assert context.target.configured is True
        assert (
            context.target.host,
            context.target.port,
        ) == legacy_server.address
        assert (
            context.target.host,
            context.target.port,
        ) != saved_server.address

    finally:
        legacy_server.stop()
        saved_server.stop()


def test_runtime_context_without_config_is_unconfigured(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv(
        "HOME",
        str(tmp_path),
    )

    context = RuntimeContext.from_env({})

    assert context.target.configured is False
    assert context.target.host is None
    assert context.target.port is None


def test_runtime_diagnostics_handler_forwards_transport_endpoint(
    monkeypatch,
):
    server = FakeM32Server().start()

    try:
        transport = OscTransport(
            host=server.address[0],
            port=server.address[1],
        )
        client = OscClient(transport)

        captured: dict[str, object] = {}

        def fake_runtime_diagnostics(
            *,
            host=None,
            port=None,
            timeout=None,
            environ=None,
        ):
            captured.update(
                {
                    "host": host,
                    "port": port,
                    "timeout": timeout,
                    "environ": environ,
                }
            )

            return {
                "status": "ok",
                "configured_host": host,
                "configured_port": port,
            }

        monkeypatch.setattr(
            read_tools,
            "runtime_diagnostics",
            fake_runtime_diagnostics,
        )

        result = (
            read_tools
            .m32_runtime_diagnostics(client)
        )

        assert (
            captured["host"],
            captured["port"],
        ) == server.address

        assert (
            captured["timeout"]
            == transport.timeout
        )

        assert (
            result["configured_host"],
            result["configured_port"],
        ) == server.address

    finally:
        server.stop()
