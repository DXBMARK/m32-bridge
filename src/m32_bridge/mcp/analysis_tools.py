"""Read-only analysis MCP tools."""

from __future__ import annotations

from m32_bridge.core.models import RuntimeMode
from m32_bridge.diagnostics.preflight import run_event_preflight
from m32_bridge.diagnostics.rta import analyze_rta, scan_rta_sources
from m32_bridge.mcp.server import ToolRegistry, ToolSpec
from m32_bridge.osc.client import OscClient


def m32_event_preflight(client: OscClient, event_profile: dict[str, object] | str | None = None) -> dict[str, object]:
    return run_event_preflight(client, event_profile=event_profile).to_dict()


def m32_analyze_gain_staging(client: OscClient) -> dict[str, object]:
    return {"findings": [f.to_dict() for f in run_event_preflight(client).findings if f.category == "gain"], "proposal_created": False}


def m32_analyze_routing(_client: OscClient) -> dict[str, object]:
    return {"findings": [], "proposal_created": False}


def m32_analyze_processing(_client: OscClient) -> dict[str, object]:
    return {"findings": [], "proposal_created": False}


def m32_analyze_rta(
    client: OscClient,
    *,
    mode: str = "current",
    runtime_mode: RuntimeMode | str = RuntimeMode.OBSERVE,
    sources: list[str] | None = None,
    event_profile: dict[str, object] | str | None = None,
    acquisition_settings: dict[str, object] | None = None,
) -> dict[str, object]:
    if mode == "current":
        return analyze_rta(client, event_profile=event_profile, acquisition_settings=acquisition_settings).to_dict()
    if mode != "scan":
        return {
            "status": "denied",
            "reason": "VALIDATION_ERROR",
            "message": "mode must be current or scan",
            "proposal_created": False,
            "write_operations": [],
        }
    if not sources:
        return {
            "status": "denied",
            "reason": "CONFIGURED_SOURCES_REQUIRED",
            "message": "scan mode requires an explicit configured sources list",
            "configured_sources": [],
            "proposal_created": False,
            "write_operations": [],
        }
    return scan_rta_sources(client, sources=sources, runtime_mode=runtime_mode, event_profile=event_profile).to_dict()


def m32_recommend_event_setup(client: OscClient, event_profile: dict[str, object] | str | None = None) -> dict[str, object]:
    result = run_event_preflight(client, event_profile=event_profile)
    return {"recommendations": result.recommendations, "proposal_created": False, "write_operations": []}


ANALYSIS_TOOL_HANDLERS = {
    "m32_event_preflight": m32_event_preflight,
    "m32_analyze_gain_staging": m32_analyze_gain_staging,
    "m32_analyze_routing": m32_analyze_routing,
    "m32_analyze_processing": m32_analyze_processing,
    "m32_analyze_rta": m32_analyze_rta,
    "m32_recommend_event_setup": m32_recommend_event_setup,
}


def register_analysis_tools(registry: ToolRegistry) -> None:
    for name, handler in ANALYSIS_TOOL_HANDLERS.items():
        registry.register(
            ToolSpec(
                name=name,
                read_only=name != "m32_analyze_rta",
                sends_osc_writes=name == "m32_analyze_rta",
                handler=handler,
            )
        )
