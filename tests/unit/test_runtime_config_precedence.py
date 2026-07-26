from __future__ import annotations

import importlib
from pathlib import Path


def _runtime_config_module():
    return importlib.import_module("m32_bridge.config.runtime")


def _write_config(path: Path, *, host: str, port: int) -> Path:
    path.write_text(f"host: {host}\nport: {port}\n", encoding="utf-8")
    return path


def test_cli_arguments_override_environment_user_config_and_project_dev_config(tmp_path: Path):
    runtime = _runtime_config_module()
    user_config = _write_config(tmp_path / "user.yaml", host="user.example", port=10023)
    project_config = _write_config(tmp_path / "project.yaml", host="project.example", port=10024)

    resolved = runtime.resolve_runtime_config(
        cli_args={"host": "cli.example", "port": 10025},
        environ={"M32_CONSOLE_HOST": "env.example", "M32_CONSOLE_PORT": "10026"},
        user_config_path=user_config,
        project_config_path=project_config,
        allow_project_local=True,
    )

    assert resolved.effective_host == "cli.example"
    assert resolved.effective_port == 10025
    assert resolved.source_by_field == {"host": "cli", "port": "cli"}


def test_environment_overrides_user_config_and_project_dev_config(tmp_path: Path):
    runtime = _runtime_config_module()
    user_config = _write_config(tmp_path / "user.yaml", host="user.example", port=10023)
    project_config = _write_config(tmp_path / "project.yaml", host="project.example", port=10024)

    resolved = runtime.resolve_runtime_config(
        cli_args={},
        environ={"M32_CONSOLE_HOST": "env.example", "M32_CONSOLE_PORT": "10026"},
        user_config_path=user_config,
        project_config_path=project_config,
        allow_project_local=True,
    )

    assert resolved.effective_host == "env.example"
    assert resolved.effective_port == 10026
    assert resolved.source_by_field == {"host": "env", "port": "env"}


def test_user_config_overrides_project_local_dev_config(tmp_path: Path):
    runtime = _runtime_config_module()
    user_config = _write_config(tmp_path / "user.yaml", host="user.example", port=10023)
    project_config = _write_config(tmp_path / "project.yaml", host="project.example", port=10024)

    resolved = runtime.resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=user_config,
        project_config_path=project_config,
        allow_project_local=True,
    )

    assert resolved.effective_host == "user.example"
    assert resolved.effective_port == 10023
    assert resolved.source_by_field == {"host": "user_config", "port": "user_config"}


def test_project_local_config_is_ignored_unless_development_or_test_context_is_explicit(tmp_path: Path):
    runtime = _runtime_config_module()
    project_config = _write_config(tmp_path / "project.yaml", host="project.example", port=10024)

    resolved = runtime.resolve_runtime_config(
        cli_args={},
        environ={},
        user_config_path=tmp_path / "missing-user.yaml",
        project_config_path=project_config,
        allow_project_local=False,
    )

    assert resolved.effective_host is None
    assert resolved.effective_port is None
    assert resolved.project_local_config_present is True
    assert resolved.project_local_config_used is False
    assert resolved.error_code == "NO_CONSOLE_HOST"
