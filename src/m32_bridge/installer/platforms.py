from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OsFamily = Literal["macos", "linux", "wsl", "windows", "raspberry_pi_os", "unsupported"]
ShellFamily = Literal["posix", "powershell", "cmd_launcher"]


@dataclass(frozen=True)
class InstallationTarget:
    os_family: OsFamily
    shell_family: ShellFamily
    architecture: str | None = None
    is_interactive: bool = False
    supports_user_local_install: bool = True
    recommendation: str = ""
    detected_shell: str | None = None
    wsl_distribution: str | None = None

    @property
    def output_platform(self) -> str:
        if self.os_family == "windows":
            return "windows_cmd" if self.shell_family == "cmd_launcher" else "windows_powershell"
        return self.os_family


def installation_target(
    *,
    os_family: OsFamily,
    shell_family: ShellFamily | None = None,
    architecture: str | None = None,
    is_interactive: bool = False,
    detected_shell: str | None = None,
    wsl_distribution: str | None = None,
) -> InstallationTarget:
    resolved_shell = shell_family or ("powershell" if os_family == "windows" else "posix")
    return InstallationTarget(
        os_family=os_family,
        shell_family=resolved_shell,
        architecture=architecture,
        is_interactive=is_interactive,
        recommendation=_recommendation(os_family),
        detected_shell=detected_shell,
        wsl_distribution=wsl_distribution,
    )


def _recommendation(os_family: OsFamily) -> str:
    return {
        "macos": "Use the POSIX user-local installer and reopen the terminal if PATH changes are needed.",
        "linux": "Use the POSIX user-local installer; do not use system paths by default.",
        "wsl": "Use the POSIX user-local installer inside WSL; keep WSL distinct from native Windows.",
        "windows": "Use the PowerShell user-local installer and the generated CMD-compatible launcher.",
        "raspberry_pi_os": "Use the POSIX user-local installer; service/image packaging is future-only.",
        "unsupported": "Unsupported OS; use manual guidance and do not report partial success.",
    }[os_family]

