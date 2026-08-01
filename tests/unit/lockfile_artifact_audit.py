from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from packaging.markers import Marker
from packaging.utils import parse_wheel_filename

from m32_bridge.installer.support_matrix import InstallerTarget


@dataclass(frozen=True)
class LockArtifactVerdict:
    target_id: str
    runtime_packages: tuple[str, ...]
    native_packages: tuple[str, ...]
    missing_wheel_packages: tuple[str, ...]
    error_code: str | None

    @property
    def ok(self) -> bool:
        return not self.missing_wheel_packages


def load_lock(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def audit_lock_artifacts(lock: dict[str, object], target: InstallerTarget) -> LockArtifactVerdict:
    packages = {package["name"]: package for package in lock["package"]}
    runtime_names = _runtime_package_names(packages, target)
    native: list[str] = []
    missing: list[str] = []

    for name in sorted(runtime_names):
        package = packages[name]
        wheels = [_wheel_name(wheel["url"]) for wheel in package.get("wheels", [])]
        if any(_is_universal_wheel(wheel) for wheel in wheels):
            continue
        native.append(name)
        if not any(_wheel_supports_target(wheel, target) for wheel in wheels):
            missing.append(name)

    return LockArtifactVerdict(
        target_id=target.target_id,
        runtime_packages=tuple(sorted(runtime_names)),
        native_packages=tuple(native),
        missing_wheel_packages=tuple(missing),
        error_code="LOCKFILE_ARTIFACT_COVERAGE_INCOMPLETE" if missing else None,
    )


def _runtime_package_names(packages: dict[str, dict[str, object]], target: InstallerTarget) -> set[str]:
    root = packages["m32-mcp-bridge"]
    pending = list(root.get("dependencies", []))
    selected: set[str] = set()
    selected_extras: dict[str, set[str]] = {}
    environment = target.marker_environment()

    while pending:
        dependency = pending.pop()
        if not _marker_applies(dependency.get("marker"), environment):
            continue
        name = dependency["name"]
        package = packages[name]
        if name not in selected:
            selected.add(name)
            pending.extend(package.get("dependencies", []))
        requested_extras = set(dependency.get("extra", []))
        new_extras = requested_extras - selected_extras.setdefault(name, set())
        for extra in new_extras:
            pending.extend(package.get("optional-dependencies", {}).get(extra, []))
        selected_extras[name].update(new_extras)
    return selected


def _marker_applies(marker: str | None, environment: dict[str, str]) -> bool:
    return marker is None or Marker(marker).evaluate(environment=environment)


def _wheel_name(url: str) -> str:
    return Path(unquote(urlparse(url).path)).name.lower()


def _wheel_tags(filename: str):
    try:
        return parse_wheel_filename(filename)[3]
    except ValueError:
        return ()


def _is_universal_wheel(filename: str) -> bool:
    return any(tag.platform == "any" and tag.abi == "none" and tag.interpreter.startswith("py3") for tag in _wheel_tags(filename))


def _wheel_supports_target(filename: str, target: InstallerTarget) -> bool:
    return any(_python_abi_matches(tag.interpreter, tag.abi) and _platform_matches(tag.platform, target) for tag in _wheel_tags(filename))


def _python_abi_matches(interpreter: str, abi: str) -> bool:
    if interpreter == "cp313" and abi in {"cp313", "abi3", "none"}:
        return True
    if abi != "abi3" or not interpreter.startswith("cp"):
        return False
    try:
        return int(interpreter[2:]) <= 313
    except ValueError:
        return False


def _platform_matches(platform: str, target: InstallerTarget) -> bool:
    if target.wheel_platform_family == "windows":
        return platform == "win_amd64"
    if target.wheel_platform_family == "macos":
        architectures = {target.architecture, "universal2"}
        return platform.startswith("macosx_") and any(platform.endswith(f"_{arch}") for arch in architectures)
    return _manylinux_matches(platform, target.architecture, target.minimum_manylinux)


def _manylinux_matches(platform: str, architecture: str, maximum: tuple[int, int] | None) -> bool:
    if not platform.endswith(f"_{architecture}") or maximum is None:
        return False
    aliases = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}
    prefix = platform[: -len(f"_{architecture}")]
    if prefix in aliases:
        return aliases[prefix] <= maximum
    parts = prefix.split("_")
    if len(parts) != 3 or parts[0] != "manylinux":
        return False
    try:
        return (int(parts[1]), int(parts[2])) <= maximum
    except ValueError:
        return False
