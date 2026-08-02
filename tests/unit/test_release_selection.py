from __future__ import annotations

from pathlib import Path

import pytest


COMMIT = "a" * 40


def _checkout(root: Path) -> Path:
    (root / "src" / "m32_bridge").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nversion='1.2.3'\n", encoding="utf-8")
    return root


def test_standalone_default_selects_latest_stable(tmp_path):
    from m32_bridge.installer.release_selection import resolve_installation_selection

    selected = resolve_installation_selection(environ={}, source_root=tmp_path)
    assert (selected.kind, selected.requested_selection) == ("stable", "stable")


def test_local_checkout_default_selects_local(tmp_path):
    from m32_bridge.installer.release_selection import resolve_installation_selection

    assert resolve_installation_selection(environ={}, source_root=_checkout(tmp_path)).kind == "local"


def test_explicit_stable_overrides_local_autodetection(tmp_path):
    from m32_bridge.installer.release_selection import resolve_installation_selection

    assert resolve_installation_selection(channel="stable", environ={}, source_root=_checkout(tmp_path)).kind == "stable"


def test_specific_version_selects_release_by_tag():
    from m32_bridge.installer.release_selection import resolve_installation_selection

    selected = resolve_installation_selection(version="v9.15.23", environ={})
    assert selected.release_tag == "v9.15.23" and selected.install_source == "github_release_asset"


def test_prerelease_main_commit_and_local_modes():
    from m32_bridge.installer.release_selection import resolve_installation_selection

    assert resolve_installation_selection(channel="prerelease", environ={}).kind == "prerelease"
    assert resolve_installation_selection(channel="main", environ={}).install_source == "github_main"
    assert resolve_installation_selection(ref=COMMIT, environ={}).install_source == "github_commit_archive"
    assert resolve_installation_selection(local=True, environ={}).install_source == "local_checkout"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"version": "v1.2.3", "channel": "stable"},
        {"version": "v1.2.3", "ref": COMMIT},
        {"version": "v1.2.3", "local": True},
        {"ref": COMMIT, "local": True},
    ],
)
def test_public_selection_conflicts_rejected(kwargs):
    from m32_bridge.installer.release_selection import ReleaseSelectionError, resolve_installation_selection

    with pytest.raises(ReleaseSelectionError, match="INSTALL_SELECTION_CONFLICT"):
        resolve_installation_selection(environ={}, **kwargs)


def test_cli_priority_over_environment():
    from m32_bridge.installer.release_selection import resolve_installation_selection

    selected = resolve_installation_selection(channel="main", environ={"M32_INSTALL_VERSION": "v1.2.3"})
    assert selected.kind == "main" and selected.origin == "cli"


def test_environment_priority_over_local_autodetection(tmp_path):
    from m32_bridge.installer.release_selection import resolve_installation_selection

    selected = resolve_installation_selection(environ={"M32_INSTALL_CHANNEL": "stable"}, source_root=_checkout(tmp_path))
    assert selected.kind == "stable" and selected.origin == "environment"


def test_latest_stable_specific_prerelease_and_commit_endpoints():
    from m32_bridge.installer.release_selection import GITHUB_API_ROOT, ReleaseResolver, resolve_installation_selection

    calls = []

    def get(url, _timeout, _limit):
        calls.append(url)
        if "/commits/" in url:
            return {"url": url, "sha": COMMIT}
        if url.endswith("/releases/latest"):
            return _release("v1.2.3", prerelease=False)
        if "/releases/tags/" in url:
            return _release("v1.2.3", prerelease=False)
        return [_release("v2.0.0-rc.1", prerelease=True), _release("v1.2.3", prerelease=False)]

    resolver = ReleaseResolver(json_get=get)
    resolver.resolve(resolve_installation_selection(channel="stable", environ={}))
    assert calls[0] == f"{GITHUB_API_ROOT}/releases/latest"
    calls.clear()
    resolver.resolve(resolve_installation_selection(version="v1.2.3", environ={}))
    assert calls[0] == f"{GITHUB_API_ROOT}/releases/tags/v1.2.3"
    calls.clear()
    result = resolver.resolve(resolve_installation_selection(channel="prerelease", environ={}))
    assert result.release_tag == "v2.0.0-rc.1"


def test_prerelease_sorts_explicitly_by_published_at():
    from m32_bridge.installer.release_selection import ReleaseResolver, resolve_installation_selection

    def get(url, _timeout, _limit):
        if "/commits/" in url:
            return {"url": url, "sha": COMMIT}
        return [
            _release("v2.0.0-rc.1", prerelease=True, published="2026-01-01T00:00:00Z"),
            _release("v2.0.0-rc.2", prerelease=True, published="2026-02-01T00:00:00Z"),
        ]

    result = ReleaseResolver(json_get=get).resolve(resolve_installation_selection(channel="prerelease", environ={}))
    assert result.release_tag == "v2.0.0-rc.2"


def _release(tag: str, *, prerelease: bool, published: str = "2026-02-01T00:00:00Z") -> dict:
    return {
        "url": f"https://api.github.com/repos/DXBMARK/m32-bridge/releases/1",
        "html_url": f"https://github.com/DXBMARK/m32-bridge/releases/tag/{tag}",
        "tag_name": tag,
        "draft": False,
        "prerelease": prerelease,
        "published_at": published,
        "assets": [
            {
                "name": "m32-bridge-release.json",
                "browser_download_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-release.json",
            }
        ],
    }
