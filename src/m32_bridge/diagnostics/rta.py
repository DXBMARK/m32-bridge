"""Read-only RTA analysis."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable

from m32_bridge.core.models import RuntimeMode
from m32_bridge.diagnostics.findings import DiagnosticFinding
from m32_bridge.osc.client import OscClient


@dataclass(frozen=True)
class RtaAnalysisResult:
    source_identity: dict[str, object]
    acquisition_settings: dict[str, object]
    band_summary: dict[str, object]
    bands: list[float]
    findings: list[DiagnosticFinding]
    confidence: str
    limitations: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "source_identity": self.source_identity,
            "acquisition_settings": self.acquisition_settings,
            "band_summary": self.band_summary,
            "bands": self.bands,
            "findings": [finding.to_dict() for finding in self.findings],
            "confidence": self.confidence,
            "limitations": self.limitations,
            "no_per_channel_spectra": True,
            "proposal_created": False,
            "write_operations": [],
        }


@dataclass(frozen=True)
class RtaScanResult:
    status: str
    runtime_mode: str
    configured_sources: list[str]
    original_source: str | None
    scanned_sources: list[dict[str, object]]
    restore_attempts: list[dict[str, object]]
    reason: str | None = None
    hardware_verified: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "runtime_mode": self.runtime_mode,
            "configured_sources": self.configured_sources,
            "original_source": self.original_source,
            "scanned_sources": self.scanned_sources,
            "restore_attempts": self.restore_attempts,
            "hardware_verified": self.hardware_verified,
            "proposal_created": False,
            "write_operations": [],
        }


def analyze_rta(
    client: OscClient,
    event_profile: dict[str, object] | str | None = None,
    acquisition_settings: dict[str, object] | None = None,
) -> RtaAnalysisResult:
    del event_profile
    raw_rta = client.rta()
    source = _normalize_source(raw_rta.get("source"))
    bands = [float(value) for value in raw_rta.get("bands", [])]
    confidence = "normal" if source else "limited"
    source_identity = {
        "source": source,
        "status": "known" if source else "unknown",
        "source_path": "/rta/source",
        "bands_path": "/rta/bands",
        "hardware_verified": False,
    }
    settings = {
        "source": source,
        "source_path": "/rta/source",
        "band_count": len(bands),
        "frequency_bins": len(bands),
        "freshness": "current_read",
        "confidence": confidence,
        "simultaneous_per_channel_spectra": False,
    }
    if acquisition_settings:
        read_derived_keys = {
            "source",
            "source_path",
            "band_count",
            "frequency_bins",
            "freshness",
            "confidence",
            "simultaneous_per_channel_spectra",
        }
        settings.update({key: value for key, value in acquisition_settings.items() if key not in read_derived_keys})

    findings = [
        DiagnosticFinding(
            finding_id="rta_no_per_channel_spectra",
            severity="INFO",
            category="rta",
            source="console",
            affected_paths=["/rta/source", "/rta/bands"],
            summary="RTA simultaneous per-channel spectra are not available",
            evidence={"simultaneous_per_channel_spectra": False},
        )
    ]
    if source is None:
        findings.append(
            DiagnosticFinding(
                finding_id="rta_source_unknown",
                severity="WARNING",
                category="rta",
                source="console",
                affected_paths=["/rta/source"],
                summary="RTA source is unknown; conclusions are limited",
                evidence={"source": None, "confidence": "limited"},
            )
        )

    return RtaAnalysisResult(
        source_identity=source_identity,
        acquisition_settings=settings,
        band_summary=_summarize_bands(bands),
        bands=bands,
        findings=findings,
        confidence=confidence,
        limitations=[
            "simultaneous per-channel spectra are not available",
            "RTA analysis is read-only and does not change source, gain, phantom, fader, or routing settings",
            "Fake M32 results do not provide hardware verification",
        ],
    )


def scan_rta_sources(
    client: OscClient,
    sources: list[str],
    runtime_mode: RuntimeMode | str,
    event_profile: dict[str, object] | str | None = None,
    cancellation: Callable[[], bool] | object | None = None,
) -> RtaScanResult:
    del event_profile
    mode = RuntimeMode(runtime_mode)
    configured_sources = _configured_sources(sources)
    if mode is not RuntimeMode.SOUNDCHECK:
        return RtaScanResult(
            status="denied",
            reason="EMERGENCY_LOCKED" if mode is RuntimeMode.EMERGENCY else "SOUNDCHECK_REQUIRED",
            runtime_mode=mode.value,
            configured_sources=configured_sources,
            original_source=None,
            scanned_sources=[],
            restore_attempts=[],
        )
    if not configured_sources:
        return RtaScanResult(
            status="denied",
            reason="CONFIGURED_SOURCES_REQUIRED",
            runtime_mode=mode.value,
            configured_sources=[],
            original_source=None,
            scanned_sources=[],
            restore_attempts=[],
        )

    original_source = _normalize_source(client.rta().get("source"))
    scanned_sources: list[dict[str, object]] = []
    restore_attempts: list[dict[str, object]] = []
    status = "success"
    reason: str | None = None

    try:
        for source in configured_sources:
            if _is_cancelled(cancellation):
                status = "cancelled"
                reason = "CANCELLED"
                break
            _set_rta_source(client, source)
            try:
                analysis = analyze_rta(client).to_dict()
            except Exception as exc:
                scanned_sources.append({"source": source, "status": "failed", "error": type(exc).__name__})
                status = "failed"
                reason = "SCAN_FAILED"
                break
            scanned_sources.append(
                {
                    "source": source,
                    "status": "scanned",
                    "band_count": analysis["acquisition_settings"]["band_count"],
                    "confidence": analysis["confidence"],
                    "no_per_channel_spectra": analysis["no_per_channel_spectra"],
                }
            )
    finally:
        restore_status = "skipped"
        if original_source is not None:
            try:
                _set_rta_source(client, original_source)
                restore_status = "restored"
            except Exception:
                restore_status = "failed"
                status = "failed"
                reason = "RESTORE_FAILED"
        restore_attempts.append({"source": original_source, "status": restore_status})

    return RtaScanResult(
        status=status,
        reason=reason,
        runtime_mode=mode.value,
        configured_sources=configured_sources,
        original_source=original_source,
        scanned_sources=scanned_sources,
        restore_attempts=restore_attempts,
    )


def _normalize_source(source: object) -> str | None:
    if source is None:
        return None
    text = str(source).strip()
    if not text or text.upper() == "UNSUPPORTED_PATH":
        return None
    return text


def _configured_sources(sources: list[str]) -> list[str]:
    return [source.strip() for source in sources if isinstance(source, str) and source.strip()]


def _set_rta_source(client: OscClient, source: str) -> None:
    reply = client.transport.request("/rta/source/set", source)
    if not reply.arguments or str(reply.arguments[0]) != "ok":
        raise RuntimeError("RTA source selection failed")


def _is_cancelled(cancellation: Callable[[], bool] | object | None) -> bool:
    if cancellation is None:
        return False
    if callable(cancellation):
        return bool(cancellation())
    is_set = getattr(cancellation, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    return False


def _summarize_bands(bands: list[float]) -> dict[str, object]:
    if not bands:
        return {"count": 0, "min_db": None, "max_db": None, "average_db": None}
    return {
        "count": len(bands),
        "min_db": min(bands),
        "max_db": max(bands),
        "average_db": mean(bands),
    }
