"""Read-only device identity classification for local runtime setup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from m32_bridge.diagnostics.runtime_output import runtime_output, unsupported_or_timeout_path


DEVICE_CLASSIFICATIONS = {
    "NOT_CONFIGURED",
    "EMULATOR_CONNECTED",
    "CONNECTED_UNVERIFIED",
    "HARDWARE_CANDIDATE",
    "HARDWARE_VERIFIED",
}


@dataclass(frozen=True)
class DeviceIdentityReport:
    classification: str
    connected: bool
    configured_host: str | None
    configured_port: int | None
    response_address: Any = None
    latency_ms: float | None = None
    model_family: str | None = None
    firmware_version: str | None = None
    api_version: str | None = None
    capability_map: dict[str, str] = field(default_factory=dict)
    unsupported_or_timeout_paths: list[dict[str, Any]] = field(default_factory=list)
    usb_evidence: dict[str, Any] | None = None
    hardware_verified: bool = False
    production_live_ready: bool = False
    osc_writes_sent: int = 0


def classify_device(
    *,
    configured_host: str | None,
    configured_port: int | None,
    intended_target_type: str = "unknown",
    info_probe: Mapping[str, Any] | None,
    optional_capability_results: list[Mapping[str, Any]] | None = None,
    usb_evidence: Mapping[str, Any] | None = None,
    hardware_acceptance_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    optional_paths = _unsupported_or_timeout_paths(optional_capability_results or [])
    if not configured_host or configured_port is None:
        return runtime_output(
            ok=False,
            status="NOT_CONFIGURED",
            error_code="NO_CONSOLE_HOST",
            message="No console host is configured. Run m32-bridge setup.",
            configured_host=None,
            configured_port=None,
            attempted_path="/info",
            latency_ms=None,
            exception_type=None,
            connected=False,
            classification="NOT_CONFIGURED",
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
            data={},
            recommendations=["Run m32-bridge setup"],
        )

    probe = dict(info_probe or {})
    connected = bool(probe.get("connected")) or probe.get("udp_info_probe_result") == "CONNECTED"
    latency_ms = probe.get("latency_ms")
    exception_type = probe.get("exception_type")
    response_address = probe.get("response_address")
    attempted_path = str(probe.get("attempted_path") or "/info")
    info_raw = list(probe.get("info_raw") or [])
    model_family = str(info_raw[0]) if len(info_raw) >= 1 else None
    firmware_version = str(info_raw[1]) if len(info_raw) >= 2 else None
    api_version = str(info_raw[2]) if len(info_raw) >= 3 else None

    if not connected:
        return runtime_output(
            ok=False,
            status="NOT_CONNECTED",
            error_code="NOT_CONNECTED",
            message="The configured endpoint did not respond to /info.",
            configured_host=configured_host,
            configured_port=configured_port,
            attempted_path=attempted_path,
            latency_ms=latency_ms,
            exception_type=exception_type,
            response_address=response_address,
            connected=False,
            classification=None,
            osc_writes_sent=0,
            hardware_verified=False,
            production_live_ready=False,
            unsupported_or_timeout_paths=optional_paths,
            data={},
            recommendations=["Check the configured endpoint and run m32-bridge setup."],
        )

    hardware_verified = _has_fixture_hardware_acceptance(intended_target_type, hardware_acceptance_evidence)
    classification = _classification(
        intended_target_type=intended_target_type,
        hardware_verified=hardware_verified,
        usb_evidence=usb_evidence,
    )
    status = "PARTIAL_CAPABILITY" if optional_paths else "CONNECTED"
    error_code = "PARTIAL_CAPABILITY" if optional_paths else None
    data: dict[str, Any] = {
        "intended_target_type": intended_target_type,
        "model_family": model_family,
        "firmware_version": firmware_version,
        "api_version": api_version,
    }
    if usb_evidence is not None:
        data["usb_evidence"] = dict(usb_evidence)
    if hardware_acceptance_evidence is not None:
        data["hardware_acceptance_evidence"] = dict(hardware_acceptance_evidence)

    return runtime_output(
        ok=True,
        status=status,
        error_code=error_code,
        message="Device identity classified from read-only evidence.",
        configured_host=configured_host,
        configured_port=configured_port,
        attempted_path=attempted_path,
        latency_ms=latency_ms,
        exception_type=exception_type,
        response_address=response_address,
        connected=True,
        classification=classification,
        osc_writes_sent=0,
        hardware_verified=hardware_verified,
        production_live_ready=False,
        unsupported_or_timeout_paths=optional_paths,
        data=data,
        recommendations=_recommendations(classification, optional_paths),
    )


def _classification(
    *,
    intended_target_type: str,
    hardware_verified: bool,
    usb_evidence: Mapping[str, Any] | None,
) -> str:
    if intended_target_type == "emulator":
        return "EMULATOR_CONNECTED"
    if hardware_verified:
        return "HARDWARE_VERIFIED"
    if intended_target_type == "hardware" and usb_evidence is not None:
        return "HARDWARE_CANDIDATE"
    return "CONNECTED_UNVERIFIED"


def _has_fixture_hardware_acceptance(
    intended_target_type: str,
    evidence: Mapping[str, Any] | None,
) -> bool:
    return bool(
        intended_target_type == "hardware"
        and evidence
        and evidence.get("source") == "fixture"
        and evidence.get("physical_suite_passed") is True
        and evidence.get("read_only") is True
        and evidence.get("writes_sent") == 0
    )


def _unsupported_or_timeout_paths(results: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        unsupported_or_timeout_path(
            path=str(item["path"]),
            status=str(item["status"]),
            reason=item.get("reason"),
            exception_type=item.get("exception_type"),
        )
        for item in results
    ]


def _recommendations(classification: str, optional_paths: list[dict[str, Any]]) -> list[str]:
    recommendations = ["Keep hardware_verified=false until hardware acceptance evidence exists."]
    if classification == "EMULATOR_CONNECTED":
        recommendations.append("Treat emulator evidence as development-only.")
    if optional_paths:
        recommendations.append("Review optional capability limitations; /info connectivity remains valid.")
    return recommendations
