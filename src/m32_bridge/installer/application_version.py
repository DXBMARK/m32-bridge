"""Resolve application versions from declarative project metadata.

The installed or staged ``pyproject.toml`` is the application-version truth.
Distribution metadata is retained only as a compatibility signal and must never
override a valid project version.
"""

from __future__ import annotations

import os
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
from typing import Mapping


_PROJECT_VERSION_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[A-Za-z][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[A-Za-z][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)


@dataclass(frozen=True)
class ApplicationVersionResolution:
    version: str
    source: str
    status: str
    pyproject_path: str | None
    distribution_version: str | None
    mismatch: bool
    error: str | None = None


def validate_project_version(value: object) -> str:
    """Validate the project's strict SemVer-compatible PEP 440 version form."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("PROJECT_VERSION_INVALID: [project].version must be a non-empty trimmed string.")
    if len(value) > 128 or any(
        character == "\x1b" or unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    ):
        raise ValueError("PROJECT_VERSION_INVALID: [project].version contains unsafe characters.")
    if _PROJECT_VERSION_RE.fullmatch(value) is None:
        raise ValueError("PROJECT_VERSION_INVALID: [project].version must be strict SemVer-compatible metadata.")
    return value


def read_project_version(pyproject_path: Path | str) -> str:
    """Read one validated ``[project].version`` using only the standard library."""

    path = Path(pyproject_path)
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"PROJECT_METADATA_INVALID: {path}") from exc
    project = document.get("project")
    if not isinstance(project, dict) or "version" not in project:
        raise ValueError("PROJECT_VERSION_MISSING: pyproject.toml has no [project].version.")
    return validate_project_version(project["version"])


def resolve_staged_application_version(staged_source_root: Path | str) -> ApplicationVersionResolution:
    return _resolve_required_project_version(Path(staged_source_root) / "pyproject.toml", "staged_pyproject")


def resolve_local_checkout_version(source_root: Path | str) -> ApplicationVersionResolution:
    return _resolve_required_project_version(Path(source_root) / "pyproject.toml", "local_checkout_pyproject")


def resolve_installed_application_version(
    app_path: Path | str | None,
    distribution_name: str = "m32-mcp-bridge",
    *,
    environ: Mapping[str, str] | None = None,
    source_root: Path | str | None = None,
    local_development: bool | None = None,
) -> ApplicationVersionResolution:
    """Resolve installed truth without requiring installed distribution metadata."""

    env = dict(os.environ if environ is None else environ)
    candidates: list[Path] = []
    configured_app = env.get("M32_BRIDGE_APP_DIR")
    if configured_app:
        candidates.append(Path(configured_app) / "pyproject.toml")
    if app_path:
        explicit = Path(app_path) / "pyproject.toml"
        if explicit not in candidates:
            candidates.append(explicit)

    dist_version = _read_distribution_version(distribution_name)
    for candidate in candidates:
        if not candidate.exists():
            continue
        resolved = _resolve_required_project_version(candidate, "installed_pyproject")
        if resolved.status != "resolved":
            return ApplicationVersionResolution(
                version=resolved.version,
                source=resolved.source,
                status=resolved.status,
                pyproject_path=resolved.pyproject_path,
                distribution_version=dist_version,
                mismatch=False,
                error=resolved.error,
            )
        mismatch = bool(dist_version and dist_version != resolved.version)
        return ApplicationVersionResolution(
            version=resolved.version,
            source="installed_pyproject",
            status="version_source_mismatch" if mismatch else "resolved",
            pyproject_path=str(candidate.resolve(strict=False)),
            distribution_version=dist_version,
            mismatch=mismatch,
        )

    if local_development is None:
        local_development = env.get("M32_BRIDGE_INSTALLED_RUNTIME") != "1"
    if local_development:
        checkout = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[3]
        pyproject = checkout / "pyproject.toml"
        if pyproject.is_file():
            return _resolve_required_project_version(pyproject, "local_checkout_pyproject")

    return ApplicationVersionResolution(
        version="unknown",
        source="unknown",
        status="version_unavailable",
        pyproject_path=None,
        distribution_version=dist_version,
        mismatch=False,
    )


def application_version(
    app_path: Path | str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Compatibility presentation helper backed by the central resolver."""

    return resolve_installed_application_version(app_path, environ=environ).version


def _resolve_required_project_version(path: Path, source: str) -> ApplicationVersionResolution:
    try:
        version = read_project_version(path)
    except FileNotFoundError:
        return ApplicationVersionResolution(
            version="unknown",
            source=source,
            status="project_metadata_missing",
            pyproject_path=str(path.resolve(strict=False)),
            distribution_version=None,
            mismatch=False,
            error="PROJECT_METADATA_MISSING",
        )
    except ValueError as exc:
        return ApplicationVersionResolution(
            version="unknown",
            source=source,
            status="project_metadata_invalid",
            pyproject_path=str(path.resolve(strict=False)),
            distribution_version=None,
            mismatch=False,
            error=str(exc).split(":", 1)[0],
        )
    return ApplicationVersionResolution(
        version=version,
        source=source,
        status="resolved",
        pyproject_path=str(path.resolve(strict=False)),
        distribution_version=None,
        mismatch=False,
    )


def _read_distribution_version(name: str) -> str | None:
    try:
        value = distribution_version(name)
    except (PackageNotFoundError, ValueError):
        return None
    try:
        return validate_project_version(value)
    except ValueError:
        return None
