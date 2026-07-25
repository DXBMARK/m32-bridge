"""OSC UDP transport with endpoint validation and timeout handling."""

from __future__ import annotations

import socket
from dataclasses import dataclass

from m32_bridge.osc.codec import OscMessage, pack_message, unpack_message


class OscTimeoutError(TimeoutError):
    pass


class OscEndpointError(RuntimeError):
    pass


@dataclass
class OscTransport:
    host: str
    port: int
    timeout: float = 0.5

    def request(self, address: str, *args: object) -> OscMessage:
        packet = pack_message(address, *args)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout)
            sock.sendto(packet, (self.host, self.port))
            try:
                response, endpoint = sock.recvfrom(65535)
            except TimeoutError as exc:
                raise OscTimeoutError("OSC request timed out") from exc
        if endpoint[0] != self.host or endpoint[1] != self.port:
            raise OscEndpointError("reply source endpoint mismatch")
        return unpack_message(response)

    def send(self, address: str, *args: object) -> None:
        packet = pack_message(address, *args)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(packet, (self.host, self.port))
