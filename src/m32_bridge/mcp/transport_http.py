"""Guardrails for the optional Streamable HTTP MCP transport.

This module validates whether the optional ChatGPT-facing transport would be
allowed to start. It deliberately does not bind sockets or create tunnels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Any, Mapping

APPROVED_TUNNELS = {"secure_mcp_tunnel", "approved_outbound_secure_tunnel"}
TRANSPORT_NAME = "streamable_http"


@dataclass(frozen=True)
class TransportGuardError:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class SecondaryTransportGuardResult:
    status: str
    enabled: bool
    bind_host: str | None = None
    bind_port: int | None = None
    started: bool = False
    would_start: bool = False
    network_side_effects: bool = False
    transport: str = TRANSPORT_NAME
    tunnel: str | None = None
    errors: tuple[TransportGuardError, ...] = field(default_factory=tuple)
    osc_public: bool = False
    osc_bind_host: str | None = None
    raw_osc_exposed: bool = False
    arbitrary_path_exposed: bool = False
    approval_token_supported: bool = False
    exposed_protocols: tuple[str, ...] = ("mcp",)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "enabled": self.enabled,
            "bind_host": self.bind_host,
            "bind_port": self.bind_port,
            "started": self.started,
            "would_start": self.would_start,
            "network_side_effects": self.network_side_effects,
            "transport": self.transport,
            "tunnel": self.tunnel,
            "errors": [error.to_dict() for error in self.errors],
            "error_codes": [error.code for error in self.errors],
            "osc_public": self.osc_public,
            "osc_bind_host": self.osc_bind_host,
            "raw_osc_exposed": self.raw_osc_exposed,
            "arbitrary_path_exposed": self.arbitrary_path_exposed,
            "approval_token_supported": self.approval_token_supported,
            "exposed_protocols": list(self.exposed_protocols),
        }


def validate_secondary_transport_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a structured guard decision for optional Streamable HTTP config."""

    return _evaluate_secondary_transport(config).to_dict()


def prepare_secondary_transport(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate optional transport readiness without starting a network server."""

    return _evaluate_secondary_transport(config).to_dict()


def _evaluate_secondary_transport(config: Mapping[str, Any] | None) -> SecondaryTransportGuardResult:
    transport_config, malformed = _transport_config(config)
    if malformed:
        return _denied(malformed)

    if not transport_config.get("enabled", False):
        return SecondaryTransportGuardResult(status="disabled", enabled=False)

    errors = _validate_enabled_transport(transport_config)
    if errors:
        return _denied(errors, bind_host=_string_or_none(transport_config.get("bind_host")), tunnel=_configured_tunnel(transport_config))

    return SecondaryTransportGuardResult(
        status="ready",
        enabled=True,
        bind_host=str(transport_config["bind_host"]),
        bind_port=_port_or_none(transport_config.get("port")),
        tunnel=_configured_tunnel(transport_config),
        started=False,
        would_start=True,
        network_side_effects=False,
    )


def _transport_config(config: Mapping[str, Any] | None) -> tuple[dict[str, Any], tuple[TransportGuardError, ...]]:
    if config is None:
        return {}, ()
    if not isinstance(config, Mapping):
        return {}, (_error("CONFIG_OBJECT_REQUIRED", "secondary transport config must be an object"),)

    transports = config.get("transports", {})
    if transports is None:
        return {}, ()
    if not isinstance(transports, Mapping):
        return {}, (_error("CONFIG_OBJECT_REQUIRED", "transports config must be an object"),)

    transport = transports.get(TRANSPORT_NAME, {})
    if transport is None:
        return {}, ()
    if not isinstance(transport, Mapping):
        return {}, (_error("CONFIG_OBJECT_REQUIRED", "streamable_http config must be an object"),)
    return dict(transport), ()


def _validate_enabled_transport(transport_config: Mapping[str, Any]) -> tuple[TransportGuardError, ...]:
    errors: list[TransportGuardError] = []
    bind_host = transport_config.get("bind_host")
    if not isinstance(bind_host, str) or not bind_host:
        errors.append(_error("BIND_HOST_REQUIRED", "enabled secondary transport requires bind_host"))
    elif not _is_loopback_or_private_bind(bind_host):
        errors.append(_error("BIND_HOST_NOT_PRIVATE", "bind_host must be loopback or private and must not be public"))

    if transport_config.get("secure_tunnel_only") is not True:
        errors.append(_error("SECURE_TUNNEL_REQUIRED", "enabled secondary transport requires secure_tunnel_only=true"))

    tunnel = _configured_tunnel(transport_config)
    if tunnel not in APPROVED_TUNNELS:
        errors.append(_error("SECURE_TUNNEL_REQUIRED", "ChatGPT transport requires Secure MCP Tunnel or an approved secure tunnel"))

    port = transport_config.get("port")
    if port is not None and (not isinstance(port, int) or port < 1 or port > 65535):
        errors.append(_error("PORT_INVALID", "port must be null or an integer from 1 to 65535"))

    if _truthy_any(transport_config, ("expose_osc", "allow_public_osc", "osc_public")):
        errors.append(_error("PUBLIC_OSC_FORBIDDEN", "OSC endpoint must never be exposed through the secondary transport"))
    if _truthy_any(transport_config, ("allow_raw_osc", "raw_osc", "raw_osc_enabled")):
        errors.append(_error("RAW_OSC_FORBIDDEN", "raw OSC access is not exposed through MCP"))
    if transport_config.get("osc_exposure") in {"public", "internet", "wan"}:
        errors.append(_error("PUBLIC_OSC_FORBIDDEN", "public OSC exposure is forbidden"))

    return tuple(errors)


def _configured_tunnel(transport_config: Mapping[str, Any]) -> str | None:
    tunnel = transport_config.get("tunnel")
    chatgpt = transport_config.get("chatgpt")
    if isinstance(chatgpt, Mapping):
        tunnel = chatgpt.get("tunnel", tunnel)
    return tunnel if isinstance(tunnel, str) else None


def _is_loopback_or_private_bind(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        parsed = ip_address(normalized)
    except ValueError:
        return False
    if parsed.is_unspecified or parsed.is_global or parsed.is_multicast:
        return False
    return parsed.is_loopback or parsed.is_private


def _truthy_any(config: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(config.get(key) is True for key in keys)


def _port_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _denied(
    errors: tuple[TransportGuardError, ...],
    *,
    bind_host: str | None = None,
    tunnel: str | None = None,
) -> SecondaryTransportGuardResult:
    return SecondaryTransportGuardResult(status="denied", enabled=False, bind_host=bind_host, tunnel=tunnel, errors=errors)


def _error(code: str, message: str) -> TransportGuardError:
    return TransportGuardError(code=code, message=message)
