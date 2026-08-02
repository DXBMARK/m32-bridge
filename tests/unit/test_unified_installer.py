from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest


COMMIT = "a" * 40


def _archive(path: Path, version: str = "1.2.3", *, unsafe_name: str | None = None) -> Path:
    with tarfile.open(path, "w:gz") as handle:
        entries = {
            "m32-bridge/pyproject.toml": f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n".encode(),
            "m32-bridge/src/m32_bridge/__init__.py": b"",
        }
        if unsafe_name:
            entries[unsafe_name] = b"escape"
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))
    return path


def _manifest(archive: Path, version: str = "1.2.3") -> dict:
    from m32_bridge.installer.release_manifest import sha256_file

    tag = f"v{version}"
    names = {
        "posix_source": "m32-bridge-source.tar.gz",
        "windows_source": "m32-bridge-source.zip",
        "posix_installer": "install.sh",
        "windows_installer": "install.ps1",
    }
    return {
        "schema_version": "1",
        "product": "X32-Bridge MCP",
        "application_version": version,
        "release_tag": tag,
        "release_channel": "prerelease" if "-" in version else "stable",
        "source_commit": COMMIT,
        "repository_url": "https://github.com/DXBMARK/m32-bridge",
        "published_at": "2026-08-02T00:00:00Z",
        "assets": {
            key: {
                "name": name,
                "url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/{name}",
                "sha256": sha256_file(archive) if key == "posix_source" else "b" * 64,
            }
            for key, name in names.items()
        },
    }


def _resolution(version: str = "1.2.3"):
    from m32_bridge.installer.release_selection import ReleaseResolution

    tag = f"v{version}"
    return ReleaseResolution(tag, "version", "prerelease" if "-" in version else "stable", tag, COMMIT, COMMIT, "github_release_asset", "2026-08-02T00:00:00Z", f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-release.json")


def test_release_archive_checksum_verified_before_extract(tmp_path):
    from m32_bridge.installer.release_download import preflight_release_install

    archive = _archive(tmp_path / "m32-bridge-source.tar.gz")
    result = preflight_release_install(_resolution(), platform="posix", manifest_document=_manifest(archive), archive_path=archive, staging_parent=tmp_path / "stage")
    assert result.archive_checksum_status == "verified"
    assert result.staged_application_version == "1.2.3"


def test_checksum_mismatch_fails_before_materialization(tmp_path):
    from m32_bridge.installer.release_download import ReleasePreflightError, preflight_release_install

    archive = _archive(tmp_path / "m32-bridge-source.tar.gz")
    manifest = _manifest(archive)
    manifest["assets"]["posix_source"]["sha256"] = "c" * 64
    with pytest.raises(ReleasePreflightError, match="RELEASE_ARCHIVE_CHECKSUM_MISMATCH"):
        preflight_release_install(_resolution(), platform="posix", manifest_document=manifest, archive_path=archive, staging_parent=tmp_path / "stage")


@pytest.mark.parametrize("name", ["../escape", "/absolute"])
def test_archive_path_traversal_and_absolute_paths_rejected(name, tmp_path):
    from m32_bridge.installer.release_download import ReleasePreflightError, safe_extract_archive

    archive = _archive(tmp_path / "m32-bridge-source.tar.gz", unsafe_name=name)
    with pytest.raises(ReleasePreflightError, match="RELEASE_ARCHIVE_UNSAFE"):
        safe_extract_archive(archive, tmp_path / "stage")


def test_release_tag_manifest_and_staged_version_must_match(tmp_path):
    from m32_bridge.installer.release_download import ReleasePreflightError, preflight_release_install

    archive = _archive(tmp_path / "m32-bridge-source.tar.gz", version="1.2.4")
    with pytest.raises(ReleasePreflightError, match="RELEASE_VERSION_MISMATCH"):
        preflight_release_install(_resolution(), platform="posix", manifest_document=_manifest(archive), archive_path=archive, staging_parent=tmp_path / "stage")


def test_preflight_failure_never_calls_apply_user_local_install(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    planned = script_runtime.build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path / "home",
        uv_state=RuntimeManagerState(uv_status="present"),
        staged_source_root=Path.cwd(),
    )
    planned["_source_root"] = str(tmp_path / "missing")
    uv = tmp_path / "uv"
    uv.write_text("#!/bin/sh\n", encoding="utf-8")
    uv.chmod(0o755)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: pytest.fail("materialization called"))
    result = script_runtime.perform_apply_install("posix", planned, uv_bin=str(uv))
    assert result["ok"] is False
    assert result["runtime_info"]["application_runtime_ready"] is False
    assert "runtime_handoff" not in result


def test_local_install_preflight_performs_no_network(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.runtime_manager import RuntimeManagerState

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: pytest.fail("network called"))
    planned = script_runtime.build_install_result(surface="posix", platform="linux", home=tmp_path, uv_state=RuntimeManagerState(uv_status="present"), staged_source_root=Path.cwd())
    script_runtime._prepare_install_preflight("posix", planned)
    assert planned["install_source"] == "local_checkout"
    assert planned["identity_status"] == "validated"
