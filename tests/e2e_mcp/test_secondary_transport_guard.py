from __future__ import annotations

from m32_bridge.mcp.transport_http import prepare_secondary_transport, validate_secondary_transport_config


def _safe_config(bind_host: str = "127.0.0.1") -> dict[str, object]:
    return {
        "transports": {
            "streamable_http": {
                "enabled": True,
                "bind_host": bind_host,
                "port": 8765,
                "secure_tunnel_only": True,
                "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
            }
        }
    }


def test_secondary_transport_does_not_make_osc_public():
    result = prepare_secondary_transport(_safe_config())

    assert result["status"] == "ready"
    assert result["osc_public"] is False
    assert result["osc_bind_host"] is None
    assert result["raw_osc_exposed"] is False
    assert result["exposed_protocols"] == ["mcp"]


def test_secondary_transport_does_not_open_raw_osc_or_arbitrary_path_surface():
    result = prepare_secondary_transport(_safe_config())

    assert result["raw_osc_exposed"] is False
    assert result["arbitrary_path_exposed"] is False
    assert "osc" not in result["exposed_protocols"]
    assert result["approval_token_supported"] is False


def test_bind_host_must_be_loopback_or_private_only():
    loopback = prepare_secondary_transport(_safe_config("127.0.0.1"))
    private = prepare_secondary_transport(_safe_config("192.168.1.20"))
    public = prepare_secondary_transport(_safe_config("8.8.8.8"))
    unspecified = prepare_secondary_transport(_safe_config("0.0.0.0"))

    assert loopback["status"] == "ready"
    assert private["status"] == "ready"
    assert public["status"] == "denied"
    assert unspecified["status"] == "denied"
    assert "BIND_HOST_NOT_PRIVATE" in public["error_codes"]
    assert "BIND_HOST_NOT_PRIVATE" in unspecified["error_codes"]


def test_disabled_config_does_not_start_secondary_transport():
    result = prepare_secondary_transport({"transports": {"streamable_http": {"enabled": False, "bind_host": "127.0.0.1"}}})

    assert result["status"] == "disabled"
    assert result["enabled"] is False
    assert result["started"] is False
    assert result["would_start"] is False
    assert result["network_side_effects"] is False


def test_malformed_or_unsafe_config_returns_structured_denial():
    malformed = validate_secondary_transport_config({"transports": {"streamable_http": "enabled"}})
    unsafe = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "0.0.0.0",
                    "secure_tunnel_only": False,
                    "allow_raw_osc": True,
                    "chatgpt": {"enabled": True, "tunnel": "plain_http"},
                }
            }
        }
    )

    assert malformed["status"] == "denied"
    assert "CONFIG_OBJECT_REQUIRED" in malformed["error_codes"]
    assert unsafe["status"] == "denied"
    assert {"BIND_HOST_NOT_PRIVATE", "SECURE_TUNNEL_REQUIRED", "RAW_OSC_FORBIDDEN"}.issubset(
        set(unsafe["error_codes"])
    )
    assert unsafe["started"] is False
    assert unsafe["network_side_effects"] is False
