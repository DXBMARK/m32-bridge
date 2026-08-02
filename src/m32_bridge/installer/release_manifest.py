"""Strict, versionless GitHub Release manifest contract."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .application_version import read_project_version
from .install_metadata import normalize_source_commit, validate_release_tag, version_from_release_tag


MANIFEST_SCHEMA_VERSION = "1"
MANIFEST_PRODUCT = "X32-Bridge MCP"
MANIFEST_FILENAME = "m32-bridge-release.json"
MANIFEST_MAX_BYTES = 128 * 1024
REPOSITORY_URL = "https://github.com/DXBMARK/m32-bridge"
ASSET_NAMES = {
    "posix_source": "m32-bridge-source.tar.gz",
    "windows_source": "m32-bridge-source.zip",
    "posix_installer": "install.sh",
    "windows_installer": "install.ps1",
}
_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "product", "application_version", "release_tag", "release_channel", "source_commit", "repository_url", "published_at", "assets"}
)
_ASSET_FIELDS = frozenset({"name", "url", "sha256"})


class ReleaseManifestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def validate_release_manifest(
    document: Mapping[str, Any] | str | bytes,
    *,
    expected_release_tag: str | None = None,
    resolved_source_commit: str | None = None,
    requested_channel: str | None = None,
) -> dict[str, Any]:
    """Return a validated manifest copy or fail closed with a controlled code."""

    loaded = _load_document(document)
    if set(loaded) != _TOP_LEVEL_FIELDS:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest fields must exactly match schema version 1.")
    if loaded.get("schema_version") != MANIFEST_SCHEMA_VERSION or loaded.get("product") != MANIFEST_PRODUCT:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest schema or product is invalid.")
    if loaded.get("repository_url") != REPOSITORY_URL:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest repository identity is invalid.")
    try:
        version = read_project_version_from_value(loaded.get("application_version"))
        tag = validate_release_tag(loaded.get("release_tag"))
        commit = normalize_source_commit(loaded.get("source_commit"))
        _validate_rfc3339(loaded.get("published_at"))
    except ValueError as exc:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest version, tag, commit, or timestamp is invalid.") from exc
    if version_from_release_tag(tag) != version:
        raise ReleaseManifestError("RELEASE_VERSION_MISMATCH", "Manifest release tag does not match application_version.")
    if expected_release_tag and tag != validate_release_tag(expected_release_tag):
        raise ReleaseManifestError("RELEASE_VERSION_MISMATCH", "Manifest tag does not match the resolved release tag.")
    if resolved_source_commit and commit != normalize_source_commit(resolved_source_commit):
        raise ReleaseManifestError("RELEASE_COMMIT_MISMATCH", "Manifest source_commit does not match the resolved tag commit.")
    channel = loaded.get("release_channel")
    if channel not in {"stable", "prerelease"}:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest release_channel is invalid.")
    tag_is_prerelease = "-" in tag[1:]
    if (channel == "prerelease") is not tag_is_prerelease:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest tag and release_channel disagree.")
    if requested_channel in {"stable", "prerelease"} and requested_channel != channel:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest channel does not match the selected channel.")

    assets = loaded.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(ASSET_NAMES):
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest asset keys are incomplete or unknown.")
    normalized_assets: dict[str, dict[str, str]] = {}
    for key, expected_name in ASSET_NAMES.items():
        asset = assets.get(key)
        if not isinstance(asset, dict) or set(asset) != _ASSET_FIELDS:
            raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", f"Manifest asset {key} has invalid fields.")
        if asset.get("name") != expected_name:
            raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", f"Manifest asset {key} has an unexpected name.")
        expected_url = release_asset_url(tag, expected_name)
        if asset.get("url") != expected_url:
            raise ReleaseManifestError("RELEASE_SOURCE_URL_MISMATCH", f"Manifest asset {key} URL is outside the exact release boundary.")
        checksum = asset.get("sha256")
        if not isinstance(checksum, str) or len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
            raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", f"Manifest asset {key} checksum is invalid.")
        normalized_assets[key] = {"name": expected_name, "url": expected_url, "sha256": checksum}
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": MANIFEST_PRODUCT,
        "application_version": version,
        "release_tag": tag,
        "release_channel": channel,
        "source_commit": commit,
        "repository_url": REPOSITORY_URL,
        "published_at": loaded["published_at"],
        "assets": normalized_assets,
    }


def build_release_manifest(
    *,
    source_root: Path | str,
    assets_dir: Path | str,
    release_tag: str,
    source_commit: str,
    published_at: str,
    release_channel: str | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    assets_root = Path(assets_dir)
    application_version = read_project_version(root / "pyproject.toml")
    tag = validate_release_tag(release_tag)
    commit = normalize_source_commit(source_commit)
    _validate_rfc3339(published_at)
    if version_from_release_tag(tag) != application_version:
        raise ReleaseManifestError("RELEASE_VERSION_MISMATCH", "Release tag must equal v<project.version>.")
    channel = release_channel or ("prerelease" if "-" in application_version else "stable")
    assets: dict[str, dict[str, str]] = {}
    for key, name in ASSET_NAMES.items():
        path = assets_root / name
        if not path.is_file():
            raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", f"Required release asset is missing: {name}")
        assets[key] = {"name": name, "url": release_asset_url(tag, name), "sha256": sha256_file(path)}
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": MANIFEST_PRODUCT,
        "application_version": application_version,
        "release_tag": tag,
        "release_channel": channel,
        "source_commit": commit,
        "repository_url": REPOSITORY_URL,
        "published_at": published_at,
        "assets": assets,
    }
    return validate_release_manifest(manifest, expected_release_tag=tag, resolved_source_commit=commit, requested_channel=channel)


def serialize_release_manifest(document: Mapping[str, Any]) -> str:
    validated = validate_release_manifest(document)
    return json.dumps(validated, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_release_manifest(document: Mapping[str, Any], path: Path | str) -> Path:
    target = Path(path)
    target.write_text(serialize_release_manifest(document), encoding="utf-8", newline="\n")
    return target


def build_sha256sums(assets_dir: Path | str, names: list[str] | tuple[str, ...]) -> str:
    root = Path(assets_dir)
    return "".join(f"{sha256_file(root / name)}  {name}\n" for name in sorted(names))


def release_asset_url(release_tag: str, asset_name: str) -> str:
    tag = validate_release_tag(release_tag)
    if asset_name not in {MANIFEST_FILENAME, "SHA256SUMS", *ASSET_NAMES.values()}:
        raise ReleaseManifestError("RELEASE_SOURCE_URL_MISMATCH", "Release asset name is not allow-listed.")
    return f"{REPOSITORY_URL}/releases/download/{tag}/{asset_name}"


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_project_version_from_value(value: Any) -> str:
    from .application_version import validate_project_version

    return validate_project_version(value)


def _load_document(value: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    if not isinstance(encoded, bytes) or len(encoded) > MANIFEST_MAX_BYTES:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest response exceeds the size limit.")
    try:
        loaded = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest JSON is invalid.") from exc
    if not isinstance(loaded, dict):
        raise ReleaseManifestError("RELEASE_MANIFEST_INVALID", "Manifest root must be an object.")
    return loaded


def _validate_rfc3339(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp must use RFC3339 UTC form.")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone.")
