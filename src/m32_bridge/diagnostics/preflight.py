"""Event preflight and setup recommendation analysis."""

from __future__ import annotations

from dataclasses import dataclass

from m32_bridge.config.event_profile import load_event_profile
from m32_bridge.diagnostics.clock import check_clock_sync
from m32_bridge.diagnostics.findings import DiagnosticFinding
from m32_bridge.osc.client import OscClient
from m32_bridge.osc.discovery import discover_identity, read_state_value


@dataclass(frozen=True)
class PreflightResult:
    findings: list[DiagnosticFinding]
    recommendations: list[str]

    @property
    def blockers(self) -> list[DiagnosticFinding]:
        return [finding for finding in self.findings if finding.blocks_readiness]

    def to_dict(self) -> dict[str, object]:
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "blockers": [finding.to_dict() for finding in self.blockers],
            "recommendations": self.recommendations,
            "write_ready": not self.blockers,
            "proposal_created": False,
        }


def run_event_preflight(client: OscClient, event_profile: dict[str, object] | str | None = None) -> PreflightResult:
    findings: list[DiagnosticFinding] = []
    profile = load_event_profile(event_profile)
    discovery = discover_identity(client.transport)
    if discovery.identity.firmware_status != "known":
        findings.append(
            DiagnosticFinding(
                finding_id="identity_firmware",
                severity="BLOCKER",
                category="identity",
                source="console",
                affected_paths=["/info"],
                summary="Firmware is unknown or unsupported",
                evidence={"firmware_status": discovery.identity.firmware_status},
                blocks_readiness=True,
            )
        )
    findings.extend(check_clock_sync(client.clock_sync()))
    gain = read_state_value(client.transport, "/ch/01/headamp/gain")
    if float(gain.native_value) > 6.0:
        findings.append(
            DiagnosticFinding(
                finding_id="gain_ch01_high",
                severity="WARNING",
                category="gain",
                source="console",
                affected_paths=["/ch/01/headamp/gain"],
                summary="Channel 1 headamp gain is high for the seeded event profile",
                evidence={"observed": gain.display_value, "path": gain.path},
                recommendation="Review gain during soundcheck before creating a proposal.",
            )
        )
    rta = client.rta()
    if not rta.get("source"):
        findings.append(
            DiagnosticFinding(
                finding_id="rta_source_unknown",
                severity="BLOCKER",
                category="rta",
                source="console",
                affected_paths=["/rta/source"],
                summary="RTA source is unknown",
                blocks_readiness=True,
            )
        )
    measurement_recommendations = _measurement_microphone_findings(profile, rta)
    findings.extend(measurement_recommendations[0])
    recommendations = [
        "Keep recommendations separate from execution.",
        "Create a proposal only after reviewing blockers and warnings.",
        *measurement_recommendations[1],
    ]
    return PreflightResult(findings=findings, recommendations=recommendations)


def _measurement_microphone_findings(
    profile: dict[str, object] | None, rta: dict[str, object]
) -> tuple[list[DiagnosticFinding], list[str]]:
    if profile is None:
        return [], []

    measurement = profile["measurement_microphone"]
    if not isinstance(measurement, dict):
        return [], []

    defined = bool(measurement["defined"])
    phantom_policy = str(measurement["phantom_policy"])
    if not defined:
        return [
            DiagnosticFinding(
                finding_id="measurement_microphone_deferred",
                severity="WARNING",
                category="measurement_microphone",
                source="event_profile",
                affected_paths=[],
                summary="Measurement microphone is deferred in the event profile",
                evidence={"defined": False},
                recommendation="Define the measurement microphone explicitly before relying on RTA-assisted setup decisions.",
            )
        ], ["Measurement microphone is incomplete; no channel was guessed from labels or names."]

    channel = int(measurement["channel"])
    protected_paths = [str(path) for path in profile.get("protected_paths", [])]
    channel_prefix = f"/ch/{channel:02d}"
    protected_sends = [path for path in protected_paths if path.startswith(f"{channel_prefix}/mix")]
    main_paths = [path for path in protected_paths if path.startswith("/main")]
    rta_eligible = bool(rta.get("source"))

    finding = DiagnosticFinding(
        finding_id="measurement_microphone_profile",
        severity="INFO",
        category="measurement_microphone",
        source="event_profile",
        affected_paths=[channel_prefix, *protected_sends, *main_paths],
        summary="Measurement microphone profile checked; phantom policy is manual advice only",
        evidence={
            "defined": True,
            "channel": channel,
            "main_excluded": bool(main_paths),
            "protected_sends_checked": protected_sends,
            "rta_eligible": rta_eligible,
            "phantom_policy": phantom_policy,
        },
        recommendation="Treat phantom power guidance as manual-only advice; do not create executable phantom operations.",
    )
    return [finding], ["Measurement microphone checks are advisory and do not create proposal write operations."]
