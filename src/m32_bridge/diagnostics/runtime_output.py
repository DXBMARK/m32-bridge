"""Common structured runtime output envelope."""

from __future__ import annotations

from typing import Any


def runtime_output(
    *,
    ok: bool,
    status: str,
    error_code: str | None = None,
    message: str | None = None,
    configured_host: str | None = None,
    configured_port: int | None = None,
    attempted_path: str | None = None,
    latency_ms: float | None = None,
    exception_type: str | None = None,
    response_address: Any = None,
    connected: bool | None = None,
    classification: str | None = None,
    osc_writes_sent: int = 0,
    hardware_verified: bool = False,
    production_live_ready: bool = False,
    unsupported_or_timeout_paths: list[dict[str, Any]] | None = None,
    data: dict[str, Any] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "status": status,
        "error_code": error_code,
        "message": message,
        "configured_host": configured_host,
        "configured_port": configured_port,
        "attempted_path": attempted_path,
        "latency_ms": latency_ms,
        "exception_type": exception_type,
        "osc_writes_sent": osc_writes_sent,
        "hardware_verified": hardware_verified,
        "production_live_ready": production_live_ready,
        "data": data or {},
        "recommendations": recommendations or [],
    }
    if response_address is not None:
        payload["response_address"] = response_address
    if connected is not None:
        payload["connected"] = connected
    if classification is not None:
        payload["classification"] = classification
    if unsupported_or_timeout_paths is not None:
        payload["unsupported_or_timeout_paths"] = [
            unsupported_or_timeout_path(**item) for item in unsupported_or_timeout_paths
        ]
    return payload


def unsupported_or_timeout_path(
    *,
    path: str,
    status: str,
    reason: str | None = None,
    exception_type: str | None = None,
) -> dict[str, str | None]:
    return {
        "path": path,
        "status": status,
        "reason": reason,
        "exception_type": exception_type,
    }
