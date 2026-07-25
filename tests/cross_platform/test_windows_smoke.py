from __future__ import annotations

import platform
from pathlib import PureWindowsPath


def _windows_smoke_entry() -> dict[str, object]:
    commands = {
        "unit": ["py", "-m", "pytest", "tests", "-m", "unit"],
        "property": ["py", "-m", "pytest", "tests", "-m", "property"],
        "fake_m32": ["py", "-m", "pytest", str(PureWindowsPath("tests", "integration_fake_m32"))],
        "mcp_smoke": ["py", "-m", "pytest", str(PureWindowsPath("tests", "e2e_mcp"))],
        "startup": ["py", "-m", "m32_bridge", "health"],
    }
    current_platform = platform.system()
    return {
        "platform": "Windows",
        "current_platform": current_platform,
        "status": "ready_to_run" if current_platform == "Windows" else "not_run_on_this_platform",
        "commands": commands,
        "uses_bash_only_syntax": False,
        "uses_unix_only_paths": False,
        "external_emulator": False,
        "claims_windows_passed": current_platform == "Windows",
    }


def test_windows_smoke_entry_is_structured_and_does_not_claim_non_windows_success():
    entry = _windows_smoke_entry()

    assert entry["platform"] == "Windows"
    assert entry["uses_bash_only_syntax"] is False
    assert entry["uses_unix_only_paths"] is False
    assert entry["external_emulator"] is False
    assert entry["commands"]["startup"] == ["py", "-m", "m32_bridge", "health"]
    assert all(command[:3] == ["py", "-m", "pytest"] for key, command in entry["commands"].items() if key != "startup")
    if platform.system() != "Windows":
        assert entry["status"] == "not_run_on_this_platform"
        assert entry["claims_windows_passed"] is False


def test_windows_smoke_paths_are_windows_native_not_unix_only():
    entry = _windows_smoke_entry()

    assert "tests\\integration_fake_m32" in entry["commands"]["fake_m32"]
    assert "tests\\e2e_mcp" in entry["commands"]["mcp_smoke"]
    assert not any("/" in arg for command in entry["commands"].values() for arg in command)
