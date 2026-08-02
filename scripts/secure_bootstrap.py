#!/usr/bin/env python3
"""Stdlib-only secure bootstrap for standalone M32 Bridge installers.

This module is embedded into the POSIX and PowerShell installer assets. It is
executed before any downloaded project source is added to ``PYTHONPATH``.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit


GITHUB_REPOSITORY = "DXBMARK/m32-bridge"
GITHUB_API_ROOT = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_USER_AGENT = "X32-Bridge-MCP-Standalone-Installer"
MANIFEST_FILENAME = "m32-bridge-release.json"
MANIFEST_SCHEMA_VERSION = "1"
MANIFEST_PRODUCT = "X32-Bridge MCP"
MANIFEST_MAX_BYTES = 128 * 1024
MAX_API_RESPONSE_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_REDIRECTS = 5
API_TIMEOUT = 10.0
DOWNLOAD_TIMEOUT = 30.0
RELEASE_REDIRECT_HOSTS = frozenset(
    {
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "github-releases.githubusercontent.com",
    }
)
ASSET_NAMES = {
    "posix_source": "m32-bridge-source.tar.gz",
    "windows_source": "m32-bridge-source.zip",
    "posix_installer": "install.sh",
    "windows_installer": "install.ps1",
}
_TOP_LEVEL_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "product",
        "application_version",
        "release_tag",
        "release_channel",
        "source_commit",
        "repository_url",
        "published_at",
        "assets",
    }
)
_ASSET_FIELDS = frozenset({"name", "url", "sha256"})
_TAG_RE = re.compile(
    r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[A-Za-z][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[A-Za-z][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
_VERSION_RE = re.compile(_TAG_RE.pattern.removeprefix("v"))
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


class BootstrapError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BootstrapPlan:
    schema_version: str
    ok: bool
    status: str
    surface: str
    dry_run: bool
    requested_selection: str
    selection_kind: str
    release_channel: str | None
    release_tag: str | None
    source_commit: str
    source_ref: str
    install_source: str
    manifest_status: str
    manifest_schema_version: str | None
    archive_checksum_status: str
    staged_application_version: str | None
    application_version: str | None
    identity_status: str
    source_archive_url: str
    source_archive_sha256: str | None
    installer_asset_url: str | None
    installer_asset_sha256: str | None
    manifest_path: str | None
    archive_path: str | None
    source_root: str | None
    user_local: bool = True
    admin_required: bool = False
    system_python_modified: bool = False
    network_scan: str = "not_run"
    console_probe: str = "not_run"
    osc_writes_sent: int = 0
    hardware_verified: bool = False
    production_live_ready: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Resolution:
    requested_selection: str
    selection_kind: str
    release_channel: str | None
    release_tag: str | None
    source_commit: str
    install_source: str
    published_at: str | None = None
    manifest_asset_url: str | None = None


def validate_release_tag(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > 128:
        raise BootstrapError("RELEASE_TAG_INVALID", "Release tag must be one trimmed v-prefixed SemVer value.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise BootstrapError("RELEASE_TAG_INVALID", "Release tag contains control characters.")
    if any(character in value for character in ("/", "\\", "%", "?", "#")) or _TAG_RE.fullmatch(value) is None:
        raise BootstrapError("RELEASE_TAG_INVALID", "Release tag must be strict v-prefixed SemVer.")
    return value


def validate_project_version(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > 128:
        raise BootstrapError("PROJECT_VERSION_INVALID", "Project version must be one trimmed value.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value) or _VERSION_RE.fullmatch(value) is None:
        raise BootstrapError("PROJECT_VERSION_INVALID", "Project version must be strict SemVer-compatible metadata.")
    return value


def normalize_commit(value: object) -> str:
    if not isinstance(value, str):
        raise BootstrapError("RELEASE_SOURCE_COMMIT_INVALID", "Source commit must be full hexadecimal SHA.")
    normalized = value.lower()
    if _COMMIT_RE.fullmatch(normalized) is None:
        raise BootstrapError("RELEASE_SOURCE_COMMIT_INVALID", "Source commit must be full 40-character hexadecimal SHA.")
    return normalized


def version_from_tag(tag: str) -> str:
    return validate_release_tag(tag)[1:]


def resolve_bootstrap(
    *,
    surface: str,
    output_root: Path | str,
    version: str | None = None,
    channel: str | None = None,
    ref: str | None = None,
    dry_run: bool = False,
    json_get: Callable[[str, float, int], Any] | None = None,
    byte_get: Callable[[str, int, float], bytes] | None = None,
    asset_download: Callable[..., Path] | None = None,
) -> BootstrapPlan:
    if surface not in {"posix", "windows"}:
        raise BootstrapError("INSTALL_PLATFORM_INVALID", "surface must be posix or windows.")
    requested = [name for name, value in (("version", version), ("channel", channel), ("ref", ref)) if value]
    if len(requested) > 1:
        raise BootstrapError("INSTALL_SELECTION_CONFLICT", "Use only one remote selector.")
    normalized_channel = (channel or "stable").strip().lower()
    if version:
        selection_kind = "version"
        requested_selection = validate_release_tag(version)
    elif ref:
        selection_kind = "commit"
        requested_selection = "commit"
    else:
        if normalized_channel not in {"stable", "prerelease", "main"}:
            raise BootstrapError("INSTALL_CHANNEL_INVALID", "channel must be stable, prerelease, or main.")
        selection_kind = normalized_channel
        requested_selection = normalized_channel

    resolver = json_get or _bounded_github_json
    resolution = _resolve_selection(
        selection_kind=selection_kind,
        requested_selection=requested_selection,
        version=version,
        ref=ref,
        json_get=resolver,
    )
    root = Path(output_root).expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)

    if resolution.install_source == "github_release_asset":
        manifest_url = resolution.manifest_asset_url
        if not manifest_url:
            raise BootstrapError("RELEASE_MANIFEST_MISSING", "Resolved release has no manifest asset.")
        manifest_bytes = (byte_get or _bounded_https_bytes)(manifest_url, MANIFEST_MAX_BYTES, DOWNLOAD_TIMEOUT)
        manifest = validate_release_manifest(
            manifest_bytes,
            expected_release_tag=resolution.release_tag,
            resolved_source_commit=resolution.source_commit,
            requested_channel=resolution.release_channel,
        )
        manifest_path = root / MANIFEST_FILENAME
        asset_key = "windows_source" if surface == "windows" else "posix_source"
        installer_key = "windows_installer" if surface == "windows" else "posix_installer"
        asset = manifest["assets"][asset_key]
        installer_asset = manifest["assets"][installer_key]
        if dry_run:
            return BootstrapPlan(
                schema_version="1",
                ok=True,
                status="release_plan_ready",
                surface=surface,
                dry_run=True,
                requested_selection=resolution.requested_selection,
                selection_kind=resolution.selection_kind,
                release_channel=resolution.release_channel,
                release_tag=resolution.release_tag,
                source_commit=resolution.source_commit,
                source_ref=resolution.source_commit,
                install_source=resolution.install_source,
                manifest_status="validated",
                manifest_schema_version=manifest["schema_version"],
                archive_checksum_status="not_downloaded_dry_run",
                staged_application_version=None,
                application_version=manifest["application_version"],
                identity_status="resolved_not_materialized",
                source_archive_url=asset["url"],
                source_archive_sha256=asset["sha256"],
                installer_asset_url=installer_asset["url"],
                installer_asset_sha256=installer_asset["sha256"],
                manifest_path=None,
                archive_path=None,
                source_root=None,
            )
        manifest_path.write_bytes(manifest_bytes)
        archive = root / asset["name"]
        downloader = asset_download or download_source_asset
        downloader(
            asset["url"],
            archive,
            expected_sha256=asset["sha256"],
            boundary="release",
            expected_commit=resolution.source_commit,
        )
        extracted = root / "extracted"
        project_root = safe_extract_archive(archive, extracted)
        staged_version = read_project_version(project_root / "pyproject.toml")
        expected_version = version_from_tag(str(resolution.release_tag))
        if len({expected_version, manifest["application_version"], staged_version}) != 1:
            raise BootstrapError("RELEASE_VERSION_MISMATCH", "Release tag, manifest, and staged project versions differ.")
        return BootstrapPlan(
            schema_version="1",
            ok=True,
            status="release_preflight_complete",
            surface=surface,
            dry_run=False,
            requested_selection=resolution.requested_selection,
            selection_kind=resolution.selection_kind,
            release_channel=resolution.release_channel,
            release_tag=resolution.release_tag,
            source_commit=resolution.source_commit,
            source_ref=resolution.source_commit,
            install_source=resolution.install_source,
            manifest_status="validated",
            manifest_schema_version=manifest["schema_version"],
            archive_checksum_status="verified",
            staged_application_version=staged_version,
            application_version=staged_version,
            identity_status="validated",
            source_archive_url=asset["url"],
            source_archive_sha256=asset["sha256"],
            installer_asset_url=installer_asset["url"],
            installer_asset_sha256=installer_asset["sha256"],
            manifest_path=str(manifest_path),
            archive_path=str(archive),
            source_root=str(project_root),
        )

    commit = normalize_commit(resolution.source_commit)
    suffix = ".zip" if surface == "windows" else ".tar.gz"
    source_url = f"{GITHUB_REPOSITORY_URL}/archive/{commit}{suffix}"
    if dry_run:
        return BootstrapPlan(
            schema_version="1",
            ok=True,
            status="commit_plan_ready",
            surface=surface,
            dry_run=True,
            requested_selection=resolution.requested_selection,
            selection_kind=resolution.selection_kind,
            release_channel=resolution.release_channel,
            release_tag=None,
            source_commit=commit,
            source_ref=commit,
            install_source=resolution.install_source,
            manifest_status="not_applicable",
            manifest_schema_version=None,
            archive_checksum_status="not_downloaded_dry_run",
            staged_application_version=None,
            application_version=None,
            identity_status="resolved_not_materialized",
            source_archive_url=source_url,
            source_archive_sha256=None,
            installer_asset_url=None,
            installer_asset_sha256=None,
            manifest_path=None,
            archive_path=None,
            source_root=None,
        )
    archive = root / f"m32-bridge-source{suffix}"
    downloader = asset_download or download_source_asset
    downloader(source_url, archive, expected_sha256=None, boundary="commit", expected_commit=commit)
    extracted = root / "extracted"
    project_root = safe_extract_archive(archive, extracted)
    staged_version = read_project_version(project_root / "pyproject.toml")
    return BootstrapPlan(
        schema_version="1",
        ok=True,
        status="commit_preflight_complete",
        surface=surface,
        dry_run=False,
        requested_selection=resolution.requested_selection,
        selection_kind=resolution.selection_kind,
        release_channel=resolution.release_channel,
        release_tag=None,
        source_commit=commit,
        source_ref=commit,
        install_source=resolution.install_source,
        manifest_status="not_applicable",
        manifest_schema_version=None,
        archive_checksum_status="verified_by_commit_source",
        staged_application_version=staged_version,
        application_version=staged_version,
        identity_status="validated",
        source_archive_url=source_url,
        source_archive_sha256=None,
        installer_asset_url=None,
        installer_asset_sha256=None,
        manifest_path=None,
        archive_path=str(archive),
        source_root=str(project_root),
    )


def _resolve_selection(
    *,
    selection_kind: str,
    requested_selection: str,
    version: str | None,
    ref: str | None,
    json_get: Callable[[str, float, int], Any],
) -> _Resolution:
    if selection_kind == "commit":
        requested_commit = normalize_commit(ref)
        commit = _resolve_commit(requested_commit, expected=requested_commit, json_get=json_get)
        return _Resolution("commit", "commit", None, None, commit, "github_commit_archive")
    if selection_kind == "main":
        commit = _resolve_commit("main", expected=None, json_get=json_get)
        return _Resolution("main", "main", "main", None, commit, "github_main")
    if selection_kind == "stable":
        release = _validate_release(json_get(f"{GITHUB_API_ROOT}/releases/latest", API_TIMEOUT, MAX_API_RESPONSE_BYTES), require_prerelease=False)
    elif selection_kind == "version":
        tag = validate_release_tag(version)
        release = _validate_release(
            json_get(f"{GITHUB_API_ROOT}/releases/tags/{tag}", API_TIMEOUT, MAX_API_RESPONSE_BYTES),
            expected_tag=tag,
        )
    elif selection_kind == "prerelease":
        response = json_get(f"{GITHUB_API_ROOT}/releases?per_page=100", API_TIMEOUT, MAX_API_RESPONSE_BYTES)
        if not isinstance(response, list):
            raise BootstrapError("RELEASE_RESPONSE_INVALID", "Prerelease response must be a list.")
        eligible: list[dict[str, Any]] = []
        for item in response:
            try:
                eligible.append(_validate_release(item, require_prerelease=True))
            except BootstrapError:
                continue
        if not eligible:
            raise BootstrapError("RELEASE_NOT_FOUND", "No published prerelease is available.")
        release = max(eligible, key=lambda item: _published_datetime(item["published_at"]))
    else:
        raise BootstrapError("INSTALL_SELECTION_CONFLICT", "Unsupported remote selection.")
    tag = validate_release_tag(release.get("tag_name"))
    commit = _resolve_commit(tag, expected=None, json_get=json_get)
    channel = "prerelease" if release.get("prerelease") is True else "stable"
    return _Resolution(
        requested_selection=requested_selection,
        selection_kind=selection_kind,
        release_channel=channel,
        release_tag=tag,
        source_commit=commit,
        install_source="github_release_asset",
        published_at=str(release["published_at"]),
        manifest_asset_url=_manifest_asset_url(release, tag),
    )


def _resolve_commit(ref: str, *, expected: str | None, json_get: Callable[[str, float, int], Any]) -> str:
    response = json_get(f"{GITHUB_API_ROOT}/commits/{ref}", API_TIMEOUT, MAX_API_RESPONSE_BYTES)
    if not isinstance(response, Mapping) or not _exact_api_identity(response.get("url"), "/commits/"):
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Commit response repository identity is invalid.")
    commit = normalize_commit(response.get("sha"))
    if expected and commit != normalize_commit(expected):
        raise BootstrapError("RELEASE_COMMIT_MISMATCH", "Resolved commit does not match requested commit.")
    return commit


def _validate_release(value: Any, *, expected_tag: str | None = None, require_prerelease: bool | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or not _exact_api_identity(value.get("url"), "/releases/"):
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release response repository identity is invalid.")
    if value.get("draft") is not False:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Draft releases cannot be installed.")
    if require_prerelease is not None and value.get("prerelease") is not require_prerelease:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release channel does not match requested channel.")
    tag = validate_release_tag(value.get("tag_name"))
    _published_datetime(value.get("published_at"))
    if expected_tag and tag != expected_tag:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release tag does not match requested tag.")
    return value


def _manifest_asset_url(release: Mapping[str, Any], tag: str) -> str:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise BootstrapError("RELEASE_MANIFEST_MISSING", "Release has no asset list.")
    expected = release_asset_url(tag, MANIFEST_FILENAME)
    matches = [item for item in assets if isinstance(item, Mapping) and item.get("name") == MANIFEST_FILENAME]
    if len(matches) != 1 or matches[0].get("browser_download_url") != expected:
        raise BootstrapError("RELEASE_MANIFEST_MISSING", "Release manifest asset is missing or has unexpected URL.")
    return expected


def validate_release_manifest(
    document: Mapping[str, Any] | str | bytes,
    *,
    expected_release_tag: str | None,
    resolved_source_commit: str | None,
    requested_channel: str | None,
) -> dict[str, Any]:
    loaded = _load_manifest(document)
    if set(loaded) != _TOP_LEVEL_MANIFEST_FIELDS:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest fields must exactly match schema version 1.")
    if loaded.get("schema_version") != MANIFEST_SCHEMA_VERSION or loaded.get("product") != MANIFEST_PRODUCT:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest schema or product is invalid.")
    if loaded.get("repository_url") != GITHUB_REPOSITORY_URL:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest repository identity is invalid.")
    version = validate_project_version(loaded.get("application_version"))
    tag = validate_release_tag(loaded.get("release_tag"))
    commit = normalize_commit(loaded.get("source_commit"))
    _published_datetime(loaded.get("published_at"))
    if version_from_tag(tag) != version:
        raise BootstrapError("RELEASE_VERSION_MISMATCH", "Manifest release tag does not match application version.")
    if expected_release_tag and tag != validate_release_tag(expected_release_tag):
        raise BootstrapError("RELEASE_VERSION_MISMATCH", "Manifest tag does not match resolved release tag.")
    if resolved_source_commit and commit != normalize_commit(resolved_source_commit):
        raise BootstrapError("RELEASE_COMMIT_MISMATCH", "Manifest commit does not match resolved tag commit.")
    channel = loaded.get("release_channel")
    if channel not in {"stable", "prerelease"}:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest release channel is invalid.")
    if (channel == "prerelease") is not ("-" in tag[1:]):
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest tag and release channel disagree.")
    if requested_channel in {"stable", "prerelease"} and channel != requested_channel:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest channel does not match selected channel.")
    assets = loaded.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(ASSET_NAMES):
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest asset keys are incomplete or unknown.")
    normalized_assets: dict[str, dict[str, str]] = {}
    for key, expected_name in ASSET_NAMES.items():
        item = assets.get(key)
        if not isinstance(item, dict) or set(item) != _ASSET_FIELDS:
            raise BootstrapError("RELEASE_MANIFEST_INVALID", f"Manifest asset {key} fields are invalid.")
        if item.get("name") != expected_name or item.get("url") != release_asset_url(tag, expected_name):
            raise BootstrapError("RELEASE_SOURCE_URL_MISMATCH", f"Manifest asset {key} URL or name is invalid.")
        checksum = item.get("sha256")
        if not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise BootstrapError("RELEASE_MANIFEST_INVALID", f"Manifest asset {key} checksum is invalid.")
        normalized_assets[key] = {"name": expected_name, "url": item["url"], "sha256": checksum}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": MANIFEST_PRODUCT,
        "application_version": version,
        "release_tag": tag,
        "release_channel": channel,
        "source_commit": commit,
        "repository_url": GITHUB_REPOSITORY_URL,
        "published_at": loaded["published_at"],
        "assets": normalized_assets,
    }


def release_asset_url(tag: str, name: str) -> str:
    validate_release_tag(tag)
    if name not in {MANIFEST_FILENAME, "SHA256SUMS", *ASSET_NAMES.values()}:
        raise BootstrapError("RELEASE_SOURCE_URL_MISMATCH", "Release asset name is not allow-listed.")
    return f"{GITHUB_REPOSITORY_URL}/releases/download/{tag}/{name}"


def download_source_asset(
    url: str,
    destination: Path | str,
    *,
    expected_sha256: str | None,
    boundary: str,
    expected_commit: str,
    timeout: float = DOWNLOAD_TIMEOUT,
    max_bytes: int = MAX_ARCHIVE_BYTES,
    opener: Any = None,
) -> Path:
    if boundary == "release":
        _validate_initial_release_asset_url(url)
    elif boundary == "commit":
        _validate_initial_commit_archive_url(url, expected_commit=expected_commit)
    else:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Unknown source boundary.")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    current = url
    written = 0
    digest = hashlib.sha256()
    request_opener = opener or urllib.request.build_opener(_NoRedirect())
    try:
        with target.open("wb") as output:
            for redirect_count in range(MAX_REDIRECTS + 1):
                request = urllib.request.Request(current, headers={"User-Agent": GITHUB_USER_AGENT})
                try:
                    response = request_opener.open(request, timeout=timeout)
                except urllib.error.HTTPError as exc:
                    if exc.code not in {301, 302, 303, 307, 308} or redirect_count >= MAX_REDIRECTS:
                        raise
                    current = _validated_redirect(
                        current,
                        exc.headers.get("Location"),
                        boundary=boundary,
                        expected_commit=expected_commit,
                        surface="windows" if target.name.endswith(".zip") else "posix",
                    )
                    continue
                with response:
                    if response.geturl() != current:
                        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Unvalidated source redirect.")
                    length = response.headers.get("Content-Length")
                    if length and int(length) > max_bytes:
                        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Source archive exceeds download limit.")
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            raise BootstrapError("RELEASE_RESPONSE_INVALID", "Source archive exceeds download limit.")
                        digest.update(chunk)
                        output.write(chunk)
                    break
            else:
                raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Source redirect limit exceeded.")
    except BootstrapError:
        target.unlink(missing_ok=True)
        raise
    except (TimeoutError, socket.timeout) as exc:
        target.unlink(missing_ok=True)
        raise BootstrapError("RELEASE_RESOLUTION_TIMEOUT", "Source archive download timed out.") from exc
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ssl.SSLError, ValueError) as exc:
        target.unlink(missing_ok=True)
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Source archive download failed safely.") from exc
    if written == 0:
        target.unlink(missing_ok=True)
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Downloaded source archive is empty.")
    if expected_sha256 and digest.hexdigest() != expected_sha256:
        target.unlink(missing_ok=True)
        raise BootstrapError("RELEASE_ARCHIVE_CHECKSUM_MISMATCH", "Downloaded archive checksum does not match manifest.")
    return target


def safe_extract_archive(archive_path: Path | str, staging_root: Path | str) -> Path:
    archive = Path(archive_path)
    target = Path(staging_root)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    try:
        if archive.name.endswith(".tar.gz"):
            _extract_tar(archive, target)
        elif archive.name.endswith(".zip"):
            _extract_zip(archive, target)
        else:
            raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Unsupported source archive format.")
    except BootstrapError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Source archive is invalid or unsafe.") from exc
    candidates = [
        item.parent
        for item in target.rglob("pyproject.toml")
        if (item.parent / "src" / "m32_bridge").is_dir() and not item.is_symlink()
    ]
    unique = sorted({candidate.resolve(strict=False) for candidate in candidates})
    if len(unique) != 1:
        raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Source archive must contain one expected project root.")
    return unique[0]


def read_project_version(path: Path | str) -> str:
    try:
        document = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise BootstrapError("PROJECT_METADATA_INVALID", "Staged pyproject.toml is invalid.") from exc
    project = document.get("project")
    if not isinstance(project, dict) or "version" not in project:
        raise BootstrapError("PROJECT_VERSION_MISSING", "Staged pyproject.toml has no project.version.")
    return validate_project_version(project["version"])


def _bounded_github_json(url: str, timeout: float, max_bytes: int) -> Any:
    if not _allowed_api_url(url):
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "GitHub API URL is outside repository boundary.")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": GITHUB_USER_AGENT,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.geturl() != url:
                raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Unexpected GitHub API redirect.")
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise BootstrapError("RELEASE_RESPONSE_INVALID", "GitHub API response exceeds size limit.")
            payload = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise BootstrapError("RELEASE_NOT_FOUND", "Requested release or commit was not found.") from exc
        if exc.code == 403:
            raise BootstrapError("GITHUB_RATE_LIMITED", "GitHub API rate limit prevented resolution.") from exc
        if 300 <= exc.code < 400:
            raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "GitHub API redirects are not accepted.") from exc
        raise BootstrapError("RELEASE_RESPONSE_INVALID", f"GitHub API returned HTTP {exc.code}.") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise BootstrapError("RELEASE_RESOLUTION_TIMEOUT", "GitHub resolution timed out.") from exc
    except (urllib.error.URLError, OSError, ssl.SSLError, ValueError) as exc:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "GitHub response failed safely.") from exc
    if len(payload) > max_bytes:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "GitHub API response exceeds size limit.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "GitHub API returned malformed JSON.") from exc


def _bounded_https_bytes(url: str, max_bytes: int, timeout: float) -> bytes:
    _validate_initial_release_asset_url(url, expected_name=MANIFEST_FILENAME)
    current = url
    opener = urllib.request.build_opener(_NoRedirect())
    for redirect_count in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers={"User-Agent": GITHUB_USER_AGENT})
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and redirect_count < MAX_REDIRECTS:
                current = _validated_redirect(current, exc.headers.get("Location"), boundary="release", expected_commit="0" * 40, surface="posix")
                continue
            if exc.code == 404:
                raise BootstrapError("RELEASE_MANIFEST_MISSING", "Release manifest was not found.") from exc
            raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release manifest request failed.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise BootstrapError("RELEASE_RESOLUTION_TIMEOUT", "Release manifest request timed out.") from exc
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release manifest request failed safely.") from exc
        with response:
            if response.geturl() != current:
                raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Unvalidated manifest redirect.")
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest exceeds size limit.")
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest exceeds size limit.")
        return payload
    raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Manifest redirect limit exceeded.")


def _validate_initial_release_asset_url(url: str, *, expected_name: str | None = None) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Release asset URL is invalid.") from exc
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != "github.com"
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.path
        or "%" in parsed.path
    ):
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Release asset URL is outside exact GitHub boundary.")
    parts = parsed.path.split("/")
    if len(parts) != 7 or parts[1:5] != ["DXBMARK", "m32-bridge", "releases", "download"]:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Release asset repository path is invalid.")
    validate_release_tag(parts[5])
    allowed = {MANIFEST_FILENAME, "SHA256SUMS", *ASSET_NAMES.values()}
    if parts[6] not in allowed or (expected_name and parts[6] != expected_name):
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Release asset name is not allow-listed.")


def _validate_initial_commit_archive_url(url: str, *, expected_commit: str) -> None:
    commit = normalize_commit(expected_commit)
    parsed = urlsplit(url)
    suffixes = {f"/{GITHUB_REPOSITORY}/archive/{commit}.tar.gz", f"/{GITHUB_REPOSITORY}/archive/{commit}.zip"}
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != "github.com"
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or parsed.path not in suffixes
    ):
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Commit archive URL is outside exact GitHub boundary.")


def _validated_redirect(current: str, location: str | None, *, boundary: str, expected_commit: str, surface: str) -> str:
    candidate = urljoin(current, location or "")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Redirect URL is invalid.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or parsed.username or parsed.password or port not in {None, 443} or parsed.fragment:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Redirect host or scheme is not allow-listed.")
    if host in {"localhost", "localhost.localdomain"} or _is_private_ip_literal(host):
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Private or loopback redirect rejected.")
    if boundary == "release":
        if host not in RELEASE_REDIRECT_HOSTS:
            raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Release redirect host is not allow-listed.")
        return candidate
    commit = normalize_commit(expected_commit)
    expected_path = f"/{GITHUB_REPOSITORY}/{'zip' if surface == 'windows' else 'tar.gz'}/{commit}"
    if host != "codeload.github.com" or parsed.path != expected_path or parsed.query:
        raise BootstrapError("SOURCE_BOUNDARY_REJECTED", "Commit redirect does not match repository, format, and commit.")
    return candidate


def _allowed_api_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower().rstrip(".") != "api.github.com"
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.fragment
        or "\\" in parsed.path
        or "%" in parsed.path
    ):
        return False
    return parsed.path.startswith(f"/repos/{GITHUB_REPOSITORY}/")


def _exact_api_identity(value: Any, marker: str) -> bool:
    if not isinstance(value, str) or not _allowed_api_url(value):
        return False
    return marker in urlsplit(value).path


def _published_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release publication time is invalid.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release publication time is invalid.") from exc
    if parsed.tzinfo is None:
        raise BootstrapError("RELEASE_RESPONSE_INVALID", "Release publication time has no timezone.")
    return parsed


def _load_manifest(value: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    if not isinstance(encoded, bytes) or len(encoded) > MANIFEST_MAX_BYTES:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest exceeds size limit.")
    try:
        loaded = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest JSON is invalid.") from exc
    if not isinstance(loaded, dict):
        raise BootstrapError("RELEASE_MANIFEST_INVALID", "Manifest root must be an object.")
    return loaded


def _is_private_ip_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified)


def _safe_member_path(name: str, root: Path) -> Path:
    if not name or "\\" in name:
        raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path is invalid.")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path escapes staging.")
    destination = root.joinpath(*pure.parts)
    try:
        destination.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path escapes staging.") from exc
    return destination


def _extract_tar(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        if len(members) > MAX_ARCHIVE_ENTRIES or sum(max(item.size, 0) for item in members) > MAX_ARCHIVE_EXPANDED_BYTES:
            raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive exceeds extraction limits.")
        for member in members:
            destination = _safe_member_path(member.name.rstrip("/"), target)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive links or devices are not permitted.")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive member could not be read.")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Unsupported archive entry.")


def _extract_zip(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as handle:
        members = handle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES or sum(item.file_size for item in members) > MAX_ARCHIVE_EXPANDED_BYTES:
            raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive exceeds extraction limits.")
        for member in members:
            destination = _safe_member_path(member.filename.rstrip("/"), target)
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive symlinks are not permitted.")
            if member.is_dir():
                if unix_mode not in {0, 0o040000}:
                    raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive directory type is invalid.")
                destination.mkdir(parents=True, exist_ok=True)
            else:
                if unix_mode not in {0, 0o100000}:
                    raise BootstrapError("RELEASE_ARCHIVE_UNSAFE", "Archive special files are not permitted.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secure standalone M32 Bridge source bootstrap")
    parser.add_argument("--surface", choices=("posix", "windows"), required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--version")
    parser.add_argument("--channel", choices=("stable", "prerelease", "main"))
    parser.add_argument("--ref")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = resolve_bootstrap(
            surface=args.surface,
            output_root=args.output_root,
            version=args.version,
            channel=args.channel,
            ref=args.ref,
            dry_run=args.dry_run,
        )
    except BootstrapError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "1",
                    "ok": False,
                    "status": "failed",
                    "error_code": exc.code,
                    "message": exc.message,
                    "admin_required": False,
                    "system_python_modified": False,
                    "network_scan": "not_run",
                    "console_probe": "not_run",
                    "osc_writes_sent": 0,
                    "hardware_verified": False,
                    "production_live_ready": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
