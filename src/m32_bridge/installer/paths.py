from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .platforms import InstallationTarget


@dataclass(frozen=True)
class InstallLocation:
    app_path: Path
    launcher_path: Path
    path_visibility: str = "unknown"
    requires_admin: bool = False


def default_install_location(
    target: InstallationTarget,
    *,
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
) -> InstallLocation:
    if target.os_family == "windows":
        base = Path(local_app_data) if local_app_data is not None else Path.home() / "AppData" / "Local"
        return InstallLocation(
            app_path=base / "M32Bridge" / "app",
            launcher_path=base / "M32Bridge" / "bin" / "m32-bridge.cmd",
            path_visibility="requires_new_terminal_or_path_update",
            requires_admin=False,
        )

    root = Path(home) if home is not None else Path.home()
    return InstallLocation(
        app_path=root / ".m32-bridge" / "app",
        launcher_path=root / ".local" / "bin" / "m32-bridge",
        path_visibility="requires_new_terminal_or_path_update",
        requires_admin=False,
    )

