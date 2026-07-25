"""Project-owned deterministic Fake M32 UDP server."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from m32_bridge.fake_m32.failures import FailureProfile
from m32_bridge.fake_m32.meters import meter_fixture
from m32_bridge.fake_m32.node import node_children
from m32_bridge.fake_m32.rta import rta_bands, rta_source
from m32_bridge.fake_m32.sync_state import sync_state
from m32_bridge.osc.codec import OscCodecError, pack_message, unpack_message


@dataclass
class FakeM32State:
    model: str = "M32"
    firmware: str = "4.13"
    gain_db: float = 10.0
    revision: int = 1
    xremote_count: int = 0
    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.values.setdefault("/rta/source", rta_source())
        self.values.setdefault("/ch/01/headamp/gain", self.gain_db)
        self.values.setdefault("/ch/01/mix/fader", -10.0)
        self.values.setdefault("/ch/01/mix/on", True)
        self.values.setdefault("/ch/01/mix/01/level", -20.0)
        self.values.setdefault("/routing/in/01", "local")
        self.values.setdefault("/-stat/model", self.model)
        self.values.setdefault("/-stat/firmware", self.firmware)
        for key, value in sync_state().items():
            self.values.setdefault(f"/-stat/{key}", value)


class FakeM32Server:
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.state = FakeM32State()
        self.failures = FailureProfile()
        self.rta_band_failure_sources: set[str] = set()
        self.rta_restore_failure_sources: set[str] = set()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.write_packets: list[str] = []

    @property
    def address(self) -> tuple[str, int]:
        if self._sock is None:
            raise RuntimeError("server not started")
        return self._sock.getsockname()

    def start(self) -> "FakeM32Server":
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.05)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._sock:
            self._sock.close()

    def set_gain(self, gain_db: float, source: str = "manual") -> None:
        self.state.gain_db = gain_db
        self.state.revision += 1
        self.state.values["/ch/01/headamp/gain"] = gain_db
        self.state.values["/-stat/last_change_source"] = source

    def set_value(self, path: str, value: Any, source: str = "manual") -> None:
        self.state.revision += 1
        self.state.values[path] = value
        self.state.values["/-stat/last_change_source"] = source

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                packet, client = self._sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                break
            if self.failures.disconnect or self.failures.consume_drop():
                continue
            if self.failures.delayed_ms:
                time.sleep(self.failures.delayed_ms / 1000)
            if self.failures.consume_malformed():
                self._sock.sendto(b"bad", client)
                continue
            try:
                response = self._handle(packet)
            except OscCodecError:
                response = pack_message("/error", "MALFORMED_REPLY")
            if self.failures.consume_out_of_order():
                if response is not None:
                    time.sleep(self.failures.out_of_order_delay_ms / 1000)
                    self._sock.sendto(response, client)
                continue
            if response is not None:
                self._sock.sendto(response, client)
                if self.failures.consume_duplicate():
                    self._sock.sendto(response, client)

    def _handle(self, packet: bytes) -> bytes | None:
        message = unpack_message(packet)
        address = message.address
        if address == "/xremote":
            self.state.xremote_count += 1
            return pack_message("/xremote", "ok")
        if address == "/info":
            return pack_message("/info", self.state.model, self.state.firmware, self.state.revision)
        if address == "/node":
            requested = str(message.arguments[0]) if message.arguments else "/"
            return pack_message("/node", requested, ",".join(node_children(requested)))
        if address == "/meters":
            return pack_message("/meters", ",".join(f"{k}={v}" for k, v in meter_fixture().items()))
        if address == "/rta/source":
            return pack_message("/rta/source", self.state.values["/rta/source"])
        if address == "/rta/source/set":
            source = str(message.arguments[0]) if message.arguments else ""
            self.write_packets.append("/rta/source")
            if source in self.rta_restore_failure_sources:
                return pack_message("/rta/source", "RESTORE_FAILED")
            self.state.values["/rta/source"] = source
            self.state.revision += 1
            return pack_message("/rta/source", "ok", source, self.state.revision)
        if address == "/rta/bands":
            if self.state.values["/rta/source"] in self.rta_band_failure_sources:
                return pack_message("/rta/bands", "UNSUPPORTED_PATH")
            return pack_message("/rta/bands", ",".join(str(v) for v in rta_bands()))
        if address.endswith("/set") or (message.arguments and address in self.state.values):
            target = address[:-4] if address.endswith("/set") else address
            self.write_packets.append(target)
            value = message.arguments[0] if message.arguments else None
            self.state.values[target] = value
            if target == "/ch/01/headamp/gain":
                self.set_gain(float(value), source="ai")
            else:
                self.state.revision += 1
            return pack_message(target, self.state.values[target], self.state.revision)
        value = self.state.values.get(address)
        if value is None:
            return pack_message(address, "UNSUPPORTED_PATH")
        if address == "/ch/01/headamp/gain":
            return pack_message(address, float(value), self.state.revision)
        return pack_message(address, value, self.state.revision)
