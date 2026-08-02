from __future__ import annotations

import base64
import gzip
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "secure_bootstrap.py"
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"
COMMIT = "a" * 40


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m32_secure_bootstrap_test", BOOTSTRAP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _release(tag: str = "v1.2.3", *, prerelease: bool = False) -> dict:
    return {
        "url": "https://api.github.com/repos/DXBMARK/m32-bridge/releases/7",
        "html_url": f"https://github.com/DXBMARK/m32-bridge/releases/tag/{tag}",
        "tag_name": tag,
        "draft": False,
        "prerelease": prerelease,
        "published_at": "2026-08-02T00:00:00Z",
        "assets": [
            {
                "name": "m32-bridge-release.json",
                "browser_download_url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/m32-bridge-release.json",
            }
        ],
    }


def _json_get(url: str, _timeout: float, _limit: int):
    if "/commits/" in url:
        return {"url": url, "sha": COMMIT}
    if url.endswith("/releases/latest"):
        return _release()
    if "/releases/tags/" in url:
        return _release(url.rsplit("/", 1)[-1])
    return [_release("v2.0.0-rc.1", prerelease=True)]


def _source_tar(path: Path, *, version: str = "1.2.3", unsafe_name: str | None = None, symlink: bool = False) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        entries = {
            "m32-bridge/pyproject.toml": f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n".encode(),
            "m32-bridge/uv.lock": b"version = 1\n",
            "m32-bridge/src/m32_bridge/__init__.py": b"",
        }
        if unsafe_name:
            entries[unsafe_name] = b"escape"
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if symlink:
            info = tarfile.TarInfo("m32-bridge/escape-link")
            info.type = tarfile.SYMTYPE
            info.linkname = "../../outside"
            archive.addfile(info)
    return path


def _source_zip(path: Path, *, version: str = "1.2.3", unsafe_name: str | None = None, symlink: bool = False) -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = {
            "m32-bridge/pyproject.toml": f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n".encode(),
            "m32-bridge/uv.lock": b"version = 1\n",
            "m32-bridge/src/m32_bridge/__init__.py": b"",
        }
        if unsafe_name:
            entries[unsafe_name] = b"escape"
        for name, payload in entries.items():
            archive.writestr(name, payload)
        if symlink:
            info = zipfile.ZipInfo("m32-bridge/escape-link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../../outside")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(archive: Path, *, tag: str = "v1.2.3", windows_archive: Path | None = None) -> bytes:
    checksum = _sha256(archive)
    windows_checksum = _sha256(windows_archive) if windows_archive is not None else "b" * 64
    assets = {
        "posix_source": ("m32-bridge-source.tar.gz", checksum),
        "windows_source": ("m32-bridge-source.zip", windows_checksum),
        "posix_installer": ("install.sh", "c" * 64),
        "windows_installer": ("install.ps1", "d" * 64),
    }
    document = {
        "schema_version": "1",
        "product": "X32-Bridge MCP",
        "application_version": tag[1:],
        "release_tag": tag,
        "release_channel": "prerelease" if "-" in tag else "stable",
        "source_commit": COMMIT,
        "repository_url": "https://github.com/DXBMARK/m32-bridge",
        "published_at": "2026-08-02T00:00:00Z",
        "assets": {
            key: {
                "name": name,
                "url": f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/{name}",
                "sha256": digest,
            }
            for key, (name, digest) in assets.items()
        },
    }
    return json.dumps(document).encode()


def test_secure_bootstrap_is_stdlib_only_and_compilable():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    compile(text, str(BOOTSTRAP), "exec")
    assert "from m32_bridge" not in text
    assert "import m32_bridge" not in text
    assert "import requests" not in text
    assert "import yaml" not in text


@pytest.mark.parametrize("surface", ["posix", "windows"])
def test_release_dry_run_resolves_manifest_without_archive_download(surface, tmp_path):
    module = _module()
    archive = _source_tar(tmp_path / "fixture.tar.gz")
    calls: list[str] = []

    def byte_get(url: str, _limit: int, _timeout: float) -> bytes:
        calls.append(url)
        return _manifest(archive)

    def forbidden_download(*_args, **_kwargs):
        raise AssertionError("dry-run downloaded the source archive")

    plan = module.resolve_bootstrap(
        surface=surface,
        output_root=tmp_path / "out",
        channel="stable",
        dry_run=True,
        json_get=_json_get,
        byte_get=byte_get,
        asset_download=forbidden_download,
    )

    assert plan.ok is True
    assert plan.status == "release_plan_ready"
    assert plan.archive_path is None
    assert plan.source_root is None
    assert plan.archive_checksum_status == "not_downloaded_dry_run"
    assert plan.manifest_status == "validated"
    assert plan.manifest_path is None
    assert calls == ["https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-release.json"]
    assert not list((tmp_path / "out").glob("m32-bridge-source.*"))
    assert not (tmp_path / "out" / "m32-bridge-release.json").exists()


def test_release_bootstrap_validates_checksum_then_extracts_one_project(tmp_path):
    module = _module()
    fixture = _source_tar(tmp_path / "fixture.tar.gz")
    manifest = _manifest(fixture)
    download_calls: list[tuple[str, str]] = []

    def downloader(url: str, destination: Path, *, expected_sha256: str, **_kwargs):
        download_calls.append((url, expected_sha256))
        assert expected_sha256 == _sha256(fixture)
        shutil.copy2(fixture, destination)
        return destination

    plan = module.resolve_bootstrap(
        surface="posix",
        output_root=tmp_path / "out",
        version="v1.2.3",
        json_get=_json_get,
        byte_get=lambda *_args: manifest,
        asset_download=downloader,
    )

    assert plan.status == "release_preflight_complete"
    assert plan.archive_checksum_status == "verified"
    assert plan.identity_status == "validated"
    assert plan.staged_application_version == "1.2.3"
    assert Path(plan.source_root, "pyproject.toml").is_file()
    assert Path(plan.source_root, "uv.lock").is_file()
    assert download_calls == [
        (
            "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz",
            _sha256(fixture),
        )
    ]


def test_windows_release_bootstrap_validates_zip_checksum_then_extracts_one_project(tmp_path):
    module = _module()
    tar_fixture = _source_tar(tmp_path / "fixture.tar.gz")
    zip_fixture = _source_zip(tmp_path / "fixture.zip")
    manifest = _manifest(tar_fixture, windows_archive=zip_fixture)

    def downloader(url: str, destination: Path, *, expected_sha256: str, **_kwargs):
        assert url.endswith("/m32-bridge-source.zip")
        assert expected_sha256 == _sha256(zip_fixture)
        shutil.copy2(zip_fixture, destination)
        return destination

    plan = module.resolve_bootstrap(
        surface="windows",
        output_root=tmp_path / "out",
        version="v1.2.3",
        json_get=_json_get,
        byte_get=lambda *_args: manifest,
        asset_download=downloader,
    )

    assert plan.status == "release_preflight_complete"
    assert plan.archive_checksum_status == "verified"
    assert plan.source_archive_url.endswith("/m32-bridge-source.zip")
    assert plan.staged_application_version == "1.2.3"
    assert Path(plan.source_root, "pyproject.toml").is_file()
    assert Path(plan.source_root, "uv.lock").is_file()


class _Response:
    def __init__(self, url: str, payload: bytes) -> None:
        self._url = url
        self._payload = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        return self._payload.read(size)


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response

    def open(self, _request, timeout: float):
        assert timeout > 0
        return self.response


def test_checksum_mismatch_deletes_archive_before_extraction(tmp_path):
    module = _module()
    url = "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz"
    destination = tmp_path / "source.tar.gz"
    opener = _Opener(_Response(url, b"not-the-expected-archive"))

    with pytest.raises(module.BootstrapError, match="RELEASE_ARCHIVE_CHECKSUM_MISMATCH"):
        module.download_source_asset(
            url,
            destination,
            expected_sha256="0" * 64,
            boundary="release",
            expected_commit=COMMIT,
            opener=opener,
        )

    assert not destination.exists()


@pytest.mark.parametrize(
    "archive_factory",
    [
        lambda path: _source_tar(path, unsafe_name="../escape"),
        lambda path: _source_tar(path, unsafe_name="/absolute"),
        lambda path: _source_tar(path, symlink=True),
    ],
)
def test_secure_extraction_rejects_traversal_absolute_and_symlink(archive_factory, tmp_path):
    module = _module()
    archive = archive_factory(tmp_path / "unsafe.tar.gz")
    with pytest.raises(module.BootstrapError, match="RELEASE_ARCHIVE_UNSAFE"):
        module.safe_extract_archive(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "archive_factory",
    [
        lambda path: _source_zip(path, unsafe_name="../escape"),
        lambda path: _source_zip(path, unsafe_name="/absolute"),
        lambda path: _source_zip(path, symlink=True),
    ],
)
def test_windows_secure_extraction_rejects_traversal_absolute_and_symlink(archive_factory, tmp_path):
    module = _module()
    archive = archive_factory(tmp_path / "unsafe.zip")
    with pytest.raises(module.BootstrapError, match="RELEASE_ARCHIVE_UNSAFE"):
        module.safe_extract_archive(archive, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_commit_redirect_requires_same_repository_format_and_commit():
    module = _module()
    initial = f"https://github.com/DXBMARK/m32-bridge/archive/{COMMIT}.tar.gz"
    allowed = f"https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/{COMMIT}"
    assert module._validated_redirect(initial, allowed, boundary="commit", expected_commit=COMMIT, surface="posix") == allowed
    for rejected in (
        f"https://codeload.github.com/OTHER/m32-bridge/tar.gz/{COMMIT}",
        f"https://codeload.github.com/DXBMARK/m32-bridge/zip/{COMMIT}",
        "https://127.0.0.1/source",
        f"https://codeload.github.com/DXBMARK/m32-bridge/tar.gz/{'b' * 40}",
    ):
        with pytest.raises(module.BootstrapError, match="SOURCE_BOUNDARY_REJECTED"):
            module._validated_redirect(initial, rejected, boundary="commit", expected_commit=COMMIT, surface="posix")


def _embedded_payload(text: str, variable: str) -> str:
    marker = f'{variable}"'
    start = text.index(marker) + len(marker)
    end = text.index('"', start)
    return text[start:end]


def test_embedded_bootstrap_payloads_match_canonical_source():
    canonical = BOOTSTRAP.read_bytes()
    expected = base64.b64encode(gzip.compress(canonical, compresslevel=9, mtime=0)).decode()
    posix = _embedded_payload(POSIX_INSTALLER.read_text(encoding="utf-8"), "SECURE_BOOTSTRAP_PAYLOAD=")
    windows = _embedded_payload(WINDOWS_INSTALLER.read_text(encoding="utf-8"), "$SecureBootstrapPayload = ")
    assert posix == expected
    assert windows == expected
    assert gzip.decompress(base64.b64decode(posix)) == canonical


def test_installers_never_extract_unverified_remote_archives_or_resolve_twice():
    posix = POSIX_INSTALLER.read_text(encoding="utf-8")
    windows = WINDOWS_INSTALLER.read_text(encoding="utf-8")
    for forbidden in ("tar -xzf", "resolve_prerelease_tag", "resolve_main_commit", "releases?per_page=100", "/commits/main"):
        assert forbidden not in posix
    for forbidden in ("Expand-Archive", "Resolve-GithubValue", "releases?per_page=100", "/commits/main"):
        assert forbidden not in windows
    for text in (posix, windows):
        assert "secure_bootstrap.py" in text
        assert "bootstrap-plan.json" in text
        assert "--bootstrap-plan" in text
    assert "mktemp -d" in posix and "m32-bridge-bootstrap.XXXXXX" in posix
    assert "[Guid]::NewGuid()" in windows


def _plan_document(tmp_path: Path) -> tuple[dict, Path]:
    root = tmp_path / "staging" / "extracted" / "m32-bridge"
    (root / "src" / "m32_bridge").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nversion='1.2.3'\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    archive = tmp_path / "staging" / "m32-bridge-source.tar.gz"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "staging" / "m32-bridge-release.json"
    manifest.write_text("{}", encoding="utf-8")
    plan = {
        "schema_version": "1",
        "ok": True,
        "status": "release_preflight_complete",
        "surface": "posix",
        "dry_run": False,
        "requested_selection": "stable",
        "selection_kind": "stable",
        "release_channel": "stable",
        "release_tag": "v1.2.3",
        "source_commit": COMMIT,
        "source_ref": COMMIT,
        "install_source": "github_release_asset",
        "manifest_status": "validated",
        "manifest_schema_version": "1",
        "archive_checksum_status": "verified",
        "staged_application_version": "1.2.3",
        "application_version": "1.2.3",
        "identity_status": "validated",
        "source_archive_url": "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz",
        "source_archive_sha256": "1" * 64,
        "installer_asset_url": "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/install.sh",
        "installer_asset_sha256": "2" * 64,
        "manifest_path": str(manifest),
        "archive_path": str(archive),
        "source_root": str(root),
        "user_local": True,
        "admin_required": False,
        "system_python_modified": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }
    plan_path = tmp_path / "staging" / "bootstrap-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan, plan_path


def test_runtime_accepts_verified_plan_without_release_resolver(monkeypatch, tmp_path):
    from m32_bridge.installer import script_runtime

    plan, plan_path = _plan_document(tmp_path)
    monkeypatch.setattr(script_runtime.ReleaseResolver, "resolve", lambda *_args, **_kwargs: pytest.fail("resolver called"))
    loaded = script_runtime._load_bootstrap_plan(
        plan_path,
        surface="posix",
        source_root=Path(plan["source_root"]),
        version=None,
        channel="stable",
        ref=None,
        local=None,
    )
    selection, resolution = script_runtime._selection_and_resolution_from_bootstrap_plan(loaded)
    assert selection.kind == "stable"
    assert selection.origin == "verified_bootstrap_plan"
    assert resolution.release_tag == "v1.2.3"
    assert resolution.source_commit == COMMIT


def test_runtime_rejects_bootstrap_plan_path_escape(tmp_path):
    from m32_bridge.installer import script_runtime

    plan, plan_path = _plan_document(tmp_path)
    outside = tmp_path / "outside"
    (outside / "src" / "m32_bridge").mkdir(parents=True)
    (outside / "pyproject.toml").write_text("[project]\nversion='1.2.3'\n", encoding="utf-8")
    (outside / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    plan["source_root"] = str(outside)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(Exception, match="escapes"):
        script_runtime._load_bootstrap_plan(
            plan_path,
            surface="posix",
            source_root=outside,
            version=None,
            channel="stable",
            ref=None,
            local=None,
        )


def test_runtime_rejects_bootstrap_plan_release_url_mismatch(tmp_path):
    from m32_bridge.installer import script_runtime

    plan, plan_path = _plan_document(tmp_path)
    plan["source_archive_url"] = "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.4/m32-bridge-source.tar.gz"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(Exception, match="URLs"):
        script_runtime._load_bootstrap_plan(
            plan_path,
            surface="posix",
            source_root=Path(plan["source_root"]),
            version=None,
            channel="stable",
            ref=None,
            local=None,
        )


def test_posix_standalone_remote_handoff_uses_one_verified_bootstrap_plan(tmp_path):
    remote = tmp_path / "downloaded" / "install.sh"
    remote.parent.mkdir()
    remote.write_text(POSIX_INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    remote.chmod(0o755)

    verified_root = tmp_path / "verified" / "m32-bridge"
    (verified_root / "src" / "m32_bridge").mkdir(parents=True)
    (verified_root / "pyproject.toml").write_text("[project]\nversion='1.2.3'\n", encoding="utf-8")
    (verified_root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    archive = tmp_path / "verified" / "m32-bridge-source.tar.gz"
    archive.write_bytes(b"verified archive fixture")
    manifest = tmp_path / "verified" / "m32-bridge-release.json"
    manifest.write_text("{}", encoding="utf-8")
    plan = {
        "schema_version": "1",
        "ok": True,
        "status": "release_preflight_complete",
        "surface": "posix",
        "dry_run": False,
        "requested_selection": "stable",
        "selection_kind": "stable",
        "release_channel": "stable",
        "release_tag": "v1.2.3",
        "source_commit": COMMIT,
        "source_ref": COMMIT,
        "install_source": "github_release_asset",
        "manifest_status": "validated",
        "manifest_schema_version": "1",
        "archive_checksum_status": "verified",
        "staged_application_version": "1.2.3",
        "application_version": "1.2.3",
        "identity_status": "validated",
        "source_archive_url": "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/m32-bridge-source.tar.gz",
        "source_archive_sha256": "1" * 64,
        "installer_asset_url": "https://github.com/DXBMARK/m32-bridge/releases/download/v1.2.3/install.sh",
        "installer_asset_sha256": "2" * 64,
        "manifest_path": str(manifest),
        "archive_path": str(archive),
        "source_root": str(verified_root),
        "user_local": True,
        "admin_required": False,
        "system_python_modified": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }
    plan_fixture = tmp_path / "plan-fixture.json"
    plan_fixture.write_text(json.dumps(plan), encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.log"
    final_args = tmp_path / "final-args.log"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_UV_LOG\"\n"
        "while [ \"$#\" -gt 0 ] && [ \"$1\" != python ]; do shift; done\n"
        "[ \"$#\" -gt 0 ] && shift\n"
        "case \"${1:-}\" in\n"
        "  *secure_bootstrap.py) cat \"$FAKE_PLAN\"; exit 0 ;;\n"
        "  -c) exec \"$FAKE_REAL_PYTHON\" \"$@\" ;;\n"
        "  -m) printf '%s\\n' \"$*\" > \"$FAKE_FINAL_ARGS\"; exit 0 ;;\n"
        "esac\n"
        "exit 99\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/bin/sh\necho NETWORK_CALLED >&2\nexit 97\n", encoding="utf-8")
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "TERM": "dumb",
            "FAKE_UV_LOG": str(uv_log),
            "FAKE_PLAN": str(plan_fixture),
            "FAKE_REAL_PYTHON": sys.executable,
            "FAKE_FINAL_ARGS": str(final_args),
        }
    )
    completed = __import__("subprocess").run(
        ["/bin/sh", str(remote)],
        cwd=remote.parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert "NETWORK_CALLED" not in completed.stderr
    calls = uv_log.read_text(encoding="utf-8")
    helper_runs = [line for line in calls.splitlines() if "secure_bootstrap.py --surface posix" in line]
    assert len(helper_runs) == 1
    final = final_args.read_text(encoding="utf-8")
    assert "-m m32_bridge.installer.script_runtime" in final
    assert "--bootstrap-plan" in final
    assert f"--source-root {verified_root}" in final
    assert "--channel stable" in final
    assert "--bootstrap-apply" in final
    assert "--archive-path" not in final
    assert "--manifest-path" not in final
