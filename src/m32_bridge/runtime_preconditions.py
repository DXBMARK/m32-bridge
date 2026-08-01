"""Central, probe-free console configuration preconditions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from m32_bridge.config.runtime import (
    ConfigResolution,
    default_user_config_path,
    resolve_runtime_config,
    validate_runtime_config,
)

ConsolePreconditionState = Literal["ready", "setup_required", "config_invalid"]


@dataclass(frozen=True)
class ConsolePrecondition:
    state: ConsolePreconditionState
    configured: bool
    error_code: str | None
    required_action: str | None
    configured_host: str | None = None
    configured_port: int | None = None
    config_path: str | None = None
    resolution: ConfigResolution | None = None
    attempted_path: str = "not_attempted"
    console_probe: str = "not_run"
    network_scan: str = "not_run"
    osc_writes_sent: int = 0

    @property
    def effective_host(self) -> str | None:
        return self.configured_host

    @property
    def effective_port(self) -> int | None:
        return self.configured_port

    @classmethod
    def setup_required(cls, *, config_path: Path | str | None = None) -> "ConsolePrecondition":
        return cls(
            state="setup_required",
            configured=False,
            error_code="SETUP_REQUIRED",
            required_action="m32-bridge setup",
            config_path=str(config_path) if config_path is not None else None,
        )

    @classmethod
    def config_invalid(
        cls,
        *,
        config_path: Path | str | None = None,
        resolution: ConfigResolution | None = None,
    ) -> "ConsolePrecondition":
        return cls(
            state="config_invalid",
            configured=False,
            error_code="CONFIG_INVALID",
            required_action="m32-bridge setup",
            config_path=str(config_path) if config_path is not None else None,
            resolution=resolution,
        )

    def as_dict(self, *, include_error_code: bool = True) -> dict[str, Any]:
        payload = {
            "precondition_state": self.state,
            "console_configured": self.configured,
            "configured_host": self.configured_host,
            "configured_port": self.configured_port,
            "effective_host": self.effective_host,
            "effective_port": self.effective_port,
            "config_path": self.config_path,
            "required_action": self.required_action,
            "attempted_path": self.attempted_path,
            "console_probe": self.console_probe,
            "network_scan": self.network_scan,
            "osc_writes_sent": self.osc_writes_sent,
        }
        if include_error_code:
            payload["error_code"] = self.error_code
        return payload


def evaluate_console_precondition(
    *,
    environ: Mapping[str, str] | None = None,
    user_config_path: Path | None = None,
) -> ConsolePrecondition:
    """Resolve readiness without probing, scanning, or sending OSC packets."""

    environment = dict(os.environ if environ is None else environ)
    config_path = user_config_path or default_user_config_path()
    resolution = resolve_runtime_config(
        cli_args={},
        environ=environment,
        user_config_path=config_path,
        allow_project_local=False,
    )

    resolved_path = resolution.config_path or (config_path if resolution.user_config_present else None)
    if resolution.error_code and resolution.error_code != "NO_CONSOLE_HOST":
        return ConsolePrecondition.config_invalid(config_path=resolved_path, resolution=resolution)
    if not resolution.effective_host:
        return ConsolePrecondition.setup_required(config_path=resolved_path)
    effective_validation = validate_runtime_config(
        {
            "host": resolution.effective_host,
            "port": resolution.effective_port,
            "intended_target_type": resolution.effective_intended_target_type,
        }
    )
    if not effective_validation.ok:
        return ConsolePrecondition.config_invalid(config_path=resolved_path, resolution=resolution)
    return ConsolePrecondition(
        state="ready",
        configured=True,
        error_code=None,
        required_action=None,
        configured_host=resolution.effective_host,
        configured_port=resolution.effective_port,
        config_path=str(resolved_path) if resolved_path is not None else None,
        resolution=resolution,
    )
