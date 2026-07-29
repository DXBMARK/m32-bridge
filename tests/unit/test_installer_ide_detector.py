from __future__ import annotations

from m32_bridge.installer.ide_detector import detect_ide_clients


def test_ide_discovery_returns_structured_detected_and_not_detected(tmp_path):
    clients = detect_ide_clients(environ={"CODEX_HOME": str(tmp_path)}, home=tmp_path)

    statuses = {client["client_id"]: client for client in clients}
    assert statuses["codex"]["status"] == "detected"
    assert statuses["codex"]["status_dot"] == "green"
    assert statuses["claude_desktop"]["status"] == "not_detected"
    assert statuses["claude_desktop"]["status_dot"] == "grey"


def test_ide_discovery_does_not_open_apps_or_write_config(tmp_path):
    clients = detect_ide_clients(environ={}, home=tmp_path)

    assert clients
    assert all(client["writes_config"] is False for client in clients)
    assert all(client["opens_app"] is False for client in clients)
    assert all(client["requires_permission"] is False for client in clients)


def test_ide_discovery_uses_macos_support_paths_without_side_effects(tmp_path):
    claude = tmp_path / "Library" / "Application Support" / "Claude"
    claude.mkdir(parents=True)

    clients = detect_ide_clients(environ={}, home=tmp_path, os_family="macos")
    statuses = {client["client_id"]: client for client in clients}

    assert statuses["claude_desktop"]["status"] == "detected"
    assert statuses["claude_desktop"]["writes_config"] is False
    assert statuses["claude_desktop"]["opens_app"] is False


def test_ide_discovery_uses_windows_appdata_hints_without_side_effects(tmp_path):
    appdata = tmp_path / "Roaming"
    code = appdata / "Code"
    code.mkdir(parents=True)

    clients = detect_ide_clients(environ={"APPDATA": str(appdata)}, home=tmp_path, os_family="windows")
    statuses = {client["client_id"]: client for client in clients}

    assert statuses["vscode"]["status"] == "detected"
    assert statuses["vscode"]["requires_permission"] is False


def test_ide_discovery_uses_linux_config_hints_without_side_effects(tmp_path):
    gemini = tmp_path / ".config" / "gemini"
    gemini.mkdir(parents=True)

    clients = detect_ide_clients(environ={}, home=tmp_path, os_family="linux")
    statuses = {client["client_id"]: client for client in clients}

    assert statuses["gemini"]["status"] == "detected"
    assert statuses["gemini"]["writes_config"] is False
