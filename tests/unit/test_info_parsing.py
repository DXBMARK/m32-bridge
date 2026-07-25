from __future__ import annotations

from m32_bridge.osc.codec import OscMessage
from m32_bridge.osc.discovery import discover_identity, parse_info_payload


class InfoTransport:
    host = "192.168.8.88"
    port = 10023

    def __init__(self, *arguments: object) -> None:
        self.arguments = arguments
        self.requests: list[str] = []

    def request(self, address: str, *args: object) -> OscMessage:
        self.requests.append(address)
        return OscMessage(address, self.arguments)


def test_parse_info_payload_with_three_values():
    parsed = parse_info_payload(("M32", "4.06", 123))

    assert parsed["model"] == "M32"
    assert parsed["firmware_version"] == "4.06"
    assert parsed["revision"] == 123
    assert parsed["product_name"] is None
    assert parsed["console_api_version"] is None
    assert parsed["extra"] == []


def test_parse_info_payload_with_patrick_x32_emulator_four_values():
    parsed = parse_info_payload(("V2.07", "X32 Emulator", "X32", "4.06"))

    assert parsed["firmware_version"] == "V2.07"
    assert parsed["product_name"] == "X32 Emulator"
    assert parsed["model"] == "X32"
    assert parsed["console_api_version"] == "4.06"
    assert parsed["revision"] is None
    assert parsed["extra"] == []


def test_discover_identity_preserves_extra_info_values_without_crashing():
    transport = InfoTransport("V2.07", "X32 Emulator", "X32", "4.06", "rev", "extra")

    discovery = discover_identity(transport, target_kind="external_emulator")

    assert discovery.info_raw == ["V2.07", "X32 Emulator", "X32", "4.06", "rev", "extra"]
    assert discovery.info_fields["revision"] == "rev"
    assert discovery.info_fields["extra"] == ["extra"]
    assert discovery.identity.model == "X32"
    assert discovery.identity.firmware_version == "V2.07"
    assert discovery.identity.endpoint_host == "192.168.8.88"
    assert discovery.identity.endpoint_port == 10023
    assert discovery.identity.hardware_verified is False
    assert transport.requests == ["/info"]
