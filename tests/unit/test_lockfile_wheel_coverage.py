from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from lockfile_artifact_audit import audit_lock_artifacts, load_lock
from m32_bridge.installer.support_matrix import INSTALLER_TARGETS, release_supported_targets, target_by_id


ROOT = Path(__file__).resolve().parents[2]
INCIDENT_PACKAGES = {
    "pydantic-core": "2.46.4",
    "rpds-py": "2026.6.3",
    "cffi": "2.1.0",
    "pyyaml": "6.0.3",
}


def test_all_release_supported_runtime_packages_have_locked_wheels():
    lock = load_lock(ROOT / "uv.lock")

    verdicts = [audit_lock_artifacts(lock, target) for target in release_supported_targets()]

    assert all(verdict.ok for verdict in verdicts), verdicts
    assert {package for verdict in verdicts for package in verdict.native_packages} == {
        "cffi",
        "cryptography",
        "pydantic-core",
        "pywin32",
        "pyyaml",
        "rpds-py",
    }


def test_macos_intel_release_gate_exposes_current_cryptography_blocker():
    verdict = audit_lock_artifacts(load_lock(ROOT / "uv.lock"), target_by_id("macos_x86_64_cp313"))

    assert verdict.ok is False
    assert verdict.error_code == "LOCKFILE_ARTIFACT_COVERAGE_INCOMPLETE"
    assert verdict.missing_wheel_packages == ("cryptography",)


def test_ubuntu_incident_packages_keep_exact_versions_and_linux_cp313_wheels():
    lock = load_lock(ROOT / "uv.lock")
    packages = {package["name"]: package for package in lock["package"]}
    verdict = audit_lock_artifacts(lock, target_by_id("linux_x86_64_cp313"))

    assert verdict.ok is True
    for package_name, expected_version in INCIDENT_PACKAGES.items():
        assert packages[package_name]["version"] == expected_version
        assert package_name in verdict.native_packages


def _fixture_lock(*, wheels: list[str], marker: str | None = None) -> dict[str, object]:
    dependency = {"name": "native-demo"}
    if marker:
        dependency["marker"] = marker
    return {
        "package": [
            {"name": "m32-mcp-bridge", "version": "0.1.0", "dependencies": [dependency]},
            {
                "name": "native-demo",
                "version": "1.0.0",
                "sdist": {"url": "https://index.invalid/native-demo-1.0.0.tar.gz"},
                "wheels": [{"url": f"https://index.invalid/{wheel}"} for wheel in wheels],
            },
        ]
    }


COMPLETE_NATIVE_WHEELS = [
    "native_demo-1.0.0-cp313-cp313-manylinux_2_17_x86_64.whl",
    "native_demo-1.0.0-cp313-cp313-manylinux_2_17_aarch64.whl",
    "native_demo-1.0.0-cp313-cp313-macosx_11_0_arm64.whl",
    "native_demo-1.0.0-cp313-cp313-macosx_10_13_x86_64.whl",
    "native_demo-1.0.0-cp313-cp313-win_amd64.whl",
]


def test_fixture_complete_native_lock_passes_every_declared_target():
    lock = _fixture_lock(wheels=COMPLETE_NATIVE_WHEELS)

    assert all(audit_lock_artifacts(lock, target).ok for target in INSTALLER_TARGETS)


@pytest.mark.parametrize(
    ("missing_wheel", "target_id"),
    [
        ("native_demo-1.0.0-cp313-cp313-manylinux_2_17_x86_64.whl", "linux_x86_64_cp313"),
        ("native_demo-1.0.0-cp313-cp313-macosx_11_0_arm64.whl", "macos_arm64_cp313"),
        ("native_demo-1.0.0-cp313-cp313-win_amd64.whl", "windows_amd64_cp313"),
    ],
)
def test_fixture_missing_target_artifact_fails_precisely(missing_wheel: str, target_id: str):
    lock = _fixture_lock(wheels=[wheel for wheel in COMPLETE_NATIVE_WHEELS if wheel != missing_wheel])

    verdict = audit_lock_artifacts(lock, target_by_id(target_id))

    assert verdict.error_code == "LOCKFILE_ARTIFACT_COVERAGE_INCOMPLETE"
    assert verdict.missing_wheel_packages == ("native-demo",)


def test_fixture_sdist_only_package_fails_but_universal_wheel_passes():
    sdist_only = _fixture_lock(wheels=[])
    universal = _fixture_lock(wheels=["native_demo-1.0.0-py3-none-any.whl"])

    assert audit_lock_artifacts(sdist_only, target_by_id("linux_x86_64_cp313")).ok is False
    assert all(audit_lock_artifacts(universal, target).ok for target in INSTALLER_TARGETS)


def test_fixture_os_marker_excludes_native_package_outside_matching_os():
    lock = _fixture_lock(
        wheels=["native_demo-1.0.0-cp313-cp313-win_amd64.whl"],
        marker="sys_platform == 'win32'",
    )

    linux = audit_lock_artifacts(lock, target_by_id("linux_x86_64_cp313"))
    windows = audit_lock_artifacts(lock, target_by_id("windows_amd64_cp313"))

    assert "native-demo" not in linux.runtime_packages
    assert windows.ok is True


def test_index_availability_never_substitutes_for_missing_lock_artifact():
    lock = _fixture_lock(wheels=[])
    index_has_compatible_wheel = True

    verdict = audit_lock_artifacts(deepcopy(lock), target_by_id("linux_x86_64_cp313"))

    assert index_has_compatible_wheel is True
    assert verdict.ok is False
    assert verdict.error_code == "LOCKFILE_ARTIFACT_COVERAGE_INCOMPLETE"
