"""JSON snapshot helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from m32_bridge.core.proposals import digest_payload


def snapshot_checksum(snapshot_without_checksum: dict[str, Any]) -> str:
    return digest_payload(snapshot_without_checksum)


def build_snapshot(
    *,
    snapshot_id: str,
    identity: dict[str, Any],
    firmware: dict[str, Any],
    state_values: list[dict[str, Any]],
    missing_paths: list[str] | None = None,
    critical_stale_paths: list[str] | None = None,
    environment_label: str,
) -> dict[str, Any]:
    snapshot = {
        "schema_version": "1.0.0",
        "snapshot_id": snapshot_id,
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "identity": identity,
        "firmware": firmware,
        "complete": not missing_paths and not critical_stale_paths,
        "environment_label": environment_label,
        "state_values": state_values,
        "missing_paths": missing_paths or [],
        "critical_stale_paths": critical_stale_paths or [],
    }
    snapshot["checksum"] = snapshot_checksum(snapshot)
    return snapshot

