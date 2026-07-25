"""Clock, AES50, and card sync readiness checks."""

from __future__ import annotations

from m32_bridge.diagnostics.findings import DiagnosticFinding, evidence_path


def check_clock_sync(clock_sync: dict[str, str]) -> list[DiagnosticFinding]:
    findings: list[DiagnosticFinding] = []
    checks = {
        "clock_rate": "48k",
        "aes50_a": "locked",
        "expansion_card_sync": "locked",
    }
    for key, expected in checks.items():
        observed = clock_sync.get(key)
        if observed != expected:
            findings.append(
                DiagnosticFinding(
                    finding_id=f"sync_{key}",
                    severity="BLOCKER",
                    category="sync",
                    source="console",
                    affected_paths=[f"/-stat/{key}"],
                    summary=f"{key} is {observed}, expected {expected}",
                    evidence=evidence_path(f"/-stat/{key}", observed, expected),
                    recommendation="Resolve clock or digital sync manually, then rerun preflight.",
                    blocks_readiness=True,
                )
            )
    return findings

