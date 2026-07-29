from __future__ import annotations

from pathlib import Path


FEATURE_DIR = Path(__file__).resolve().parents[2] / "specs" / "003-cross-platform-installers-and-first-run-setup"


def _contract() -> str:
    return (FEATURE_DIR / "contracts" / "installer-contract.md").read_text(encoding="utf-8")


def test_installer_contract_documents_user_local_entrypoints_and_paths():
    text = _contract()

    assert "install.sh" in text
    assert "install.ps1" in text
    assert "~/.m32-bridge/app" in text
    assert "~/.local/bin/m32-bridge" in text
    assert "%LOCALAPPDATA%\\M32Bridge\\app" in text
    assert "%LOCALAPPDATA%\\M32Bridge\\bin\\m32-bridge.cmd" in text
    assert "admin" in text.lower()
    assert "user-local" in text


def test_installer_contract_documents_runtime_manager_without_global_py():
    text = _contract()

    assert "uv" in text
    assert "global `py`" in text
    assert "manual guidance" in text
    assert "silent partial success" in text


def test_installer_contract_documents_all_idempotency_states():
    text = _contract()

    for state in [
        "fresh_install",
        "existing_install",
        "repair",
        "update",
        "already_current",
        "partial_failure",
        "failed",
    ]:
        assert state in text


def test_installer_contract_keeps_download_inspect_run_recommended():
    text = _contract()

    assert "Download the installer script" in text
    assert "Inspect it" in text
    assert "Run it locally" in text
    assert "curl -LsSf <url>/install.sh | sh" in text
    assert 'irm <url>/install.ps1 | iex' in text
    assert "Convenience examples must not be presented as safer" in text


def test_installer_contract_documents_first_run_setup_no_write_behavior():
    text = _contract()

    assert "/info" in text
    assert "no `/set`" in text
    assert "save config only after confirmation" in text
    assert "never hang in non-TTY" in text
    assert "osc_writes_sent=0" in text

