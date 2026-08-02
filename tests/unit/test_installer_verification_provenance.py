from __future__ import annotations

from pathlib import Path

from m32_bridge.installer import verification
from m32_bridge.installer.install_metadata import (
    build_install_metadata,
    build_official_release_urls,
    write_install_metadata,
)
from m32_bridge.installer.runtime_manager import (
    RuntimeManagerState,
)


VERSION = "0.1.0"
COMMIT = "a" * 40


def _installed_paths(
    tmp_path: Path,
) -> tuple[Path, Path]:
    app = tmp_path / ".m32-bridge" / "app"
    launcher = (
        tmp_path
        / ".local"
        / "bin"
        / "m32-bridge"
    )

    app.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)

    (app / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'm32-mcp-bridge'\n"
        f"version = '{VERSION}'\n",
        encoding="utf-8",
    )

    launcher.write_text(
        "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )

    return app, launcher


def _patch_local_dependencies(monkeypatch):
    monkeypatch.setattr(
        verification,
        "detect_uv_status",
        lambda: RuntimeManagerState(
            uv_status="present"
        ),
    )

    monkeypatch.setattr(
        verification,
        "inspect_runtime",
        lambda **kwargs: {
            "uv_detected": True,
            "managed_python_detected": True,
            "python_version": "3.13.14",
            "python_path": (
                "/tmp/app/.venv/bin/python3"
            ),
            "system_python_version": "3.8.2",
            "system_python_path": "/usr/bin/python3",
            "system_python_used": False,
            "system_python_modified": False,
        },
    )

    monkeypatch.setattr(
        verification,
        "detect_ide_clients",
        lambda **kwargs: [],
    )

    monkeypatch.setattr(
        verification,
        "render_mcp_guidance",
        lambda **kwargs: {
            "ok": True,
            "status": "MCP_GUIDANCE_READY",
            "version": kwargs["version"],
            "command": "m32-bridge",
            "args": ["mcp-server"],
            "manual_copy_only": True,
            "console_probe": "not_run",
            "network_scan": False,
            "osc_writes_sent": 0,
        },
    )


def _render(monkeypatch, tmp_path: Path) -> dict:
    _patch_local_dependencies(monkeypatch)

    return verification.render_post_install_verification(
        environ={
            "SHELL": "/bin/bash",
            "M32_BRIDGE_INSTALLED_RUNTIME": "1",
        },
        home=tmp_path,
    )


def _write_metadata(
    app: Path,
    launcher: Path,
    *,
    install_source: str,
    selection: str,
    release: bool = False,
) -> None:
    urls = build_official_release_urls(
        "posix",
        COMMIT,
    )

    result = {
        "app_path": str(app),
        "launcher_path": str(launcher),
        "application_version": VERSION,
        "application_version_source": (
            "staged_pyproject"
        ),
        "install_source": install_source,
        "selection": selection,
        "source_ref": (
            COMMIT
            if install_source != "local_checkout"
            else "not_available"
        ),
        "source_commit": (
            COMMIT
            if install_source != "local_checkout"
            else None
        ),
        "platform": "linux",
        "architecture": "x86_64",
    }

    if install_source in {
        "github_commit_archive",
        "github_main",
    }:
        result["source_url"] = (
            urls["source_archive_url"]
        )
        result["source_archive_url"] = (
            urls["source_archive_url"]
        )

    if release:
        tag = f"v{VERSION}"
        result.update(
            {
                "install_source": (
                    "github_release_asset"
                ),
                "selection": "stable",
                "release_tag": tag,
                "release_channel": "stable",
                "source_ref": COMMIT,
                "source_commit": COMMIT,
                "source_archive_url": (
                    "https://github.com/"
                    "DXBMARK/m32-bridge/"
                    f"releases/download/{tag}/"
                    "m32-bridge-source.tar.gz"
                ),
                "source_url": (
                    "https://github.com/"
                    "DXBMARK/m32-bridge/"
                    f"releases/download/{tag}/"
                    "m32-bridge-source.tar.gz"
                ),
                "installer_asset_url": (
                    "https://github.com/"
                    "DXBMARK/m32-bridge/"
                    f"releases/download/{tag}/"
                    "install.sh"
                ),
                "source_archive_sha256": "a" * 64,
                "installer_asset_sha256": "b" * 64,
                "manifest_status": "validated",
                "manifest_schema_version": "1",
            }
        )

    metadata = build_install_metadata(
        "posix",
        result,
        installed_at="2026-08-03T00:00:00+00:00",
    )

    write_install_metadata(
        metadata,
        app_path=app,
    )


def test_commit_install_reports_exact_metadata_provenance(
    monkeypatch,
    tmp_path,
):
    app, launcher = _installed_paths(tmp_path)

    _write_metadata(
        app,
        launcher,
        install_source="github_commit_archive",
        selection="commit",
    )

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_metadata_status"]
        == "metadata_valid"
    )
    assert payload["provenance_trusted"] is True
    assert (
        payload["install_source"]
        == "github_commit_archive"
    )
    assert payload["selection"] == "commit"
    assert payload["source_ref"] == COMMIT
    assert payload["source_commit"] == COMMIT
    assert payload["release_tag"] == "not_available"
    assert payload["version"] == VERSION
    assert payload["application_version"] == VERSION
    assert (
        payload["mcp_guidance"]["version"]
        == VERSION
    )

    assert payload["console_probe_attempted"] is False
    assert payload["scan_attempted"] is False
    assert payload["osc_writes_sent"] == 0


def test_release_install_reports_release_identity(
    monkeypatch,
    tmp_path,
):
    app, launcher = _installed_paths(tmp_path)

    _write_metadata(
        app,
        launcher,
        install_source="github_release_asset",
        selection="stable",
        release=True,
    )

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_source"]
        == "github_release_asset"
    )
    assert payload["selection"] == "stable"
    assert payload["release_channel"] == "stable"
    assert payload["release_tag"] == f"v{VERSION}"
    assert payload["source_commit"] == COMMIT
    assert payload["provenance_trusted"] is True


def test_local_checkout_is_reported_only_from_valid_metadata(
    monkeypatch,
    tmp_path,
):
    app, launcher = _installed_paths(tmp_path)

    _write_metadata(
        app,
        launcher,
        install_source="local_checkout",
        selection="local",
    )

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_source"]
        == "local_checkout"
    )
    assert payload["selection"] == "local"
    assert payload["provenance_trusted"] is True
    assert (
        payload["install_metadata_status"]
        == "metadata_valid"
    )


def test_missing_metadata_does_not_invent_local_checkout(
    monkeypatch,
    tmp_path,
):
    _installed_paths(tmp_path)

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_metadata_status"]
        == "metadata_missing"
    )
    assert payload["provenance_trusted"] is False
    assert payload["install_source"] == "not_available"
    assert payload["selection"] == "not_available"
    assert payload["source_commit"] == "not_available"
    assert payload["version"] == VERSION


def test_invalid_metadata_does_not_invent_provenance(
    monkeypatch,
    tmp_path,
):
    app, _launcher = _installed_paths(tmp_path)

    metadata_path = (
        app.parent
        / "install-metadata.json"
    )
    metadata_path.write_text(
        "{not-json",
        encoding="utf-8",
    )

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_metadata_status"]
        == "metadata_invalid"
    )
    assert payload["provenance_trusted"] is False
    assert payload["install_source"] == "not_available"
    assert payload["release_tag"] == "not_available"
    assert payload["source_commit"] == "not_available"


def test_stale_metadata_is_not_trusted(
    monkeypatch,
    tmp_path,
):
    app, launcher = _installed_paths(tmp_path)

    _write_metadata(
        app,
        launcher,
        install_source="github_commit_archive",
        selection="commit",
    )

    (app / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'm32-mcp-bridge'\n"
        "version = '0.1.1'\n",
        encoding="utf-8",
    )

    payload = _render(monkeypatch, tmp_path)

    assert (
        payload["install_metadata_status"]
        == "metadata_stale"
    )
    assert payload["provenance_trusted"] is False
    assert payload["install_source"] == "not_available"
    assert payload["source_commit"] == "not_available"
    assert payload["version"] == "0.1.1"
