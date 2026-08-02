"""Unified installer selection and GitHub release resolution."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .install_metadata import normalize_source_commit, validate_release_tag


GITHUB_REPOSITORY = "DXBMARK/m32-bridge"
GITHUB_API_ROOT = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_USER_AGENT = "X32-Bridge-MCP-Installer"
DEFAULT_TIMEOUT = 10.0
MAX_API_RESPONSE_BYTES = 1024 * 1024
PUBLIC_CHANNELS = frozenset({"stable", "prerelease", "main"})


class ReleaseSelectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ReleaseResolutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class InstallationSelection:
    requested_selection: str
    kind: str
    channel: str | None
    version: str | None
    release_tag: str | None
    source_commit: str | None
    install_source: str
    origin: str


@dataclass(frozen=True)
class ReleaseResolution:
    requested_selection: str
    selection_kind: str
    release_channel: str | None
    release_tag: str | None
    source_commit: str | None
    source_ref: str | None
    install_source: str
    published_at: str | None = None
    manifest_asset_url: str | None = None


def is_local_checkout(source_root: Path | str | None) -> bool:
    if source_root is None:
        return False
    root = Path(source_root)
    return (root / "pyproject.toml").is_file() and (root / "src" / "m32_bridge").is_dir()


def resolve_installation_selection(
    *,
    version: str | None = None,
    channel: str | None = None,
    ref: str | None = None,
    local: bool | None = None,
    environ: Mapping[str, str] | None = None,
    source_root: Path | str | None = None,
) -> InstallationSelection:
    """Apply CLI, environment, local autodetection, then stable priority."""

    env = dict(os.environ if environ is None else environ)
    cli_present = any(value not in {None, False, ""} for value in (version, channel, ref, local))
    if not cli_present:
        version = _optional(env.get("M32_INSTALL_VERSION"))
        channel = _optional(env.get("M32_INSTALL_CHANNEL"))
        ref = _optional(env.get("M32_INSTALL_REF"))
        local_value = _optional(env.get("M32_INSTALL_LOCAL"))
        local = _parse_env_bool(local_value) if local_value is not None else None
        origin = "environment" if any(value not in {None, False, ""} for value in (version, channel, ref, local)) else "default"
    else:
        origin = "cli"

    requested = [name for name, value in (("version", version), ("channel", channel), ("ref", ref), ("local", local is True)) if value not in {None, False, ""}]
    if len(requested) > 1:
        raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", f"Conflicting public selectors: {', '.join(requested)}.")
    if local is False and not requested:
        local = None

    if version:
        tag = validate_release_tag(version)
        return InstallationSelection(tag, "version", None, tag[1:], tag, None, "github_release_asset", origin)
    if ref:
        commit = normalize_source_commit(ref)
        return InstallationSelection("commit", "commit", None, None, None, commit, "github_commit_archive", origin)
    if local:
        return InstallationSelection("local", "local", None, None, None, None, "local_checkout", origin)
    if channel:
        normalized_channel = str(channel).strip().lower()
        if normalized_channel not in PUBLIC_CHANNELS:
            raise ReleaseSelectionError("INSTALL_CHANNEL_INVALID", "channel must be stable, prerelease, or main.")
        if normalized_channel == "main":
            return InstallationSelection("main", "main", "main", None, None, None, "github_main", origin)
        return InstallationSelection(normalized_channel, normalized_channel, normalized_channel, None, None, None, "github_release_asset", origin)
    if is_local_checkout(source_root):
        return InstallationSelection("local", "local", None, None, None, None, "local_checkout", "auto_local")
    return InstallationSelection("stable", "stable", "stable", None, None, None, "github_release_asset", "default")


class ReleaseResolver:
    """Resolve public selections against the one official GitHub repository."""

    def __init__(
        self,
        *,
        json_get: Callable[[str, float, int], Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_response_bytes: int = MAX_API_RESPONSE_BYTES,
    ) -> None:
        self._json_get = json_get or _bounded_github_json
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    def resolve(self, selection: InstallationSelection) -> ReleaseResolution:
        if selection.kind == "local":
            return ReleaseResolution("local", "local", None, None, None, None, "local_checkout")
        if selection.kind == "main":
            commit = self._resolve_commit("main", expected=None)
            return ReleaseResolution("main", "main", "main", None, commit, commit, "github_main")
        if selection.kind == "commit":
            commit = self._resolve_commit(str(selection.source_commit), expected=selection.source_commit)
            return ReleaseResolution("commit", "commit", None, None, commit, commit, "github_commit_archive")

        if selection.kind == "stable":
            release = self._get(f"{GITHUB_API_ROOT}/releases/latest")
            release = self._validate_release(release, require_prerelease=False)
        elif selection.kind == "version":
            tag = validate_release_tag(selection.release_tag)
            release = self._get(f"{GITHUB_API_ROOT}/releases/tags/{tag}")
            release = self._validate_release(release, expected_tag=tag)
        elif selection.kind == "prerelease":
            releases = self._get(f"{GITHUB_API_ROOT}/releases?per_page=100")
            if not isinstance(releases, list):
                raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Prerelease response must be a list.")
            eligible: list[dict[str, Any]] = []
            for item in releases:
                try:
                    eligible.append(self._validate_release(item, require_prerelease=True))
                except ReleaseResolutionError:
                    continue
            if not eligible:
                raise ReleaseResolutionError("RELEASE_NOT_FOUND", "No published prerelease is available.")
            release = max(eligible, key=lambda item: _published_datetime(item["published_at"]))
        else:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Unsupported installation selection.")

        tag = validate_release_tag(release.get("tag_name"))
        commit = self._resolve_commit(tag, expected=None)
        channel = "prerelease" if release.get("prerelease") is True else "stable"
        manifest_url = _manifest_asset_url(release, tag)
        return ReleaseResolution(
            requested_selection=selection.requested_selection,
            selection_kind=selection.kind,
            release_channel=channel,
            release_tag=tag,
            source_commit=commit,
            source_ref=commit,
            install_source="github_release_asset",
            published_at=str(release["published_at"]),
            manifest_asset_url=manifest_url,
        )

    def _get(self, url: str) -> Any:
        if not _allowed_api_url(url):
            raise ReleaseResolutionError("SOURCE_BOUNDARY_REJECTED", "GitHub API URL is outside the official repository boundary.")
        return self._json_get(url, self.timeout, self.max_response_bytes)

    def _resolve_commit(self, ref: str, *, expected: str | None) -> str:
        response = self._get(f"{GITHUB_API_ROOT}/commits/{ref}")
        if not isinstance(response, Mapping) or not _exact_api_identity(response.get("url"), "/commits/"):
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Commit response repository identity is invalid.")
        try:
            commit = normalize_source_commit(response.get("sha"))
        except ValueError as exc:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Commit response has no full immutable SHA.") from exc
        if expected and commit != normalize_source_commit(expected):
            raise ReleaseResolutionError("RELEASE_COMMIT_MISMATCH", "Resolved commit does not match the requested commit.")
        return commit

    def _validate_release(
        self,
        value: Any,
        *,
        expected_tag: str | None = None,
        require_prerelease: bool | None = None,
    ) -> dict[str, Any]:
        if not isinstance(value, dict) or not _exact_api_identity(value.get("url"), "/releases/"):
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Release response repository identity is invalid.")
        if value.get("draft") is not False:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Draft releases cannot be installed.")
        if require_prerelease is not None and value.get("prerelease") is not require_prerelease:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Release channel does not match the requested channel.")
        try:
            tag = validate_release_tag(value.get("tag_name"))
            _published_datetime(value.get("published_at"))
        except (ValueError, TypeError) as exc:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Release tag or publication time is invalid.") from exc
        if expected_tag and tag != expected_tag:
            raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "Release tag does not match the requested tag.")
        return value


def _bounded_github_json(url: str, timeout: float, max_bytes: int) -> Any:
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
            final_url = response.geturl()
            if final_url != url:
                raise ReleaseResolutionError("SOURCE_BOUNDARY_REJECTED", "Unexpected GitHub API redirect.")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "GitHub API response exceeds the size limit.")
            payload = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ReleaseResolutionError("RELEASE_NOT_FOUND", "The requested GitHub release or commit was not found.") from exc
        if exc.code == 403:
            raise ReleaseResolutionError("GITHUB_RATE_LIMITED", "GitHub API rate limit prevented release resolution.") from exc
        if 300 <= exc.code < 400:
            raise ReleaseResolutionError("SOURCE_BOUNDARY_REJECTED", "GitHub API redirects are not accepted.") from exc
        raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", f"GitHub API returned HTTP {exc.code}.") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise ReleaseResolutionError("RELEASE_RESOLUTION_TIMEOUT", "GitHub release resolution timed out.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ReleaseResolutionError("RELEASE_RESOLUTION_TIMEOUT", "GitHub release resolution timed out.") from exc
        raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "GitHub release resolution failed.") from exc
    except (ValueError, OSError) as exc:
        raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "GitHub API response could not be read safely.") from exc
    if len(payload) > max_bytes:
        raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "GitHub API response exceeds the size limit.")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseResolutionError("RELEASE_RESPONSE_INVALID", "GitHub API returned malformed JSON.") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _manifest_asset_url(release: Mapping[str, Any], tag: str) -> str:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ReleaseResolutionError("RELEASE_MANIFEST_MISSING", "Release has no manifest asset list.")
    expected = f"{GITHUB_REPOSITORY_URL}/releases/download/{tag}/m32-bridge-release.json"
    matches = [item for item in assets if isinstance(item, Mapping) and item.get("name") == "m32-bridge-release.json"]
    if len(matches) != 1 or matches[0].get("browser_download_url") != expected:
        raise ReleaseResolutionError("RELEASE_MANIFEST_MISSING", "Release manifest asset is missing or has an unexpected URL.")
    return expected


def _allowed_api_url(url: str) -> bool:
    if not isinstance(url, str) or any(ord(character) < 32 for character in url):
        return False
    allowed = (
        f"{GITHUB_API_ROOT}/releases/latest",
        f"{GITHUB_API_ROOT}/releases?per_page=100",
    )
    return url in allowed or url.startswith(f"{GITHUB_API_ROOT}/releases/tags/v") or url.startswith(f"{GITHUB_API_ROOT}/commits/")


def _exact_api_identity(value: Any, resource_prefix: str) -> bool:
    return isinstance(value, str) and value.startswith(f"{GITHUB_API_ROOT}{resource_prefix}") and "?" not in value and "#" not in value


def _published_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("published_at must be RFC3339 UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("published_at must include timezone")
    return parsed


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_env_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ReleaseSelectionError("INSTALL_LOCAL_INVALID", "M32_INSTALL_LOCAL must be a boolean value.")
