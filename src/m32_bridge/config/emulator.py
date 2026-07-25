"""External X32 emulator target configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping


EXTERNAL_EMULATOR_MARKER = "external_emulator"
DEFAULT_EXTERNAL_EMULATOR_TIMEOUT = 1.0
PATRICK_X32_EMULATOR = "Patrick-Gilles Maillot X32 Emulator"


class ExternalEmulatorConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ExternalEmulatorTarget:
    host: str
    port: int
    timeout: float = DEFAULT_EXTERNAL_EMULATOR_TIMEOUT
    marker: str = EXTERNAL_EMULATOR_MARKER
    source: str = PATRICK_X32_EMULATOR
    known_capability_limitations: tuple[str, ...] = field(
        default_factory=lambda: (
            "/node may time out on the Patrick X32 Emulator build used for this gate",
            "/meters may time out on the Patrick X32 Emulator build used for this gate",
            "leaf reads may not include revision metadata",
        )
    )

    def __post_init__(self) -> None:
        if not self.host:
            raise ExternalEmulatorConfigError("M32_EXTERNAL_EMULATOR_HOST is required")
        if not 1 <= int(self.port) <= 65535:
            raise ExternalEmulatorConfigError("M32_EXTERNAL_EMULATOR_PORT must be between 1 and 65535")
        if self.timeout <= 0:
            raise ExternalEmulatorConfigError("external emulator timeout must be positive")

    @property
    def endpoint(self) -> tuple[str, int]:
        return self.host, self.port


def load_external_emulator_target(environ: Mapping[str, str] | None = None) -> ExternalEmulatorTarget:
    env = environ or os.environ
    host = env.get("M32_EXTERNAL_EMULATOR_HOST", "").strip()
    raw_port = env.get("M32_EXTERNAL_EMULATOR_PORT", "").strip()
    if not host:
        raise ExternalEmulatorConfigError("M32_EXTERNAL_EMULATOR_HOST is required")
    if not raw_port:
        raise ExternalEmulatorConfigError("M32_EXTERNAL_EMULATOR_PORT is required")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ExternalEmulatorConfigError("M32_EXTERNAL_EMULATOR_PORT must be an integer") from exc
    return ExternalEmulatorTarget(host=host, port=port)

