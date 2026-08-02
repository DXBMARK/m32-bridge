from __future__ import annotations

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _project(root: Path, version: str = "1.2.3") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "pyproject.toml"
    path.write_text(f"[project]\nname='m32-mcp-bridge'\nversion='{version}'\n", encoding="utf-8")
    return path


def test_read_project_version_uses_project_metadata(tmp_path):
    from m32_bridge.installer.application_version import read_project_version

    assert read_project_version(_project(tmp_path, "9.15.23")) == "9.15.23"


@pytest.mark.parametrize("version", ["0.1.0", "1.0.0", "9.15.23", "2.0.0-rc.1"])
def test_supported_project_versions(version, tmp_path):
    from m32_bridge.installer.application_version import read_project_version

    assert read_project_version(_project(tmp_path, version)) == version


@pytest.mark.parametrize("version", ["", " 1.2.3", "01.2.3", "1.2", "1.2.3\nnext"])
def test_invalid_project_versions_are_controlled(version, tmp_path):
    from m32_bridge.installer.application_version import read_project_version

    with pytest.raises(ValueError):
        read_project_version(_project(tmp_path, version))


def test_installed_source_only_runtime_reads_version_from_pyproject(monkeypatch, tmp_path):
    from m32_bridge.installer import application_version as module

    _project(tmp_path / "app", "1.7.4")
    monkeypatch.setattr(module, "_read_distribution_version", lambda _name: None)
    resolved = module.resolve_installed_application_version(tmp_path / "app", local_development=False)
    assert resolved.version == "1.7.4"
    assert resolved.source == "installed_pyproject"
    assert resolved.status == "resolved"


def test_installed_runtime_never_needs_project_distribution_metadata(monkeypatch, tmp_path):
    from m32_bridge.installer import application_version as module

    _project(tmp_path / "app", "3.4.5")
    monkeypatch.setattr(module, "_read_distribution_version", lambda _name: None)
    assert module.application_version(tmp_path / "app", environ={"M32_BRIDGE_INSTALLED_RUNTIME": "1"}) == "3.4.5"


def test_distribution_metadata_alone_is_not_application_version_truth(monkeypatch, tmp_path):
    from m32_bridge.installer import application_version as module

    monkeypatch.setattr(module, "_read_distribution_version", lambda _name: "8.7.6")
    resolved = module.resolve_installed_application_version(tmp_path / "missing", local_development=False)
    assert resolved.version == "unknown"
    assert resolved.source == "unknown"
    assert resolved.status == "version_unavailable"
    assert resolved.distribution_version == "8.7.6"


def test_distribution_and_pyproject_mismatch_is_explicit(monkeypatch, tmp_path):
    from m32_bridge.installer import application_version as module

    _project(tmp_path / "app", "1.2.3")
    monkeypatch.setattr(module, "_read_distribution_version", lambda _name: "1.2.4")
    resolved = module.resolve_installed_application_version(tmp_path / "app", local_development=False)
    assert resolved.version == "1.2.3"
    assert resolved.status == "version_source_mismatch"
    assert resolved.mismatch is True


def test_staged_version_never_uses_requested_or_metadata_values(tmp_path):
    from m32_bridge.installer.application_version import resolve_staged_application_version

    _project(tmp_path, "5.17.3")
    resolved = resolve_staged_application_version(tmp_path)
    assert resolved.version == "5.17.3"
    assert resolved.source == "staged_pyproject"


def test_missing_installed_version_is_controlled(monkeypatch, tmp_path):
    from m32_bridge.installer import application_version as module

    monkeypatch.setattr(module, "_read_distribution_version", lambda _name: None)
    resolved = module.resolve_installed_application_version(tmp_path / "missing", local_development=False)
    assert resolved.version == "unknown"
    assert resolved.status == "version_unavailable"


def test_package_dunder_version_uses_central_resolver(monkeypatch):
    import m32_bridge
    from m32_bridge.installer import application_version as module

    monkeypatch.setattr(module, "application_version", lambda *_args, **_kwargs: "9.8.7")

    assert m32_bridge.__version__ == "9.8.7"
    assert "__version__" not in vars(m32_bridge)


def _current_version_literals(*roots: Path) -> list[str]:
    from m32_bridge.installer.application_version import read_project_version

    current = read_project_version(ROOT / "pyproject.toml")
    quoted = re.compile(rf"(?P<quote>['\"]){re.escape(current)}(?P=quote)")
    occurrences: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.suffix in {".py", ".sh", ".ps1", ".yml", ".yaml"})
        for path in paths:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if quoted.search(line):
                    occurrences.append(f"{path.relative_to(ROOT)}:{line_number}")
    return occurrences


def test_current_project_version_not_hardcoded_in_src_or_scripts():
    assert _current_version_literals(ROOT / "src", ROOT / "scripts") == []


def test_script_runtime_has_no_application_version_constant():
    assert _current_version_literals(ROOT / "src/m32_bridge/installer/script_runtime.py") == []


def test_posix_installer_has_no_target_version_constant():
    assert _current_version_literals(ROOT / "scripts/install.sh") == []


def test_powershell_installer_has_no_target_version_constant():
    assert _current_version_literals(ROOT / "scripts/install.ps1") == []


def test_no_application_version_fallback_literal():
    assert _current_version_literals(ROOT / "src", ROOT / "scripts") == []


def test_pyproject_is_single_declarative_version_source():
    assert _current_version_literals(ROOT / "src", ROOT / "scripts", ROOT / ".github") == []


def test_product_user_agents_do_not_embed_release_versions():
    pattern = re.compile(r"User-Agent[^\n]*(?:M32|X32)[^\n]*/v?[0-9]+\.[0-9]+(?:\.[0-9]+)?", re.IGNORECASE)
    occurrences: list[str] = []
    for root in (ROOT / "src", ROOT / "scripts"):
        paths = sorted(path for path in root.rglob("*") if path.suffix in {".py", ".sh", ".ps1"})
        for path in paths:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern.search(line):
                    occurrences.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert occurrences == []
