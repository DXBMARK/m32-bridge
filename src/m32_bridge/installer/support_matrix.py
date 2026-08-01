from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallerTarget:
    target_id: str
    os_family: str
    architecture: str
    python_tag: str
    python_version: str
    uv_platform: str
    wheel_platform_family: str
    minimum_compatibility: str
    minimum_manylinux: tuple[int, int] | None = None
    release_supported: bool = True
    blocked_dependency: str | None = None
    support_blocker: str = ""

    def marker_environment(self) -> dict[str, str]:
        sys_platform = {"linux": "linux", "wsl": "linux", "raspberry_pi_os": "linux", "macos": "darwin", "windows": "win32"}[self.os_family]
        platform_system = {"linux": "Linux", "wsl": "Linux", "raspberry_pi_os": "Linux", "macos": "Darwin", "windows": "Windows"}[self.os_family]
        return {
            "implementation_name": "cpython",
            "implementation_version": "3.13.0",
            "os_name": "nt" if self.os_family == "windows" else "posix",
            "platform_machine": self.architecture,
            "platform_python_implementation": "CPython",
            "platform_release": "",
            "platform_system": platform_system,
            "platform_version": "",
            "python_full_version": "3.13.0",
            "python_version": self.python_version,
            "sys_platform": sys_platform,
            "extra": "",
        }


INSTALLER_TARGETS = (
    InstallerTarget(
        target_id="linux_x86_64_cp313",
        os_family="linux",
        architecture="x86_64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="x86_64-manylinux_2_17",
        wheel_platform_family="linux",
        minimum_compatibility="glibc >= 2.17 (Ubuntu 20.04 compatible)",
        minimum_manylinux=(2, 17),
    ),
    InstallerTarget(
        target_id="wsl_x86_64_cp313",
        os_family="wsl",
        architecture="x86_64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="x86_64-manylinux_2_17",
        wheel_platform_family="linux",
        minimum_compatibility="Linux manylinux glibc >= 2.17 policy inside WSL",
        minimum_manylinux=(2, 17),
    ),
    InstallerTarget(
        target_id="macos_arm64_cp313",
        os_family="macos",
        architecture="arm64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="aarch64-apple-darwin",
        wheel_platform_family="macos",
        minimum_compatibility="macOS arm64 wheel or universal2 wheel",
    ),
    InstallerTarget(
        target_id="macos_x86_64_cp313",
        os_family="macos",
        architecture="x86_64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="x86_64-apple-darwin",
        wheel_platform_family="macos",
        minimum_compatibility="macOS x86_64 wheel or universal2 wheel",
        release_supported=False,
        blocked_dependency="cryptography==49.0.0",
        support_blocker="The locked cryptography version has no macOS x86_64 wheel on the package index.",
    ),
    InstallerTarget(
        target_id="windows_amd64_cp313",
        os_family="windows",
        architecture="amd64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="x86_64-pc-windows-msvc",
        wheel_platform_family="windows",
        minimum_compatibility="Windows amd64 wheel",
    ),
    InstallerTarget(
        target_id="raspberry_pi_os_arm64_cp313",
        os_family="raspberry_pi_os",
        architecture="aarch64",
        python_tag="cp313",
        python_version="3.13",
        uv_platform="aarch64-manylinux_2_17",
        wheel_platform_family="linux",
        minimum_compatibility="Raspberry Pi OS 64-bit with glibc >= 2.17",
        minimum_manylinux=(2, 17),
    ),
)


def target_by_id(target_id: str) -> InstallerTarget:
    return next(target for target in INSTALLER_TARGETS if target.target_id == target_id)


def release_supported_targets() -> tuple[InstallerTarget, ...]:
    return tuple(target for target in INSTALLER_TARGETS if target.release_supported)


def target_for_installer_platform(platform: str, architecture: str | None) -> InstallerTarget | None:
    normalized_platform = "windows" if platform in {"windows", "windows_cmd", "windows_powershell"} else platform
    normalized_architecture = _normalize_architecture(architecture, windows=normalized_platform == "windows")
    return next(
        (
            target
            for target in INSTALLER_TARGETS
            if target.os_family == normalized_platform and target.architecture == normalized_architecture
        ),
        None,
    )


def _normalize_architecture(architecture: str | None, *, windows: bool) -> str:
    normalized = (architecture or "").strip().lower()
    x86_64 = "amd64" if windows else "x86_64"
    arm64 = "arm64" if normalized == "arm64" and not windows else "aarch64"
    return {
        "amd64": x86_64,
        "x64": x86_64,
        "x86_64": x86_64,
        "arm64": arm64,
        "aarch64": "aarch64",
    }.get(normalized, normalized)
