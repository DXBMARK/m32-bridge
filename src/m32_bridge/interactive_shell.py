"""Optional local interactive slash-command shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from m32_bridge.diagnostics.mcp_guidance import build_mcp_launch_guidance
from m32_bridge.diagnostics.runtime_output import runtime_output


@dataclass
class LocalShellState:
    write_locked: bool = True


SHELL_COMMAND_EQUIVALENTS = {
    "/help": "m32-bridge help",
    "/runsetup": "m32-bridge setup",
    "/getinfo": "m32-bridge get-info",
    "/config": "m32-bridge config show",
    "/test": "m32-bridge get-info",
    "/doctor": "m32-bridge doctor-runtime",
    "/detect": "m32-bridge detect-device",
    "/mcp": "m32-bridge mcp-server --help",
    "/claude": "m32-bridge mcp guidance",
    "/mode": "m32-bridge mode",
    "/lock": "m32-bridge lock",
    "/unlock": "m32-bridge unlock",
    "/exit": "exit",
}


def non_interactive_shell_required(*, stdin_is_tty: bool) -> dict[str, Any]:
    return runtime_output(
        ok=False,
        status="NON_INTERACTIVE_SHELL_REQUIRED",
        error_code="NON_INTERACTIVE_SHELL_REQUIRED",
        message="The interactive shell requires an interactive terminal.",
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data={"stdin_is_tty": stdin_is_tty, "started": False},
        recommendations=["m32-bridge setup", "m32-bridge health", "m32-bridge mcp-server"],
    ) | {"started": False}


def parse_slash_command(command: str) -> dict[str, Any]:
    text = command.strip()
    if text.startswith("/config set host "):
        host = text.removeprefix("/config set host ").strip()
        return _parsed(text, f"m32-bridge config set --host {host}")
    if text.startswith("/config set port "):
        port = text.removeprefix("/config set port ").strip()
        return _parsed(text, f"m32-bridge config set --port {port}")
    if text in SHELL_COMMAND_EQUIVALENTS:
        return _parsed(text, SHELL_COMMAND_EQUIVALENTS[text])
    return runtime_output(
        ok=False,
        status="UNKNOWN_SHELL_COMMAND",
        error_code="UNKNOWN_SHELL_COMMAND",
        message="Unknown shell command.",
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
    ) | _surface_flags() | {"slash_command": text, "mapped_cli_equivalent": None}


def dispatch_slash_command(
    command: str,
    *,
    shell_state: LocalShellState | None = None,
    host: str | None = None,
    port: int | None = None,
    target_type: str = "unknown",
    connected: bool = False,
    stale: bool = False,
    reconciled: bool = False,
    emergency_active: bool = False,
    policy_allows_write_readiness: bool = False,
) -> dict[str, Any]:
    text = command.strip()
    state = shell_state or LocalShellState()
    if text == "/help":
        return shell_help()
    if text == "/exit":
        return _ok("EXIT", data={"exit": True}) | {"exit": True}
    if text == "/lock":
        state.write_locked = True
        return _ok("LOCKED", data={"write_locked": True})
    if text == "/unlock":
        denial = _unlock_denial(
            connected=connected,
            stale=stale,
            reconciled=reconciled,
            emergency_active=emergency_active,
            policy_allows_write_readiness=policy_allows_write_readiness,
        )
        if denial is not None:
            state.write_locked = True
            return runtime_output(
                ok=False,
                status=denial,
                error_code=denial,
                message="Unlock denied by local write-governance checks.",
                attempted_path=None,
                latency_ms=None,
                exception_type=None,
                osc_writes_sent=0,
                hardware_verified=False,
                production_live_ready=False,
                data={"write_locked": True},
            ) | _surface_flags()
        state.write_locked = False
        return _ok("UNLOCKED", data={"write_locked": False})
    if text in {"/mcp", "/claude"}:
        return _ok("MCP_GUIDANCE", data=build_mcp_launch_guidance(host_app="claude" if text == "/claude" else "generic_ai"))
    if text == "/config":
        return _ok("CONFIG", data={"mapped_cli_equivalent": "m32-bridge config show"})
    if text in {"/runsetup", "/getinfo", "/test", "/doctor", "/detect"}:
        return _dispatch_read_only(text, host=host, port=port, target_type=target_type)
    if text == "/mode":
        return _ok("MODE", data={"runtime_mode": "OBSERVE"})
    return parse_slash_command(text)


def shell_help() -> dict[str, Any]:
    commands = ", ".join(SHELL_COMMAND_EQUIVALENTS)
    text = (
        "Slash commands work only inside the m32-bridge interactive shell; "
        "they are not standalone OS terminal commands. Available commands: "
        f"{commands}"
    )
    return _ok("HELP", data={"text": text}) | {"text": text}


def interactive_shell_loop() -> int:
    state = LocalShellState()
    while True:
        try:
            command = input("m32-bridge> ")
        except EOFError:
            return 0
        payload = dispatch_slash_command(command, shell_state=state)
        print(payload)
        if payload.get("exit") is True:
            return 0


def _dispatch_read_only(command: str, *, host: str | None, port: int | None, target_type: str) -> dict[str, Any]:
    if command == "/runsetup":
        from m32_bridge.cli import setup_runtime

        return setup_runtime(host=host, port=port, target_type=target_type, save=False)
    if command in {"/getinfo", "/test"}:
        from m32_bridge.diagnostics.runtime import setup_info_probe

        probe = setup_info_probe(host, port)
        return runtime_output(
            ok=probe["udp_info_probe_result"] == "CONNECTED",
            status=probe["udp_info_probe_result"],
            error_code=None if probe["udp_info_probe_result"] == "CONNECTED" else "NOT_CONNECTED",
            configured_host=host,
            configured_port=port,
            attempted_path="/info",
            latency_ms=probe["latency_ms"],
            exception_type=probe["exception_type"],
            response_address=probe["response_address"],
            connected=probe["udp_info_probe_result"] == "CONNECTED",
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
        )
    if command == "/doctor":
        from m32_bridge.cli import doctor_runtime_command

        return doctor_runtime_command(host=host, port=port, timeout=0.5)
    if command == "/detect":
        from m32_bridge.cli import detect_device_runtime

        return detect_device_runtime(host=host, port=port, target_type=target_type)
    return _ok("NOOP")


def _unlock_denial(
    *,
    connected: bool,
    stale: bool,
    reconciled: bool,
    emergency_active: bool,
    policy_allows_write_readiness: bool,
) -> str | None:
    if not connected:
        return "UNLOCK_DENIED_DISCONNECTED"
    if stale:
        return "UNLOCK_DENIED_STALE"
    if not reconciled:
        return "UNLOCK_DENIED_UNRECONCILED"
    if emergency_active:
        return "UNLOCK_DENIED_EMERGENCY"
    if not policy_allows_write_readiness:
        return "UNLOCK_DENIED_POLICY"
    return None


def _parsed(command: str, equivalent: str) -> dict[str, Any]:
    return _ok("PARSED", data={"slash_command": command, "mapped_cli_equivalent": equivalent}) | {
        "slash_command": command,
        "mapped_cli_equivalent": equivalent,
    }


def _ok(status: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return runtime_output(
        ok=True,
        status=status,
        error_code=None,
        attempted_path=None,
        latency_ms=None,
        exception_type=None,
        osc_writes_sent=0,
        hardware_verified=False,
        production_live_ready=False,
        data=data or {},
    ) | _surface_flags()


def _surface_flags() -> dict[str, Any]:
    return {
        "raw_osc_available": False,
        "arbitrary_path_available": False,
        "shell_execution_available": False,
    }
