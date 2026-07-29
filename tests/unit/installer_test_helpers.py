from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IsolatedInstallHome:
    root: Path

    @property
    def posix_home(self) -> Path:
        return self.root / "home" / "operator"

    @property
    def windows_local_app_data(self) -> Path:
        return self.root / "win" / "LocalAppData"

    @property
    def posix_app_path(self) -> Path:
        return self.posix_home / ".m32-bridge" / "app"

    @property
    def posix_launcher_path(self) -> Path:
        return self.posix_home / ".local" / "bin" / "m32-bridge"

    @property
    def windows_app_path(self) -> Path:
        return self.windows_local_app_data / "M32Bridge" / "app"

    @property
    def windows_launcher_path(self) -> Path:
        return self.windows_local_app_data / "M32Bridge" / "bin" / "m32-bridge.cmd"


def isolated_install_home(tmp_path: Path) -> IsolatedInstallHome:
    return IsolatedInstallHome(root=tmp_path)


def dry_run_environment(tmp_path: Path) -> dict[str, str]:
    home = isolated_install_home(tmp_path)
    return {
        "HOME": str(home.posix_home),
        "LOCALAPPDATA": str(home.windows_local_app_data),
        "M32_INSTALL_DRY_RUN": "1",
    }

