from __future__ import annotations

from m32_bridge.mcp.transport_http import prepare_secondary_transport, validate_secondary_transport_config


def test_secondary_transport_is_disabled_by_default():
    result = validate_secondary_transport_config({})

    assert result["status"] == "disabled"
    assert result["enabled"] is False
    assert result["started"] is False
    assert result["network_side_effects"] is False
    assert result["transport"] == "streamable_http"


def test_chatgpt_secure_tunnel_is_optional_only_without_explicit_enable():
    result = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "bind_host": "127.0.0.1",
                    "secure_tunnel_only": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )

    assert result["status"] == "disabled"
    assert result["enabled"] is False
    assert result["started"] is False
    assert result["errors"] == []


def test_public_osc_exposure_is_forbidden_even_when_tunnel_is_enabled():
    result = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "127.0.0.1",
                    "secure_tunnel_only": True,
                    "expose_osc": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )

    assert result["status"] == "denied"
    assert result["started"] is False
    assert result["osc_public"] is False
    assert result["raw_osc_exposed"] is False
    assert "PUBLIC_OSC_FORBIDDEN" in result["error_codes"]


def test_enable_requires_clear_safe_config():
    missing_tunnel = validate_secondary_transport_config(
        {"transports": {"streamable_http": {"enabled": True, "bind_host": "127.0.0.1"}}}
    )
    safe = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "127.0.0.1",
                    "secure_tunnel_only": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )

    assert missing_tunnel["status"] == "denied"
    assert "SECURE_TUNNEL_REQUIRED" in missing_tunnel["error_codes"]
    assert safe["status"] == "ready"
    assert safe["enabled"] is True
    assert safe["started"] is False
    assert safe["would_start"] is True
    assert safe["network_side_effects"] is False


def test_bind_host_must_be_loopback_or_private_not_unspecified_or_public():
    safe_private = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "10.10.0.8",
                    "secure_tunnel_only": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )
    unspecified = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "0.0.0.0",
                    "secure_tunnel_only": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )
    public = validate_secondary_transport_config(
        {
            "transports": {
                "streamable_http": {
                    "enabled": True,
                    "bind_host": "8.8.8.8",
                    "secure_tunnel_only": True,
                    "chatgpt": {"enabled": True, "tunnel": "secure_mcp_tunnel"},
                }
            }
        }
    )

    assert safe_private["status"] == "ready"
    assert unspecified["status"] == "denied"
    assert public["status"] == "denied"
    assert "BIND_HOST_NOT_PRIVATE" in unspecified["error_codes"]
    assert "BIND_HOST_NOT_PRIVATE" in public["error_codes"]


def test_prepare_secondary_transport_never_starts_when_disabled():
    result = prepare_secondary_transport({"transports": {"streamable_http": {"enabled": False}}})

    assert result["status"] == "disabled"
    assert result["started"] is False
    assert result["network_side_effects"] is False
