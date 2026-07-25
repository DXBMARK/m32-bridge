from __future__ import annotations

import re
from pathlib import Path

from m32_bridge.mcp.server import ToolRegistry, register_mvp_tools


CONTRACT_PATH = Path("specs/001-m32-mcp-bridge/contracts/mcp-tools.md")
PROHIBITED_PATTERNS = (
    "raw_osc",
    "send_raw_osc",
    "osc_raw",
    "arbitrary_path",
    "set_any_path",
    "execute_shell",
    "shell",
    "firmware_write",
    "set_firmware",
    "firmware",
    "shutdown",
    "shutdown_console",
    "sd_format",
    "sd_format",
    "format_sd",
    "phantom_enable",
    "enable_phantom",
    "sample_rate_set",
    "set_sample_rate",
    "clock_write",
    "clock_set",
    "set_clock",
    "approval_token",
)


def _declared_tools() -> set[str]:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"`(m32_[a-z0-9_]+)`", text))


def test_every_declared_mvp_tool_is_registered_in_registry():
    registry = ToolRegistry()
    register_mvp_tools(registry)

    assert _declared_tools() <= set(registry.names())


def test_no_prohibited_mcp_tools_are_exposed():
    registry = ToolRegistry()
    register_mvp_tools(registry)

    exposed = " ".join(registry.names()).lower()
    for pattern in PROHIBITED_PATTERNS:
        assert pattern not in exposed


def test_final_mcp_tool_surface_has_no_forbidden_schema_or_handler_parameters():
    registry = ToolRegistry()
    register_mvp_tools(registry)

    forbidden = set(PROHIBITED_PATTERNS)
    for name in registry.names():
        spec = registry.get(name)
        handler_text = " ".join([spec.name, spec.handler.__name__, " ".join(spec.handler.__annotations__)])
        parameter_text = " ".join(spec.handler.__code__.co_varnames[: spec.handler.__code__.co_argcount])
        surface = f"{handler_text} {parameter_text}".lower()
        for pattern in forbidden:
            assert pattern not in surface


def test_write_metadata_is_conservative_and_emergency_tools_do_not_write_osc():
    registry = ToolRegistry()
    register_mvp_tools(registry)

    for name in registry.names():
        spec = registry.get(name)
        assert not (spec.read_only and spec.sends_osc_writes)
        if name in {"m32_execute_proposal", "m32_rollback_proposal", "m32_analyze_rta"}:
            assert spec.read_only is False
            assert spec.sends_osc_writes is True
        if name in {"m32_lock_writes", "m32_unlock_writes", "m32_enter_emergency", "m32_exit_emergency_to_observe"}:
            assert spec.sends_osc_writes is False
