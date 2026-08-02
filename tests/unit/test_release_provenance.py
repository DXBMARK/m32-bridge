from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest


COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def _result(tmp_path: Path, *, surface: str = "posix", **overrides: object) -> dict[str, object]:
    requested_tag = str(overrides.get("release_tag") or "v0.1.0")
    fixture_version = str(overrides.pop("_fixture_version", requested_tag[1:]))
    if surface == "windows":
        root = tmp_path / "M32Bridge"
        app = root / "app"
        launcher = root / "bin" / "m32-bridge.cmd"
        platform = "windows_powershell"
    else:
        app = tmp_path / ".m32-bridge" / "app"
        launcher = tmp_path / ".local" / "bin" / "m32-bridge"
        platform = "linux"
    app.mkdir(parents=True, exist_ok=True)
    (app / "pyproject.toml").write_text(
        f"[project]\nname='m32-mcp-bridge'\nversion='{fixture_version}'\n",
        encoding="utf-8",
    )
    launcher.parent.mkdir(parents=True, exist_ok=True)
    values: dict[str, object] = {
        "tty_mode": "runtime",
        "app_path": str(app),
        "launcher_path": str(launcher),
        "platform": platform,
        "architecture": "x86_64",
        "target_version": None,
        "application_version": fixture_version,
        "application_version_source": "installed_pyproject",
        "install_source": "github_release_asset",
        "selection": requested_tag,
        "release_channel": "prerelease" if "-" in requested_tag[1:] else "stable",
        "release_tag": "v0.1.0",
        "source_commit": COMMIT_A,
        "source_ref": COMMIT_A,
        "source_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{requested_tag}/m32-bridge-source.{'zip' if surface == 'windows' else 'tar.gz'}",
        "source_archive_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{requested_tag}/m32-bridge-source.{'zip' if surface == 'windows' else 'tar.gz'}",
        "source_archive_sha256": "1" * 64,
        "installer_asset_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{requested_tag}/{'install.ps1' if surface == 'windows' else 'install.sh'}",
        "installer_asset_sha256": "2" * 64,
        "manifest_status": "validated",
        "manifest_schema_version": "1",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("tag", ["v0.1.0", "v9.15.23"])
def test_release_tag_v0_1_0_is_valid(tag):
    from m32_bridge.installer.install_metadata import validate_release_tag

    assert validate_release_tag(tag) == tag


def test_release_tag_large_version_is_valid():
    from m32_bridge.installer.install_metadata import validate_release_tag

    assert validate_release_tag("v9.15.23") == "v9.15.23"


@pytest.mark.parametrize("tag", ["v1.0.0-rc.1", "v1.0.0-alpha", "v1.0.0-alpha.1", "v1.0.0-beta.2"])
def test_release_prerelease_tag_is_valid(tag):
    from m32_bridge.installer.install_metadata import validate_release_tag

    assert validate_release_tag(tag) == tag


def test_release_alpha_and_beta_tags_are_valid():
    from m32_bridge.installer.install_metadata import validate_release_tag

    assert all(validate_release_tag(tag) == tag for tag in ("v1.0.0-alpha.1", "v1.0.0-beta.2"))


@pytest.mark.parametrize(
    "tag",
    [
        "1.0.0",
        "v01.2.3",
        "v1.02.3",
        "v1.0.0/next",
        "v1.0.0 next",
        "v1.0.0\n",
        "v1.0.0\x1b[2J",
        "v1.0.0%2fnext",
        "refs/tags/v1.0.0",
    ],
)
def test_invalid_release_tags_are_rejected(tag):
    from m32_bridge.installer.install_metadata import validate_release_tag

    with pytest.raises(ValueError):
        validate_release_tag(tag)


def test_release_tag_without_v_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("1.0.0")


def test_release_tag_with_leading_zero_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("v01.2.3")


def test_release_tag_with_slash_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("v1.0.0/x")


def test_release_tag_with_whitespace_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("v1.0.0 x")


def test_release_tag_with_control_character_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("v1.0.0\x1b")


def test_release_tag_with_percent_encoding_is_rejected():
    from m32_bridge.installer.install_metadata import validate_release_tag
    with pytest.raises(ValueError):
        validate_release_tag("v1.0.0%2fnext")


def test_release_tag_matches_application_version():
    from m32_bridge.installer.install_metadata import version_from_release_tag
    assert version_from_release_tag("v0.1.0") == "0.1.0"


def test_prerelease_tag_matches_application_version():
    from m32_bridge.installer.install_metadata import version_from_release_tag
    assert version_from_release_tag("v1.0.0-rc.1") == "1.0.0-rc.1"


def test_release_version_mismatch_is_rejected(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    with pytest.raises(ValueError, match="RELEASE_VERSION_MISMATCH"):
        build_install_metadata("posix", _result(tmp_path, _fixture_version="0.1.1"))


def test_release_source_commit_requires_full_40_hex(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    with pytest.raises(ValueError, match="RELEASE_SOURCE_COMMIT_INVALID"):
        build_install_metadata("posix", _result(tmp_path, source_commit="abc1234", source_ref="abc1234"))


def test_release_source_commit_normalizes_uppercase(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    upper = "A" * 40
    metadata = build_install_metadata(
        "posix",
        _result(tmp_path, source_commit=upper, source_ref=upper, source_url=f"https://github.com/DXBMARK/m32-bridge/archive/{upper}.tar.gz"),
    )
    assert metadata["source_commit"] == COMMIT_A
    assert metadata["source_ref"] == COMMIT_A


def test_release_short_commit_is_rejected_in_release_mode(tmp_path):
    test_release_source_commit_requires_full_40_hex(tmp_path)


def test_release_source_ref_must_equal_source_commit(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    with pytest.raises(ValueError, match="RELEASE_COMMIT_MISMATCH"):
        build_install_metadata("posix", _result(tmp_path, source_ref=COMMIT_B))


def test_release_commit_with_non_hex_character_is_rejected(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    with pytest.raises(ValueError, match="RELEASE_SOURCE_COMMIT_INVALID"):
        build_install_metadata("posix", _result(tmp_path, source_commit="g" * 40, source_ref="g" * 40))


def test_release_posix_urls_generated_from_commit():
    from m32_bridge.installer.install_metadata import build_official_release_urls
    urls = build_official_release_urls("posix", COMMIT_A)
    assert urls == {
        "repository_url": "https://github.com/DXBMARK/m32-bridge",
        "source_archive_url": f"https://github.com/DXBMARK/m32-bridge/archive/{COMMIT_A}.tar.gz",
        "raw_installer_url": f"https://raw.githubusercontent.com/DXBMARK/m32-bridge/{COMMIT_A}/scripts/install.sh",
        "allowed_redirect_url": f"https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/{COMMIT_A}",
    }


def test_release_windows_urls_generated_from_commit():
    from m32_bridge.installer.install_metadata import build_official_release_urls
    urls = build_official_release_urls("windows", COMMIT_B)
    assert urls["source_archive_url"].endswith(f"/{COMMIT_B}.zip")
    assert urls["raw_installer_url"].endswith(f"/{COMMIT_B}/scripts/install.ps1")
    assert urls["allowed_redirect_url"].endswith(f"/zip/{COMMIT_B}")


def test_release_urls_do_not_contain_release_tag():
    from m32_bridge.installer.install_metadata import build_official_release_urls
    assert "v0.1.0" not in json.dumps(build_official_release_urls("posix", COMMIT_A))


def test_release_urls_change_when_commit_changes():
    from m32_bridge.installer.install_metadata import build_official_release_urls
    assert build_official_release_urls("posix", COMMIT_A) != build_official_release_urls("posix", COMMIT_B)


def test_release_urls_do_not_require_code_change_for_new_version():
    from m32_bridge.installer.install_metadata import build_official_release_urls, version_from_release_tag
    for tag in ("v0.1.0", "v9.15.23"):
        assert version_from_release_tag(tag) == tag[1:]
        assert build_official_release_urls("posix", COMMIT_A)["source_archive_url"].endswith(f"/{COMMIT_A}.tar.gz")


def test_release_metadata_contains_application_version_tag_and_commit(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    metadata = build_install_metadata("posix", _result(tmp_path))
    assert metadata["application_version"] == "0.1.0"
    assert metadata["release_tag"] == "v0.1.0"
    assert metadata["source_commit"] == COMMIT_A
    assert metadata["source_ref"] == COMMIT_A
    assert metadata["source_archive_url"].endswith("/v0.1.0/m32-bridge-source.tar.gz")
    assert metadata["installer_asset_url"].endswith("/v0.1.0/install.sh")
    assert "allowed_redirect_url" not in metadata


def test_non_release_metadata_does_not_invent_release_tag(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    metadata = build_install_metadata("posix", _result(tmp_path, release_tag=None, source_commit=None, source_ref="abcdef1", source_url="https://github.com/DXBMARK/m32-bridge/archive/abcdef1.tar.gz"))
    assert "release_tag" not in metadata
    assert "source_commit" not in metadata


def test_custom_source_cannot_become_official_by_providing_release_tag(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    metadata = build_install_metadata("posix", _result(tmp_path, source_url="https://example.com/source.tar.gz", source_archive_url="https://example.com/source.tar.gz"))
    assert metadata["install_source"] == "custom"
    assert "repository_url" not in metadata
    assert "release_tag" not in metadata


def test_release_metadata_does_not_store_credentials(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    metadata = build_install_metadata("posix", _result(tmp_path))
    assert not any(word in json.dumps(metadata).lower() for word in ("authorization", "cookie", "github_token"))


def test_release_status_displays_version_tag_and_full_commit(monkeypatch, tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status
    from m32_bridge.installer.tty_app import render_runtime_status_panel
    result = _result(tmp_path)
    write_install_metadata(build_install_metadata("posix", result), app_path=result["app_path"])
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.0")
    text = render_runtime_status_panel(build_runtime_status(dict(result)))
    assert "v0.1.0" in text and COMMIT_A in text and "0.1.0" in text


def test_release_dashboard_displays_version_and_tag_compactly(monkeypatch, tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status
    from m32_bridge.installer.tty_app import render_full_screen, strip_ansi
    result = _result(tmp_path)
    write_install_metadata(build_install_metadata("posix", result), app_path=result["app_path"])
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.0")
    build_runtime_status(result)
    text = strip_ansi(render_full_screen("posix", result, dry_run=False, color=False, width=90, height=20))
    assert "Version 0.1.0 · Release v0.1.0" in text


def test_non_release_status_displays_release_tag_not_available(monkeypatch, tmp_path):
    from m32_bridge.installer.runtime_status import build_runtime_status
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.0")
    assert build_runtime_status(dict(_result(tmp_path)))["installation_source"]["release_tag"] == "not_available"


def test_stale_metadata_is_not_attributed_to_new_application_version(monkeypatch, tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status
    old = _result(tmp_path)
    write_install_metadata(build_install_metadata("posix", old), app_path=old["app_path"])
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.1")
    payload = build_runtime_status(dict(old))
    assert payload["application"]["install_metadata_status"] == "metadata_stale"
    assert payload["installation_source"]["release_tag"] == "not_available"
    assert payload["installation_source"]["source_commit"] == "not_available"
    assert payload["application"]["version"] == "0.1.1"


def test_stale_metadata_disables_source_refresh(monkeypatch, tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status
    old = _result(tmp_path)
    write_install_metadata(build_install_metadata("posix", old), app_path=old["app_path"])
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.1")
    payload = build_runtime_status(dict(old), refresh=True, source_checker=lambda *_: pytest.fail("network"))
    assert payload["safety"]["internet_source_refresh"] == "not_run_metadata_stale"


def test_release_status_refresh_uses_exact_four_release_asset_targets(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    from m32_bridge.installer.runtime_status import refresh_official_source_status
    metadata = build_install_metadata("posix", _result(tmp_path))
    calls: list[str] = []
    refresh_official_source_status(metadata, platform_data={"os": "Linux"}, checker=lambda url, _: calls.append(url) or "reachable")
    assert calls == [
        "https://github.com/",
        "https://github.com/DXBMARK/m32-bridge",
        "https://github.com/DXBMARK/m32-bridge/releases/download/v0.1.0/install.sh",
        "https://github.com/DXBMARK/m32-bridge/releases/download/v0.1.0/m32-bridge-source.tar.gz",
    ]


def test_release_assets_do_not_reuse_commit_codeload_allowlist(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    from m32_bridge.installer.runtime_status import _redirect_allowed_urls
    metadata = build_install_metadata("posix", _result(tmp_path))
    assert _redirect_allowed_urls(metadata, archive_url=metadata["source_archive_url"]) == frozenset()


@pytest.mark.parametrize("destination", [f"https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/{COMMIT_B}", "https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/refs/tags/v0.1.0", f"https://codeload.github.com/OTHER/m32-bridge/tar.gz/{COMMIT_A}", "https://127.0.0.1/source"])
def test_release_codeload_unsafe_destinations_are_rejected(tmp_path, destination):
    from m32_bridge.installer.install_metadata import build_install_metadata
    from m32_bridge.installer.runtime_status import _canonical_codeload_url, _redirect_allowed_urls
    metadata = build_install_metadata("posix", _result(tmp_path))
    assert (_canonical_codeload_url(destination) or destination) not in _redirect_allowed_urls(metadata, archive_url=metadata["source_archive_url"])


def test_multiple_release_versions_use_identical_production_code_path(tmp_path):
    from m32_bridge.installer.install_metadata import build_install_metadata
    for index, tag in enumerate(("v0.1.0", "v0.1.1", "v1.0.0", "v9.15.23", "v2.0.0-rc.1")):
        commit = f"{index + 1:x}" * 40
        metadata = build_install_metadata("posix", _result(tmp_path / str(index), target_version=tag[1:], release_tag=tag, source_commit=commit, source_ref=commit, source_url=f"https://github.com/DXBMARK/m32-bridge/archive/{commit}.tar.gz"))
        assert metadata["release_tag"] == tag
        assert metadata["source_commit"] == commit


def test_production_source_contains_no_hardcoded_release_tags():
    import m32_bridge.installer.install_metadata as install_metadata
    import m32_bridge.installer.runtime_status as runtime_status
    production = inspect.getsource(install_metadata) + inspect.getsource(runtime_status)
    for tag in ("v0.1.0", "v0.1.1", "v1.0.0", "v9.15.23", "v2.0.0-rc.1"):
        assert tag not in production


def _planned_release(tmp_path: Path, *, version: str, tag: str, commit: str) -> dict[str, object]:
    from m32_bridge.installer.runtime_manager import RuntimeManagerState
    from m32_bridge.installer.script_runtime import build_install_result

    planned = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=False,
        home=tmp_path,
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    app = Path(str(planned["app_path"]))
    app.mkdir(parents=True, exist_ok=True)
    (app / "pyproject.toml").write_text(f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n", encoding="utf-8")
    planned.update(
        application_version=version,
        application_version_source="installed_pyproject",
        install_source="github_release_asset",
        selection=tag,
        requested_selection=tag,
        release_channel="prerelease" if "-" in tag[1:] else "stable",
        release_tag=tag,
        source_commit=commit,
        source_ref=commit,
        source_archive_url=f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-source.tar.gz",
        source_archive_sha256="1" * 64,
        installer_asset_url=f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/install.sh",
        installer_asset_sha256="2" * 64,
        manifest_status="validated",
        manifest_schema_version="1",
        _source_root=str(app),
    )
    return planned


def _release_snapshot(planned: dict[str, object], *, version: str, tag: str, commit: str) -> dict[str, object]:
    return {
        **planned,
        "application_version": version,
        "application_version_source": "installed_pyproject",
        "selection": tag,
        "release_channel": "prerelease" if "-" in tag[1:] else "stable",
        "release_tag": tag,
        "source_commit": commit,
        "source_ref": commit,
        "source_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-source.tar.gz",
        "source_archive_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-source.tar.gz",
        "installer_asset_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/install.sh",
    }


def _set_installed_version(planned: dict[str, object], version: str) -> None:
    Path(str(planned["app_path"]), "pyproject.toml").write_text(
        f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n",
        encoding="utf-8",
    )


def test_release_update_replaces_metadata_atomically(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.install_metadata import build_install_metadata, read_install_metadata, write_install_metadata

    planned = _planned_release(tmp_path, version="0.1.1", tag="v0.1.1", commit=COMMIT_B)
    old = _release_snapshot(planned, version="0.1.0", tag="v0.1.0", commit=COMMIT_A)
    _set_installed_version(planned, "0.1.0")
    write_install_metadata(build_install_metadata("posix", old), app_path=planned["app_path"])
    _set_installed_version(planned, "0.1.1")
    monkeypatch.setattr(script_runtime, "_prepare_install_preflight", lambda *_args, **_kwargs: planned)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: None)
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    applied = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    loaded = read_install_metadata(Path(str(applied["app_path"])).parent / "install-metadata.json")
    assert loaded["data"]["application_version"] == "0.1.1"
    assert loaded["data"]["release_tag"] == "v0.1.1"
    assert loaded["data"]["source_commit"] == COMMIT_B
    assert list(Path(str(applied["app_path"])).parent.glob(".install-metadata.json.*.tmp")) == []


def test_release_update_removes_old_tag_and_commit(monkeypatch, tmp_path):
    test_release_update_replaces_metadata_atomically(monkeypatch, tmp_path)
    text = (tmp_path / ".m32-bridge" / "install-metadata.json").read_text(encoding="utf-8")
    assert "v0.1.0" not in text and COMMIT_A not in text


def test_failed_update_before_readiness_preserves_previous_metadata(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata

    planned = _planned_release(tmp_path, version="0.1.1", tag="v0.1.1", commit=COMMIT_B)
    old = _release_snapshot(planned, version="0.1.0", tag="v0.1.0", commit=COMMIT_A)
    _set_installed_version(planned, "0.1.0")
    path = write_install_metadata(build_install_metadata("posix", old), app_path=planned["app_path"])
    _set_installed_version(planned, "0.1.1")
    monkeypatch.setattr(script_runtime, "_prepare_install_preflight", lambda *_args, **_kwargs: planned)
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("apply failed")))
    failed = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    assert failed["ok"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["release_tag"] == "v0.1.0"


def test_successful_update_with_metadata_failure_marks_previous_metadata_stale(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.install_metadata import build_install_metadata, write_install_metadata
    from m32_bridge.installer.runtime_status import build_runtime_status

    planned = _planned_release(tmp_path, version="0.1.1", tag="v0.1.1", commit=COMMIT_B)
    old = _release_snapshot(planned, version="0.1.0", tag="v0.1.0", commit=COMMIT_A)
    _set_installed_version(planned, "0.1.0")
    write_install_metadata(build_install_metadata("posix", old), app_path=planned["app_path"])
    _set_installed_version(planned, "0.1.1")
    monkeypatch.setattr(script_runtime, "_prepare_install_preflight", lambda *_args, **_kwargs: planned)
    monkeypatch.setattr(script_runtime, "_apply_user_local_install", lambda *args, **kwargs: None)
    monkeypatch.setattr(script_runtime, "_resolve_uv_executable", lambda *args, **kwargs: "/opt/uv")
    monkeypatch.setattr(script_runtime, "write_install_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    applied = script_runtime.perform_apply_install("posix", planned, uv_bin="/opt/uv")
    monkeypatch.setattr("m32_bridge.installer.runtime_status._application_version", lambda: "0.1.1")
    payload = build_runtime_status(applied)
    assert applied["ok"] is True
    assert applied["runtime_info"]["install_metadata_status"] == "write_failed"
    assert payload["application"]["install_metadata_status"] == "metadata_stale"
    assert payload["installation_source"]["release_tag"] == "not_available"


def test_release_cli_arguments_override_environment(monkeypatch, capsys):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.release_selection import ReleaseResolution

    captured: dict[str, object] = {}
    monkeypatch.setenv("M32_INSTALL_VERSION", "v9.9.9")
    monkeypatch.setattr(script_runtime.ReleaseResolver, "resolve", lambda _self, selection: ReleaseResolution(selection.requested_selection, "version", "stable", selection.release_tag, COMMIT_B, COMMIT_B, "github_release_asset"))
    monkeypatch.setattr(script_runtime, "build_install_result", lambda **kwargs: captured.update(kwargs) or {"ok": True, "installer_can_continue": True})
    assert script_runtime.main(["--surface", "posix", "--dry-run", "--json", "--version", "v1.2.3"]) == 0
    capsys.readouterr()
    assert captured["selection"].release_tag == "v1.2.3"
    assert captured["release_resolution"].source_commit == COMMIT_B


def test_release_environment_is_used_when_cli_arguments_absent(monkeypatch, capsys):
    from m32_bridge.installer import script_runtime
    from m32_bridge.installer.release_selection import ReleaseResolution

    captured: dict[str, object] = {}
    monkeypatch.setenv("M32_INSTALL_VERSION", "v1.2.3")
    monkeypatch.setattr(script_runtime.ReleaseResolver, "resolve", lambda _self, selection: ReleaseResolution(selection.requested_selection, "version", "stable", selection.release_tag, COMMIT_A, COMMIT_A, "github_release_asset"))
    monkeypatch.setattr(script_runtime, "build_install_result", lambda **kwargs: captured.update(kwargs) or {"ok": True, "installer_can_continue": True})
    assert script_runtime.main(["--surface", "posix", "--dry-run", "--json"]) == 0
    capsys.readouterr()
    assert captured["selection"].release_tag == "v1.2.3"
    assert captured["release_resolution"].source_commit == COMMIT_A


def test_release_scripts_pass_release_metadata():
    root = Path(__file__).resolve().parents[2]
    posix = (root / "scripts" / "install.sh").read_text(encoding="utf-8")
    windows = (root / "scripts" / "install.ps1").read_text(encoding="utf-8")
    for name in ("M32_INSTALL_VERSION", "M32_INSTALL_CHANNEL", "M32_INSTALL_REF", "M32_INSTALL_LOCAL"):
        assert name in posix and name in windows
    assert all(flag in posix for flag in ("--version", "--channel", "--ref", "--local"))
    assert all(flag in windows for flag in ("--version", "--channel", "--ref", "--local"))
