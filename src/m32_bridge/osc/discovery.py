"""Identity and capability discovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from m32_bridge.core.models import ConsoleIdentity, StateValue, VerificationState
from m32_bridge.osc.transport import OscTransport


@dataclass(frozen=True)
class DiscoveryResult:
    identity: ConsoleIdentity
    write_locked: bool
    info_raw: list[object]
    info_fields: dict[str, object | None]


def parse_info_payload(arguments: list[object] | tuple[object, ...]) -> dict[str, object | None]:
    values = list(arguments)
    if len(values) >= 4:
        return {
            "firmware_version": values[0],
            "product_name": values[1],
            "model": values[2],
            "console_api_version": values[3],
            "revision": values[4] if len(values) > 4 else None,
            "extra": values[5:] if len(values) > 5 else [],
        }
    return {
        "model": values[0] if len(values) > 0 else None,
        "firmware_version": values[1] if len(values) > 1 else None,
        "revision": values[2] if len(values) > 2 else None,
        "product_name": None,
        "console_api_version": None,
        "extra": values[3:] if len(values) > 3 else [],
    }


def discover_identity(transport: OscTransport, target_kind: str = "fake_m32") -> DiscoveryResult:
    message = transport.request("/info")
    info_raw = list(message.arguments)
    info_fields = parse_info_payload(info_raw)
    model = info_fields.get("model") or "unknown"
    firmware = info_fields.get("firmware_version")
    firmware_status = "known" if firmware else "unknown"
    environment = "emulator" if target_kind in {"fake_m32", "external_emulator"} else "hardware-unverified"
    identity = ConsoleIdentity(
        identity_id=f"{target_kind}:{model}:{firmware}",
        model=str(model),
        firmware_version=str(firmware),
        firmware_status=firmware_status,
        endpoint_host=transport.host,
        endpoint_port=transport.port,
        source=target_kind,
        observed_at=datetime.now(UTC),
        environment_label=environment,
        verification_state=VerificationState.EMULATOR if environment == "emulator" else VerificationState.HARDWARE_UNVERIFIED,
        hardware_verified=False,
    )
    return DiscoveryResult(identity=identity, write_locked=firmware_status != "known", info_raw=info_raw, info_fields=info_fields)


def read_state_value(transport: OscTransport, path: str, source: str = "fake_m32") -> StateValue:
    message = transport.request(path)
    value = message.arguments[0]
    revision = int(message.arguments[1]) if len(message.arguments) > 1 and isinstance(message.arguments[1], int) else 0
    now = datetime.now(UTC)
    return StateValue(
        path=path,
        raw_value=value,
        native_value=value,
        display_value=f"{value:+.1f} dB" if isinstance(value, float) else str(value),
        unit="dB" if isinstance(value, float) else None,
        value_type=type(value).__name__,
        source=source,
        revision=revision,
        observed_at=now,
        fresh_until=now + timedelta(seconds=2),
        confidence=1.0,
        stale=False,
        partial=False,
        support_status="supported",
        environment_label="emulator" if source in {"fake_m32", "external_emulator"} else "hardware-unverified",
    )
