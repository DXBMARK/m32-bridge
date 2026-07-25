"""Diagnostic finding model and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiagnosticFinding:
    finding_id: str
    severity: str
    category: str
    source: str
    affected_paths: list[str]
    summary: str
    evidence: dict[str, object] = field(default_factory=dict)
    recommendation: str | None = None
    blocks_readiness: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "category": self.category,
            "source": self.source,
            "affected_paths": self.affected_paths,
            "summary": self.summary,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "blocks_readiness": self.blocks_readiness,
        }


def evidence_path(path: str, observed: object, expected: object | None = None) -> dict[str, object]:
    result = {"path": path, "observed": observed}
    if expected is not None:
        result["expected"] = expected
    return result

