"""Truthful, user-local installation metadata for the installed Runtime Console."""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .application_version import (
    resolve_installed_application_version,
    resolve_staged_application_version,
    validate_project_version,
)

SCHEMA_VERSION = "1"
PRODUCT_NAME = "X32-Bridge MCP"
OFFICIAL_REPOSITORY_URL = "https://github.com/DXBMARK/m32-bridge"
METADATA_FILENAME = "install-metadata.json"
_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "product",
        "application_version",
        "application_version_source",
        "installed_at",
        "install_source",
        "selection",
        "release_channel",
        "release_tag",
        "source_ref",
        "source_commit",
        "repository_url",
        "source_archive_url",
        "source_archive_sha256",
        "installer_asset_url",
        "installer_asset_sha256",
        "manifest_status",
        "manifest_schema_version",
        "raw_installer_url",
        "source_url_status",
        "platform",
        "architecture",
        "app_path",
        "launcher_path",
    }
)
_INSTALL_SOURCES = frozenset(
    {
        "local_checkout",
        "github_release_asset",
        "github_commit_archive",
        "github_main",
        "custom",
        # Read compatibility for metadata created before the unified resolver.
        "github_release_or_archive",
        "github_raw",
    }
)
_PLATFORMS = frozenset({"macos", "linux", "wsl", "raspberry_pi_os", "windows_powershell", "windows_cmd"})
_MAX_TEXT = 256
_COMMIT_RE = re.compile(r"[0-9A-Fa-f]{7,40}\Z")
_FULL_COMMIT_RE = re.compile(r"[0-9A-Fa-f]{40}\Z")
_RELEASE_TAG_RE = re.compile(
    r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z"
)


def install_metadata_path(
    *,
    surface: str | None = None,
    app_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the metadata path without consulting project checkout state."""

    if app_path is not None:
        app = Path(app_path).expanduser()
        return app.parent / METADATA_FILENAME
    env = dict(os.environ if environ is None else environ)
    windows = surface == "windows" or (surface is None and os.name == "nt")
    if windows:
        base = Path(env.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "M32Bridge"
    else:
        base = Path(env.get("HOME") or Path.home()) / ".m32-bridge"
    return base / METADATA_FILENAME


def build_install_metadata(
    surface: str,
    result: Mapping[str, Any],
    *,
    installed_at: str | None = None,
) -> dict[str, Any]:
    """Build the small allow-listed document persisted after a successful apply."""

    app_path = Path(str(result.get("app_path") or "")).expanduser()
    launcher_path = Path(str(result.get("launcher_path") or "")).expanduser()
    application_version, application_version_source = _result_application_version(result, app_path)
    source_url = str(result.get("source_archive_url") or result.get("source_url") or "").strip()
    source_ref = str(result["source_ref"]) if result.get("source_ref") else "not_available"
    release_tag_input = result.get("release_tag")
    source_commit_input = result.get("source_commit")
    release_tag = validate_release_tag(release_tag_input) if release_tag_input not in {None, ""} else None
    source_commit = normalize_source_commit(source_commit_input) if source_commit_input not in {None, ""} else None
    if release_tag and version_from_release_tag(release_tag) != application_version:
        raise ValueError("RELEASE_VERSION_MISMATCH: release_tag must match application_version.")
    if release_tag:
        if source_commit is None:
            raise ValueError("RELEASE_COMMIT_MISMATCH: versioned Release metadata requires source_commit.")
        normalized_ref = str(source_ref).lower()
        if normalized_ref != source_commit:
            raise ValueError("RELEASE_COMMIT_MISMATCH: source_ref must equal source_commit.")
        source_ref = source_commit
    install_source = str(result.get("install_source") or "local_checkout")
    legacy_source = install_source in {"github_raw", "github_release_or_archive"}
    if legacy_source and release_tag:
        install_source = "github_release_asset" if release_tag else "github_commit_archive"
    if release_tag and install_source != "github_release_asset":
        raise ValueError("RELEASE_MANIFEST_INVALID: release_tag requires github_release_asset.")
    if install_source in {"github_commit_archive", "github_main"}:
        if source_commit is None:
            source_commit = normalize_source_commit(source_ref)
        source_ref = source_commit
    if install_source == "local_checkout" and release_tag:
        raise ValueError("RELEASE_MANIFEST_INVALID: local checkout cannot claim a Release tag.")

    descriptor = official_source_descriptor(source_url) if source_url else None
    legacy_official = bool(
        legacy_source
        and descriptor
        and descriptor.get("kind") in {"archive", "raw"}
        and descriptor.get("ref") == source_ref
    )
    official_source = install_source in {"github_release_asset", "github_commit_archive", "github_main"} or legacy_official
    if source_url and (descriptor is None or (legacy_source and not legacy_official)):
        install_source = "custom"
        official_source = False
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT_NAME,
        "application_version": application_version,
        "application_version_source": application_version_source,
        "installed_at": installed_at or datetime.now(timezone.utc).isoformat(),
        "install_source": install_source,
        "selection": str(result.get("selection") or result.get("requested_selection") or ("local" if install_source == "local_checkout" else "not_available")),
        "source_ref": source_ref,
        "platform": str(result.get("platform") or surface),
        "architecture": str(result.get("architecture") or "unknown"),
        "app_path": str(app_path),
        "launcher_path": str(launcher_path),
    }
    if official_source:
        payload["repository_url"] = OFFICIAL_REPOSITORY_URL
        if source_commit:
            payload["source_commit"] = source_commit
        if release_tag:
            payload["release_tag"] = release_tag
            payload["release_channel"] = str(result.get("release_channel") or ("prerelease" if "-" in release_tag[1:] else "stable"))
            payload["manifest_status"] = str(result.get("manifest_status") or "validated")
            payload["manifest_schema_version"] = str(result.get("manifest_schema_version") or SCHEMA_VERSION)
            archive_name = "m32-bridge-source.zip" if surface == "windows" else "m32-bridge-source.tar.gz"
            installer_name = "install.ps1" if surface == "windows" else "install.sh"
            expected_archive = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{release_tag}/{archive_name}"
            expected_installer = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{release_tag}/{installer_name}"
            archive_url = str(result.get("source_archive_url") or source_url)
            installer_url = str(result.get("installer_asset_url") or "")
            if archive_url != expected_archive or installer_url != expected_installer:
                raise ValueError("RELEASE_SOURCE_URL_MISMATCH: persisted Release asset URLs must match tag and platform.")
            payload["source_archive_url"] = archive_url
            payload["installer_asset_url"] = installer_url
            payload["source_archive_sha256"] = _checksum(result.get("source_archive_sha256"), "source archive")
            payload["installer_asset_sha256"] = _checksum(result.get("installer_asset_sha256"), "installer asset")
        elif install_source in {"github_commit_archive", "github_main"}:
            official_urls = build_official_release_urls(surface, source_commit)
            if source_url and source_url != official_urls["source_archive_url"]:
                raise ValueError("RELEASE_SOURCE_URL_MISMATCH: commit/main archive must be pinned to source_commit.")
            payload["source_archive_url"] = official_urls["source_archive_url"]
            payload["raw_installer_url"] = official_urls["raw_installer_url"]
        else:
            payload.update(_official_urls(surface, source_ref=source_ref))
    elif install_source == "custom":
        payload["source_url_status"] = "not_persisted"
    return payload


def write_install_metadata(
    metadata: Mapping[str, Any],
    *,
    app_path: Path | str,
    path: Path | None = None,
) -> Path:
    """Atomically replace metadata inside the application install root."""

    app = Path(app_path).expanduser()
    if not app.is_absolute():
        raise ValueError("Application path must be absolute before metadata is written.")
    install_root = app.parent.resolve()
    target = path or install_root / METADATA_FILENAME
    target = Path(target).expanduser()
    if not target.is_absolute() or target.parent.resolve() != install_root:
        raise ValueError("Install metadata must remain inside the user-local install root.")
    document = dict(metadata)
    _validate_document(document, expected_app_path=app)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    fd: int | None = None
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
        if os.name != "nt":
            target.chmod(0o600)
        return target
    finally:
        if fd is not None:
            os.close(fd)
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def read_install_metadata(path: Path) -> dict[str, Any]:
    """Read metadata fail-safe; absence or malformed content never escapes."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"status": "metadata_missing", "path": str(path), "data": {}}
    except OSError:
        return {"status": "metadata_invalid", "path": str(path), "data": {}}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "metadata_invalid", "path": str(path), "data": {}}
    if not isinstance(loaded, dict):
        return {"status": "metadata_invalid", "path": str(path), "data": {}}
    try:
        _validate_document(loaded)
    except ValueError:
        return {"status": "metadata_invalid", "path": str(path), "data": {}}
    return {"status": "metadata_valid", "path": str(path), "data": loaded}


def assert_same_tag_immutable(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> None:
    existing_tag = existing.get("release_tag")
    incoming_tag = incoming.get("release_tag")
    if existing_tag and incoming_tag and existing_tag == incoming_tag:
        old_commit = existing.get("source_commit")
        new_commit = incoming.get("source_commit")
        if old_commit and new_commit and normalize_source_commit(old_commit) != normalize_source_commit(new_commit):
            raise ValueError("RELEASE_TAG_COMMIT_CONFLICT: existing tag resolves to another source commit.")


def is_official_source_url(url: str) -> bool:
    return official_source_descriptor(url) is not None


def is_commit_ref(value: Any) -> bool:
    return isinstance(value, str) and _COMMIT_RE.fullmatch(value) is not None


def validate_release_tag(value: Any) -> str:
    """Return one strict, terminal-safe SemVer release tag."""

    if not isinstance(value, str) or not _printable(value, max_length=128):
        raise ValueError("RELEASE_TAG_INVALID: release_tag must be printable and at most 128 characters.")
    if any(character in value for character in ("/", "\\", "%", "?", "#")):
        raise ValueError("RELEASE_TAG_INVALID: release_tag contains a forbidden delimiter.")
    if _RELEASE_TAG_RE.fullmatch(value) is None:
        raise ValueError("RELEASE_TAG_INVALID: release_tag must be strict v-prefixed SemVer.")
    return value


def normalize_release_tag(value: Any) -> str:
    return validate_release_tag(value)


def version_from_release_tag(value: Any) -> str:
    return validate_release_tag(value)[1:]


def normalize_source_commit(value: Any) -> str:
    if not isinstance(value, str) or not _printable(value, max_length=40) or _FULL_COMMIT_RE.fullmatch(value) is None:
        raise ValueError("RELEASE_SOURCE_COMMIT_INVALID: source_commit must be a full 40-character hexadecimal SHA.")
    return value.lower()


def build_official_release_urls(platform: str, source_commit: Any) -> dict[str, str]:
    """Derive every official immutable release URL from one full commit SHA."""

    commit = normalize_source_commit(source_commit)
    windows = platform == "windows" or str(platform).startswith("windows")
    archive_kind = "zip" if windows else "tar.gz"
    installer_name = "install.ps1" if windows else "install.sh"
    return {
        "repository_url": OFFICIAL_REPOSITORY_URL,
        "source_archive_url": f"{OFFICIAL_REPOSITORY_URL}/archive/{commit}.{archive_kind}",
        "raw_installer_url": f"https://raw.githubusercontent.com/DXBMARK/m32-bridge/{commit}/scripts/{installer_name}",
        "allowed_redirect_url": f"https://codeload.github.com/DXBMARK/m32-bridge/{archive_kind}/{commit}",
    }


def official_source_descriptor(url: str) -> dict[str, str | None] | None:
    """Return a structural exact match for one supported initial source URL."""

    canonical = canonical_source_url(url)
    if canonical is None or canonical != url:
        return None
    parsed = urlsplit(canonical)
    host = parsed.hostname or ""
    path = parsed.path
    if host == "github.com":
        if path == "/" or path == "/DXBMARK/m32-bridge":
            return {"kind": "root" if path == "/" else "repository", "ref": None, "platform": None}
        match = re.fullmatch(r"/DXBMARK/m32-bridge/archive/([0-9A-Fa-f]{7,40})\.(tar\.gz|zip)", path)
        if match:
            return {"kind": "archive", "ref": match.group(1), "platform": "posix" if match.group(2) == "tar.gz" else "windows"}
        match = re.fullmatch(r"/DXBMARK/m32-bridge/archive/refs/heads/main\.(tar\.gz|zip)", path)
        if match:
            return {"kind": "archive", "ref": "main", "platform": "posix" if match.group(1) == "tar.gz" else "windows"}
        match = re.fullmatch(
            r"/DXBMARK/m32-bridge/releases/download/(v[^/]+)/(m32-bridge-source\.tar\.gz|m32-bridge-source\.zip|install\.sh|install\.ps1|m32-bridge-release\.json|SHA256SUMS)",
            path,
        )
        if match:
            try:
                tag = validate_release_tag(match.group(1))
            except ValueError:
                return None
            platform = "windows" if match.group(2) in {"m32-bridge-source.zip", "install.ps1"} else "posix"
            return {"kind": "release_asset", "ref": tag, "platform": platform}
        return None
    if host == "raw.githubusercontent.com":
        match = re.fullmatch(r"/DXBMARK/m32-bridge/(main|[0-9A-Fa-f]{7,40})/scripts/(install\.sh|install\.ps1)", path)
        if match:
            return {"kind": "raw", "ref": match.group(1), "platform": "posix" if match.group(2) == "install.sh" else "windows"}
    return None


def canonical_source_url(url: str) -> str | None:
    """Canonicalize a candidate without broad repository-prefix trust."""

    if not isinstance(url, str) or not _printable(url, max_length=2048):
        return None
    if "\\" in url:
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return None
    if parsed.query or parsed.fragment or port not in {None, 443}:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in {"github.com", "raw.githubusercontent.com"}:
        return None
    if "%" in parsed.path:
        return None
    if "\\" in parsed.path or any(part in {".", ".."} for part in parsed.path.split("/")):
        return None
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    if parsed.path.endswith("/") and path != "/":
        path += "/"
    if host == "github.com" and path == "/":
        path = "/"
    return urlunsplit(("https", host, path, "", ""))


def _official_urls(surface: str, *, source_ref: str) -> dict[str, str]:
    platform_key = "windows" if surface == "windows" else "posix"
    archive_suffix = "zip" if platform_key == "windows" else "tar.gz"
    installer_name = "install.ps1" if platform_key == "windows" else "install.sh"
    if is_commit_ref(source_ref):
        archive = f"https://github.com/DXBMARK/m32-bridge/archive/{source_ref}.{archive_suffix}"
    elif source_ref == "main":
        archive = f"https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.{archive_suffix}"
    else:
        raise ValueError("Official source_ref must be main or a pinned commit SHA.")
    return {
        "source_archive_url": archive,
        "raw_installer_url": f"https://raw.githubusercontent.com/DXBMARK/m32-bridge/{source_ref}/scripts/{installer_name}",
    }


def _validate_document(document: Mapping[str, Any], *, expected_app_path: Path | None = None) -> None:
    unknown = set(document) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError("Install metadata contains unsupported fields.")
    required = {
        "schema_version",
        "product",
        "application_version",
        "application_version_source",
        "installed_at",
        "install_source",
        "selection",
        "platform",
        "architecture",
        "app_path",
        "launcher_path",
    }
    if required - set(document):
        raise ValueError("Install metadata is incomplete.")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported install metadata schema version.")
    if document.get("product") != PRODUCT_NAME:
        raise ValueError("Unexpected install metadata product.")
    if document.get("install_source") not in _INSTALL_SOURCES:
        raise ValueError("Unknown install source.")
    if document.get("platform") not in _PLATFORMS:
        raise ValueError("Unsupported install platform.")
    _validate_timestamp(document.get("installed_at"))
    for key, value in document.items():
        if not isinstance(value, str):
            raise ValueError("Install metadata values must be strings.")
        lowered = key.lower()
        if any(secret in lowered for secret in ("token", "credential", "password", "secret", "api_key")):
            raise ValueError("Secrets are not permitted in install metadata.")
        limit = 128 if key in {"source_ref", "release_tag", "source_commit"} else _MAX_TEXT
        if not _printable(value, max_length=limit):
            raise ValueError("Install metadata contains invalid control characters or length.")
        if key.endswith("_url") and not is_official_source_url(value):
            raise ValueError("Only official source URLs may be persisted.")
    if document.get("install_source") in {"github_raw", "github_release_or_archive", "github_commit_archive", "github_main"}:
        source_ref = document.get("source_ref")
        modern = document.get("install_source") in {"github_commit_archive", "github_main"}
        if modern and (not isinstance(source_ref, str) or _FULL_COMMIT_RE.fullmatch(source_ref) is None):
            raise ValueError("Official source_ref must be one full immutable commit SHA.")
        if not modern and source_ref != "main" and not is_commit_ref(source_ref):
            raise ValueError("Legacy official source_ref must be main or a commit SHA.")
        for key in ("source_archive_url", "raw_installer_url"):
            descriptor = official_source_descriptor(str(document.get(key) or ""))
            if descriptor is None or descriptor.get("ref") != source_ref:
                raise ValueError("Official source URLs must match source_ref exactly.")
    release_tag = document.get("release_tag")
    source_commit = document.get("source_commit")
    if release_tag is not None:
        normalized_tag = validate_release_tag(release_tag)
        commit = normalize_source_commit(source_commit)
        if version_from_release_tag(normalized_tag) != document.get("application_version"):
            raise ValueError("RELEASE_VERSION_MISMATCH: release_tag must match application_version.")
        if document.get("source_ref") != commit:
            raise ValueError("RELEASE_COMMIT_MISMATCH: source_ref must equal source_commit.")
        if document.get("install_source") != "github_release_asset":
            raise ValueError("RELEASE_MANIFEST_INVALID: release_tag requires github_release_asset.")
        expected_channel = "prerelease" if "-" in normalized_tag[1:] else "stable"
        if document.get("release_channel") != expected_channel:
            raise ValueError("RELEASE_MANIFEST_INVALID: release channel does not match tag.")
        if document.get("manifest_status") != "validated" or document.get("manifest_schema_version") != SCHEMA_VERSION:
            raise ValueError("RELEASE_MANIFEST_INVALID: trusted Release metadata requires a validated manifest.")
        windows = document.get("platform") in {"windows_powershell", "windows_cmd"}
        archive_name = "m32-bridge-source.zip" if windows else "m32-bridge-source.tar.gz"
        installer_name = "install.ps1" if windows else "install.sh"
        expected_archive = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{normalized_tag}/{archive_name}"
        expected_installer = f"{OFFICIAL_REPOSITORY_URL}/releases/download/{normalized_tag}/{installer_name}"
        if document.get("source_archive_url") != expected_archive or document.get("installer_asset_url") != expected_installer:
            raise ValueError("RELEASE_SOURCE_URL_MISMATCH: persisted Release URLs must match release_tag.")
        _checksum(document.get("source_archive_sha256"), "source archive")
        _checksum(document.get("installer_asset_sha256"), "installer asset")
    elif source_commit is not None:
        commit = normalize_source_commit(source_commit)
        if document.get("install_source") not in {"github_commit_archive", "github_main"} or document.get("source_ref") != commit:
            raise ValueError("RELEASE_SOURCE_COMMIT_INVALID: non-Release commit provenance is inconsistent.")
    validate_project_version(document.get("application_version"))
    if document.get("application_version_source") not in {"staged_pyproject", "installed_pyproject", "local_checkout_pyproject"}:
        raise ValueError("Application version source must be a trusted pyproject.toml.")
    if not str(document.get("architecture", "")).strip():
        raise ValueError("Architecture must not be empty.")
    app = _normalized_absolute_path(document.get("app_path"), "Application")
    launcher = _normalized_absolute_path(document.get("launcher_path"), "Launcher")
    if expected_app_path is not None and app != expected_app_path.expanduser().resolve(strict=False):
        raise ValueError("Application path does not match the install target.")
    if document.get("platform") in {"windows_powershell", "windows_cmd"}:
        if app.name != "app" or app.parent.name != "M32Bridge" or launcher.parent != app.parent / "bin" or launcher.name.lower() != "m32-bridge.cmd":
            raise ValueError("Install paths are outside the Windows user-local roots.")
    else:
        expected_launcher = app.parent.parent / ".local" / "bin" / "m32-bridge"
        if app.name != "app" or app.parent.name != ".m32-bridge" or launcher != expected_launcher:
            raise ValueError("Install paths are outside the POSIX user-local roots.")


def _normalized_absolute_path(value: Any, label: str) -> Path:
    candidate = Path(str(value)).expanduser()
    if not candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ValueError(f"{label} path must be absolute and normalized.")
    normalized = candidate.resolve(strict=False)
    if str(candidate) != str(normalized):
        raise ValueError(f"{label} path must be absolute and normalized.")
    return normalized


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("Installed timestamp must be a string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Installed timestamp must be valid RFC3339.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Installed timestamp must include a timezone.")


def _result_application_version(result: Mapping[str, Any], app_path: Path) -> tuple[str, str]:
    staged_root = result.get("staged_source_root") or result.get("_source_root")
    if staged_root:
        resolution = resolve_staged_application_version(str(staged_root))
        if resolution.status != "resolved":
            raise ValueError("PROJECT_VERSION_INVALID: staged pyproject.toml is unavailable or invalid.")
        requested_value = result.get("application_version")
        if requested_value not in {None, ""} and validate_project_version(requested_value) != resolution.version:
            raise ValueError("RELEASE_VERSION_MISMATCH: application_version must match staged pyproject.toml.")
        return resolution.version, "staged_pyproject"
    installed = resolve_installed_application_version(app_path, local_development=False)
    if installed.status in {"resolved", "version_source_mismatch"} and installed.source == "installed_pyproject":
        requested_value = result.get("application_version")
        if requested_value not in {None, ""} and validate_project_version(requested_value) != installed.version:
            raise ValueError("RELEASE_VERSION_MISMATCH: application_version must match installed pyproject.toml.")
        return installed.version, "installed_pyproject"
    value = result.get("application_version")
    source = result.get("application_version_source")
    if value not in {None, ""} and source in {"staged_pyproject", "installed_pyproject", "local_checkout_pyproject"}:
        return validate_project_version(value), str(source)
    raise ValueError("PROJECT_VERSION_MISSING: install metadata requires pyproject.toml application truth.")


def _checksum(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"RELEASE_MANIFEST_INVALID: {label} SHA256 must be 64 lowercase hexadecimal characters.")
    return value


def _printable(value: str, *, max_length: int) -> bool:
    if not value or len(value) > max_length:
        return False
    return all(character != "\x1b" and unicodedata.category(character) not in {"Cc", "Cf", "Cs"} for character in value)
