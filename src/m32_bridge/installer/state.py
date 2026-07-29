from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .paths import InstallLocation


InstallStatus = Literal[
    "fresh_install",
    "existing_install",
    "repair",
    "update",
    "already_current",
    "partial_failure",
    "failed",
]


@dataclass(frozen=True)
class InstallationState:
    status: InstallStatus
    previous_version: str | None = None
    target_version: str | None = None
    actions_planned: tuple[str, ...] = ()
    actions_completed: tuple[str, ...] = ()
    rollback_or_recovery: str | None = None
    osc_writes_sent: int = 0
    hardware_verified: bool = False
    production_live_ready: bool = False


def determine_install_state(
    location: InstallLocation,
    *,
    app_exists: bool | None = None,
    launcher_exists: bool | None = None,
    current_version: str | None = None,
    target_version: str | None = None,
    partial_failure_marker: bool = False,
) -> InstallationState:
    app_present = _exists(location.app_path, app_exists)
    launcher_present = _exists(location.launcher_path, launcher_exists)
    if partial_failure_marker:
        return InstallationState(
            status="partial_failure",
            previous_version=current_version,
            target_version=target_version,
            rollback_or_recovery="Run repair or remove incomplete user-local app and launcher files.",
        )
    if not app_present and not launcher_present:
        return InstallationState(status="fresh_install", target_version=target_version, actions_planned=("create_app", "create_launcher"))
    if app_present and not launcher_present:
        return InstallationState(status="repair", previous_version=current_version, target_version=target_version, actions_planned=("restore_launcher",))
    if target_version and current_version and current_version != target_version:
        return InstallationState(status="update", previous_version=current_version, target_version=target_version, actions_planned=("update_app",))
    if app_present and launcher_present:
        return InstallationState(status="already_current", previous_version=current_version, target_version=target_version)
    return InstallationState(status="existing_install", previous_version=current_version, target_version=target_version)


def _exists(path: Path, override: bool | None) -> bool:
    return path.exists() if override is None else override

