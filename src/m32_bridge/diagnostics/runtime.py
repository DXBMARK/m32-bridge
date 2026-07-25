"""Read-only runtime diagnostics for host-launched subprocesses."""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import yaml

from m32_bridge.osc.codec import pack_message, unpack_message

DEFAULT_CONFIG_PATH = "config.example.yaml"
DEFAULT_TIMEOUT_SECONDS = 0.5


def runtime_diagnostics(
    *,
    host: str | None = None,
    port: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    target = _runtime_target(env, host=host, port=port)
    probe = _probe_info(target["host"], target["port"], timeout=timeout)
    status = "ok" if probe["udp_info_probe_result"] == "CONNECTED" else "not_connected"
    result: dict[str, Any] = {
        "control": "doctor-runtime",
        "status": status,
        "error_code": None if status == "ok" else "NOT_CONNECTED",
        "connection_lifecycle": "connected" if status == "ok" else "not_connected",
        "structured": True,
        "process_pid": os.getpid(),
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "configured_host": target["host"],
        "configured_port": target["port"],
        "m32_config_present": "M32_CONFIG" in env,
        "m32_config": _m32_config_presence(env),
        "env_overrides_visible": any(name in env for name in ("M32_CONSOLE_HOST", "M32_CONSOLE_PORT")),
        "visible_env_overrides": [name for name in ("M32_CONSOLE_HOST", "M32_CONSOLE_PORT") if name in env],
        "launched_from": _detect_launched_from(env),
        "attempted_path": "/info",
        "osc_writes_sent": 0,
        "write_operations": [],
        "hardware_verified": False,
        "proposal_created": False,
        "raw_osc_available": False,
        "arbitrary_path_available": False,
        "approval_token_supported": False,
        "console_write": False,
    }
    result.update(probe)
    return result


def console_status_not_connected_diagnostics(
    *,
    host: str,
    port: int,
    latency_ms: int,
    exception: Exception,
) -> dict[str, Any]:
    return {
        "status": "not_connected",
        "error_code": "NOT_CONNECTED",
        "connection_lifecycle": "not_connected",
        "configured_host": host,
        "configured_port": port,
        "attempted_path": "/info",
        "latency_ms": latency_ms,
        "exception_type": type(exception).__name__,
        "exception": f"{type(exception).__name__}: {exception}",
        "hardware_verified": False,
        "osc_writes_sent": 0,
        "write_operations": [],
    }


def _runtime_target(env: Mapping[str, str], *, host: str | None, port: int | None) -> dict[str, Any]:
    config = _load_runtime_config(env)
    target_config = config.get("target", {}) if isinstance(config.get("target"), dict) else {}
    configured_host = host or env.get("M32_CONSOLE_HOST") or _string_or_none(target_config.get("osc_host"))
    configured_port = port if port is not None else _int_or_none(env.get("M32_CONSOLE_PORT") or target_config.get("osc_port"))
    return {"host": configured_host, "port": configured_port}


def _probe_info(host: str | None, port: int | None, *, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    if not host or port is None:
        return {
            "udp_info_probe_result": "NOT_CONNECTED",
            "response_address": None,
            "exception_type": "ConnectionConfigMissing",
            "latency_ms": _elapsed_ms(started),
            "info_raw": None,
        }

    response_address: tuple[str, int] | None = None
    try:
        packet = pack_message("/info")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (host, port))
            response, response_address = sock.recvfrom(65535)
        message = unpack_message(response)
    except Exception as exc:
        return {
            "udp_info_probe_result": "NOT_CONNECTED",
            "response_address": list(response_address) if response_address else None,
            "exception_type": type(exc).__name__,
            "latency_ms": _elapsed_ms(started),
            "info_raw": None,
        }
    return {
        "udp_info_probe_result": "CONNECTED",
        "response_address": list(response_address) if response_address else None,
        "exception_type": None,
        "latency_ms": _elapsed_ms(started),
        "info_raw": list(message.arguments),
    }


def _m32_config_presence(env: Mapping[str, str]) -> dict[str, Any]:
    path_text = env.get("M32_CONFIG")
    if path_text is None:
        return {"present": False, "path": None, "exists": False}
    path = Path(path_text)
    return {"present": True, "path": str(path), "exists": path.exists()}


def _load_runtime_config(env: Mapping[str, str]) -> dict[str, Any]:
    config_path = Path(env.get("M32_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _detect_launched_from(env: Mapping[str, str]) -> str:
    explicit = env.get("M32_LAUNCHED_FROM")
    if explicit:
        return explicit
    if env.get("CLAUDE_DESKTOP") or env.get("CLAUDE_APP_PATH"):
        return "claude_desktop"
    if env.get("TERM_PROGRAM") or env.get("TERM") or env.get("SSH_TTY"):
        return "terminal"
    return "unknown"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
