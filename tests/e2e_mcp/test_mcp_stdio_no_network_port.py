from __future__ import annotations

import socket


def test_mcp_stdio_server_creation_does_not_open_network_socket(monkeypatch):
    opened: list[tuple] = []
    real_socket = socket.socket

    def recording_socket(*args, **kwargs):
        opened.append(args)
        return real_socket(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", recording_socket)

    from m32_bridge.mcp.server import create_mcp_stdio_server

    server = create_mcp_stdio_server()

    assert server.name == "m32-bridge-local"
    assert opened == []


def test_default_mcp_guidance_declares_no_network_port():
    from m32_bridge.diagnostics.mcp_guidance import build_mcp_launch_guidance

    guidance = build_mcp_launch_guidance(host_app="claude")

    assert guidance["transport"] == "stdio"
    assert guidance["opens_network_port"] is False
    assert guidance["command"] == "m32-bridge"
    assert guidance["args"] == ["mcp-server"]
