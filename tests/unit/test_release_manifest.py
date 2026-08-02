from __future__ import annotations

import json
from pathlib import Path

import pytest


COMMIT = "a" * 40
CHECKSUM = "b" * 64


def _manifest(tag: str = "v1.2.3", channel: str = "stable") -> dict:
    version = tag[1:]
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
        "release_channel": channel,
        "source_commit": COMMIT,
        "repository_url": "https://github.com/DXBMARK/m32-bridge",
        "published_at": "2026-08-02T00:00:00Z",
        "assets": {
            key: {
                "name": name,
                "url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/{name}",
                "sha256": CHECKSUM,
            }
            for key, name in names.items()
        },
    }


def test_release_manifest_valid_stable_and_prerelease():
    from m32_bridge.installer.release_manifest import validate_release_manifest

    assert validate_release_manifest(_manifest())["release_channel"] == "stable"
    assert validate_release_manifest(_manifest("v2.0.0-rc.1", "prerelease"))["application_version"] == "2.0.0-rc.1"


def test_manifest_tag_matches_application_version():
    from m32_bridge.installer.release_manifest import ReleaseManifestError, validate_release_manifest

    document = _manifest()
    document["application_version"] = "1.2.4"
    with pytest.raises(ReleaseManifestError, match="RELEASE_VERSION_MISMATCH"):
        validate_release_manifest(document)


def test_manifest_commit_matches_resolved_tag_commit():
    from m32_bridge.installer.release_manifest import ReleaseManifestError, validate_release_manifest

    with pytest.raises(ReleaseManifestError, match="RELEASE_COMMIT_MISMATCH"):
        validate_release_manifest(_manifest(), resolved_source_commit="c" * 40)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(extra="x"),
        lambda value: value.update(product="Other"),
        lambda value: value.update(repository_url="https://github.com/OTHER/m32-bridge"),
        lambda value: value["assets"]["posix_source"].update(sha256="A" * 64),
        lambda value: value["assets"]["posix_source"].update(url="https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.4/m32-bridge-source.tar.gz"),
        lambda value: value["assets"]["posix_source"].update(url="https://github.com/OTHER/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz"),
        lambda value: value["assets"]["posix_source"].update(url="https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz?token=x"),
    ],
)
def test_manifest_rejects_unknown_wrong_or_unsafe_values(mutate):
    from m32_bridge.installer.release_manifest import ReleaseManifestError, validate_release_manifest

    document = _manifest()
    mutate(document)
    with pytest.raises(ReleaseManifestError):
        validate_release_manifest(document)


def test_manifest_rejects_stable_prerelease_mismatch():
    from m32_bridge.installer.release_manifest import ReleaseManifestError, validate_release_manifest

    with pytest.raises(ReleaseManifestError):
        validate_release_manifest(_manifest("v2.0.0-rc.1", "stable"))


def test_manifest_response_size_is_bounded():
    from m32_bridge.installer.release_manifest import MANIFEST_MAX_BYTES, ReleaseManifestError, validate_release_manifest

    with pytest.raises(ReleaseManifestError):
        validate_release_manifest(b"{" + b"x" * MANIFEST_MAX_BYTES + b"}")


def test_manifest_builder_is_deterministic_and_reads_pyproject(tmp_path):
    from m32_bridge.installer.release_manifest import ASSET_NAMES, build_release_manifest, serialize_release_manifest

    source = tmp_path / "source"
    assets = tmp_path / "assets"
    source.mkdir()
    assets.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='m32-mcp-bridge'\nversion='9.15.23'\n", encoding="utf-8")
    for index, name in enumerate(ASSET_NAMES.values()):
        (assets / name).write_bytes(f"asset-{index}".encode())
    kwargs = dict(source_root=source, assets_dir=assets, release_tag="v9.15.23", source_commit=COMMIT, published_at="2026-08-02T00:00:00Z")
    first = serialize_release_manifest(build_release_manifest(**kwargs))
    second = serialize_release_manifest(build_release_manifest(**kwargs))
    assert first == second
    assert json.loads(first)["application_version"] == "9.15.23"


def test_multiple_versions_use_same_builder_without_code_change(tmp_path):
    from m32_bridge.installer.release_manifest import ASSET_NAMES, build_release_manifest

    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ASSET_NAMES.values():
        (assets / name).write_text(name, encoding="utf-8")
    for version in ("0.1.0", "0.1.1", "1.0.0", "9.15.23", "2.0.0-rc.1"):
        source = tmp_path / version
        source.mkdir()
        (source / "pyproject.toml").write_text(f"[project]\nversion='{version}'\n", encoding="utf-8")
        manifest = build_release_manifest(source_root=source, assets_dir=assets, release_tag=f"v{version}", source_commit=COMMIT, published_at="2026-08-02T00:00:00Z")
        assert manifest["application_version"] == version


def test_release_workflow_is_generic_and_quality_gated():
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'tags:\n      - "v*"' in text
    assert "workflow_dispatch:" in text
    assert "if: github.event_name == 'push'" in text
    assert "uv lock --check" in text
    assert "python -m compileall src tests scripts" in text
    assert "--extra test python -m pytest tests/unit tests/cross_platform" in text
    assert "uv run --frozen --python 3.13 pytest" not in text
    assert 'ref: ${{ github.sha }}' in text
    assert "tag {actual} does not match {expected}" in text
    assert "git archive" in text
    assert "scripts/build_release_manifest.py" in text
    assert "date -u +\'%Y-%m-%dT%H:%M:%SZ\'" in text
    assert "git show -s --format=%cI" not in text
    for name in ("install.sh", "install.ps1", "m32-bridge-source.tar.gz", "m32-bridge-source.zip", "m32-bridge-release.json", "SHA256SUMS"):
        assert f"dist/{name}" in text
    assert not any(suffix in text for suffix in (".msi", ".pkg", ".deb", ".rpm", ".exe"))
    assert "git add" not in text and "git commit" not in text and "git push" not in text


def test_release_workflow_contains_no_hardcoded_release_version():
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for version in ("v0.1.0", "v0.1.1", "v1.0.0", "v9.15.23", "v2.0.0-rc.1"):
        assert version not in text
