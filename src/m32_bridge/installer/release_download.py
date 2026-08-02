"""Secure release asset download, extraction, and identity preflight."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import shutil
import socket
import ssl
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit

from .application_version import resolve_staged_application_version
from .install_metadata import normalize_source_commit, validate_release_tag, version_from_release_tag
from .release_manifest import MANIFEST_MAX_BYTES, ReleaseManifestError, sha256_file, validate_release_manifest
from .release_selection import GITHUB_USER_AGENT, ReleaseResolution


RELEASE_REDIRECT_HOSTS = frozenset(
    {
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "github-releases.githubusercontent.com",
    }
)
MAX_REDIRECTS = 5
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
DOWNLOAD_TIMEOUT = 30.0


class ReleasePreflightError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ReleasePreflightResult:
    ok: bool
    selection_state: str
    resolved_release_tag: str | None
    resolved_source_commit: str | None
    manifest_status: str
    manifest_schema_version: str | None
    archive_checksum_status: str
    staged_application_version: str
    identity_status: str
    staged_source_root: str
    source_archive_url: str | None
    source_archive_sha256: str | None
    installer_asset_url: str | None
    installer_asset_sha256: str | None
    release_channel: str | None
    install_source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_initial_release_asset_url(url: str, *, expected_tag: str | None = None, expected_name: str | None = None) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset URL is invalid.") from exc
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
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset URL is outside the exact GitHub boundary.")
    parts = parsed.path.split("/")
    if len(parts) != 7 or parts[1:5] != ["DXBMARK", "m32-bridge", "releases", "download"]:
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset repository path is invalid.")
    tag, name = parts[5], parts[6]
    if name == "":
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset name is missing.")
    validate_release_tag(tag)
    allowed_names = {"m32-bridge-release.json", "m32-bridge-source.tar.gz", "m32-bridge-source.zip", "install.sh", "install.ps1", "SHA256SUMS"}
    if name not in allowed_names:
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset name is not allow-listed.")
    if expected_tag and tag != validate_release_tag(expected_tag):
        raise ReleasePreflightError("RELEASE_SOURCE_URL_MISMATCH", "Release asset URL uses another tag.")
    if expected_name and name != expected_name:
        raise ReleasePreflightError("RELEASE_SOURCE_URL_MISMATCH", "Release asset URL uses another asset name.")
    return url


def fetch_release_manifest(url: str, *, timeout: float = DOWNLOAD_TIMEOUT, opener: Any = None) -> bytes:
    validate_initial_release_asset_url(url, expected_name="m32-bridge-release.json")
    return _read_https(url, timeout=timeout, max_bytes=MANIFEST_MAX_BYTES, opener=opener)


def download_release_asset(
    url: str,
    destination: Path | str,
    *,
    expected_sha256: str,
    timeout: float = DOWNLOAD_TIMEOUT,
    max_bytes: int = MAX_ARCHIVE_BYTES,
    opener: Any = None,
) -> Path:
    validate_initial_release_asset_url(url)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    request_opener = opener or urllib.request.build_opener(_NoRedirect())
    current = url
    written = 0
    try:
        with target.open("wb") as output:
            for redirect_count in range(MAX_REDIRECTS + 1):
                request = urllib.request.Request(current, headers={"User-Agent": GITHUB_USER_AGENT})
                try:
                    response = request_opener.open(request, timeout=timeout)
                except urllib.error.HTTPError as exc:
                    if exc.code not in {301, 302, 303, 307, 308} or redirect_count >= MAX_REDIRECTS:
                        raise
                    current = _validated_redirect(current, exc.headers.get("Location"))
                    continue
                with response:
                    final_url = response.geturl()
                    if final_url != current:
                        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Unvalidated release asset redirect.")
                    length = response.headers.get("Content-Length")
                    if length and int(length) > max_bytes:
                        raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Release asset exceeds the download size limit.")
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Release asset exceeds the download size limit.")
                        digest.update(chunk)
                        output.write(chunk)
                    break
            else:
                raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release asset redirect limit exceeded.")
    except ReleasePreflightError:
        target.unlink(missing_ok=True)
        raise
    except (TimeoutError, socket.timeout) as exc:
        target.unlink(missing_ok=True)
        raise ReleasePreflightError("RELEASE_RESOLUTION_TIMEOUT", "Release asset download timed out.") from exc
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ssl.SSLError, ValueError) as exc:
        target.unlink(missing_ok=True)
        raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Release asset download failed safely.") from exc
    if written == 0 or digest.hexdigest() != expected_sha256:
        target.unlink(missing_ok=True)
        raise ReleasePreflightError("RELEASE_ARCHIVE_CHECKSUM_MISMATCH", "Downloaded release asset checksum does not match the manifest.")
    return target


def safe_extract_archive(archive_path: Path | str, staging_root: Path | str) -> Path:
    archive = Path(archive_path)
    target = Path(staging_root)
    target.mkdir(parents=True, exist_ok=True)
    try:
        if archive.name.endswith(".tar.gz"):
            _extract_tar(archive, target)
        elif archive.name.endswith(".zip"):
            _extract_zip(archive, target)
        else:
            raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Unsupported source archive format.")
        return locate_single_project_root(target)
    except ReleasePreflightError:
        raise
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release source archive is invalid or unsafe.") from exc


def locate_single_project_root(staging_root: Path | str) -> Path:
    root = Path(staging_root)
    candidates = [
        path.parent
        for path in root.rglob("pyproject.toml")
        if (path.parent / "src" / "m32_bridge").is_dir() and not path.is_symlink()
    ]
    unique = sorted({candidate.resolve(strict=False) for candidate in candidates})
    if len(unique) != 1:
        raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive must contain one expected project root.")
    return unique[0]


def preflight_release_install(
    resolution: ReleaseResolution,
    *,
    platform: str,
    manifest_document: Mapping[str, Any] | str | bytes | None = None,
    archive_path: Path | str | None = None,
    staging_parent: Path | str | None = None,
    requested_version: str | None = None,
    manifest_fetcher: Callable[[str], bytes] | None = None,
    asset_downloader: Callable[..., Path] | None = None,
) -> ReleasePreflightResult:
    if resolution.install_source != "github_release_asset" or not resolution.release_tag or not resolution.source_commit:
        raise ReleasePreflightError("RELEASE_MANIFEST_INVALID", "Official Release preflight requires resolved tag and commit identity.")
    tag = validate_release_tag(resolution.release_tag)
    commit = normalize_source_commit(resolution.source_commit)
    if manifest_document is None:
        if not resolution.manifest_asset_url:
            raise ReleasePreflightError("RELEASE_MANIFEST_MISSING", "Resolved release has no manifest asset.")
        fetcher = manifest_fetcher or fetch_release_manifest
        manifest_document = fetcher(resolution.manifest_asset_url)
    try:
        manifest = validate_release_manifest(
            manifest_document,
            expected_release_tag=tag,
            resolved_source_commit=commit,
            requested_channel=resolution.release_channel,
        )
    except ReleaseManifestError as exc:
        raise ReleasePreflightError(exc.code, exc.message) from exc
    asset_key = "windows_source" if platform == "windows" or platform.startswith("windows") else "posix_source"
    installer_key = "windows_installer" if asset_key == "windows_source" else "posix_installer"
    asset = manifest["assets"][asset_key]
    installer_asset = manifest["assets"][installer_key]
    parent = Path(staging_parent) if staging_parent is not None else Path(tempfile.mkdtemp(prefix="m32-bridge-release-"))
    parent.mkdir(parents=True, exist_ok=True)
    archive = Path(archive_path) if archive_path is not None else parent / asset["name"]
    if archive_path is None:
        downloader = asset_downloader or download_release_asset
        downloader(asset["url"], archive, expected_sha256=asset["sha256"])
    elif not archive.is_file() or sha256_file(archive) != asset["sha256"]:
        raise ReleasePreflightError("RELEASE_ARCHIVE_CHECKSUM_MISMATCH", "Staged release archive checksum does not match the manifest.")
    extracted = parent / "extracted"
    if extracted.exists():
        shutil.rmtree(extracted)
    project_root = safe_extract_archive(archive, extracted)
    staged = resolve_staged_application_version(project_root)
    if staged.status != "resolved":
        raise ReleasePreflightError("RELEASE_VERSION_MISMATCH", "Staged source has no valid project version.")
    expected_version = version_from_release_tag(tag)
    requested = version_from_release_tag(requested_version) if requested_version else expected_version
    if len({requested, expected_version, manifest["application_version"], staged.version}) != 1:
        raise ReleasePreflightError("RELEASE_VERSION_MISMATCH", "Requested, tag, manifest, and staged project versions differ.")
    return ReleasePreflightResult(
        ok=True,
        selection_state=resolution.requested_selection,
        resolved_release_tag=tag,
        resolved_source_commit=commit,
        manifest_status="validated",
        manifest_schema_version=manifest["schema_version"],
        archive_checksum_status="verified",
        staged_application_version=staged.version,
        identity_status="validated",
        staged_source_root=str(project_root),
        source_archive_url=asset["url"],
        source_archive_sha256=asset["sha256"],
        installer_asset_url=installer_asset["url"],
        installer_asset_sha256=installer_asset["sha256"],
        release_channel=manifest["release_channel"],
        install_source="github_release_asset",
    )


def _read_https(url: str, *, timeout: float, max_bytes: int, opener: Any = None) -> bytes:
    request_opener = opener or urllib.request.build_opener(_NoRedirect())
    current = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers={"User-Agent": GITHUB_USER_AGENT})
        try:
            response = request_opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and redirect_count < MAX_REDIRECTS:
                current = _validated_redirect(current, exc.headers.get("Location"))
                continue
            if exc.code == 404:
                raise ReleasePreflightError("RELEASE_MANIFEST_MISSING", "Release manifest was not found.") from exc
            raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Release manifest request failed.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ReleasePreflightError("RELEASE_RESOLUTION_TIMEOUT", "Release manifest request timed out.") from exc
        except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
            raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Release manifest request failed safely.") from exc
        with response:
            if response.geturl() != current:
                raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Unvalidated manifest redirect.")
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ReleasePreflightError("RELEASE_MANIFEST_INVALID", "Release manifest exceeds the size limit.")
            payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ReleasePreflightError("RELEASE_MANIFEST_INVALID", "Release manifest exceeds the size limit.")
        return payload
    raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release manifest redirect limit exceeded.")


def _validated_redirect(current: str, location: str | None) -> str:
    candidate = urljoin(current, location or "")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release redirect URL is invalid.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or host not in RELEASE_REDIRECT_HOSTS or parsed.username or parsed.password or port not in {None, 443} or parsed.fragment:
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Release redirect host or scheme is not allow-listed.")
    if host in {"localhost", "localhost.localdomain"} or _is_private_ip_literal(host):
        raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Private or loopback release redirect rejected.")
    return candidate


def _is_private_ip_literal(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified)


def _safe_member_path(name: str, root: Path) -> Path:
    if not name or "\\" in name:
        raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path is invalid.")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path escapes staging.")
    destination = root.joinpath(*pure.parts)
    try:
        destination.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Archive entry path escapes staging.") from exc
    return destination


def _extract_tar(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        if len(members) > MAX_ARCHIVE_ENTRIES or sum(max(member.size, 0) for member in members) > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive exceeds extraction limits.")
        for member in members:
            destination = _safe_member_path(member.name.rstrip("/"), target)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive links or devices are not permitted.")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive member could not be read.")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Unsupported release archive entry.")


def _extract_zip(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as handle:
        members = handle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES or sum(member.file_size for member in members) > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive exceeds extraction limits.")
        for member in members:
            destination = _safe_member_path(member.filename.rstrip("/"), target)
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ReleasePreflightError("RELEASE_ARCHIVE_UNSAFE", "Release archive symlinks are not permitted.")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None
