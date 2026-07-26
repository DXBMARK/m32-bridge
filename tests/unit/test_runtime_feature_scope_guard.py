from __future__ import annotations

import argparse
import inspect
from pathlib import Path

import tomllib

from m32_bridge import __main__ as package_main
from m32_bridge import cli
from m32_bridge.mcp.server import ToolRegistry, register_mvp_tools


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_SURFACE_TERMS = {
    "raw_osc",
    "send_raw_osc",
    "osc_raw",
    "arbitrary_path",
    "set_any_path",
    "execute_shell",
    "shell_command",
    "firmware_write",
    "set_firmware",
    "shutdown_console",
    "format_sd",
    "phantom_enable",
    "enable_phantom",
    "sample_rate_set",
    "set_sample_rate",
    "clock_write",
    "clock_set",
    "set_clock",
    "approval_token",
    "webui",
    "database",
    "backend_service",
    "microservice",
    "remote_mcp",
    "chatgpt_tunnel",
}


def test_stable_launcher_is_declared_as_project_console_script():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["m32-bridge"] == "m32_bridge.__main__:main"


def test_package_entrypoint_dispatches_to_existing_cli_main():
    assert package_main.main is cli.main


def test_cli_public_subcommands_do_not_expose_forbidden_runtime_surfaces():
    parser = cli._build_parser()
    subparser_actions = [action for action in parser._actions if isinstance(action, argparse._SubParsersAction)]
    subcommands = set(subparser_actions[0].choices) if subparser_actions else set()
    surface = " ".join(sorted(subcommands)).lower()

    for term in FORBIDDEN_SURFACE_TERMS:
        assert term not in surface


def test_mcp_tool_names_and_public_handler_parameters_do_not_expose_forbidden_surfaces():
    registry = ToolRegistry()
    register_mvp_tools(registry)

    for name in registry.names():
        spec = registry.get(name)
        public_parameters = [
            parameter_name
            for parameter_name in inspect.signature(spec.handler).parameters
            if parameter_name
            not in {
                "client",
                "store",
                "controller",
                "connection",
                "audit_writer",
            }
        ]
        surface = " ".join([name, *public_parameters]).lower()
        for term in FORBIDDEN_SURFACE_TERMS:
            assert term not in surface


def test_runtime_startup_remains_local_without_webui_database_service_or_production_claims():
    result = package_main.startup_verification()

    assert result["local_process"] is True
    assert result["webui"] is False
    assert result["database"] is False
    assert result["microservices"] is False
    assert result["network_side_effects"] is False
    assert result["public_network_exposure"] is False
    assert result["production_live_ready"] is False
