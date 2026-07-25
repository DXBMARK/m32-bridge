"""Semantic OSC client adapters."""

from __future__ import annotations

import inspect

from m32_bridge.core.models import Operation
from m32_bridge.core.semantic_paths import is_semantic_write_allowed
from m32_bridge.osc.meters import parse_meter_summary
from m32_bridge.osc.transport import OscTransport

_WRITE_CALLERS = {"m32_bridge.core.executor", "m32_bridge.core.rollback"}


class OscClient:
    def __init__(self, transport: OscTransport) -> None:
        self.transport = transport

    def read_value(self, path: str):
        return self.transport.request(path).arguments

    def write_value(self, path: str, value: object, **_kwargs):
        raise ValueError("direct OSC writes are prohibited; use a validated operation write")

    def write_operation(self, operation: Operation, value: object):
        caller = inspect.currentframe().f_back
        caller_module = caller.f_globals.get("__name__") if caller is not None else None
        if caller_module not in _WRITE_CALLERS:
            raise ValueError("validated writes may only be issued by executor or rollback")
        if not is_semantic_write_allowed(operation.semantic_action, operation.target_path):
            raise ValueError("only allowlisted semantic operation paths may be written")
        self.transport.send(operation.target_path, value)
        return []

    def node(self, path: str = "/") -> list[str]:
        message = self.transport.request("/node", path)
        if len(message.arguments) < 2:
            return []
        children = str(message.arguments[1])
        return [item for item in children.split(",") if item]

    def meters(self) -> dict[str, float]:
        message = self.transport.request("/meters")
        return parse_meter_summary(str(message.arguments[0]))

    def rta(self) -> dict[str, object]:
        source = self.transport.request("/rta/source").arguments[0]
        bands = [float(item) for item in str(self.transport.request("/rta/bands").arguments[0]).split(",") if item]
        return {"source": source, "bands": bands, "simultaneous_per_channel_spectra": False}

    def clock_sync(self) -> dict[str, str]:
        keys = ["clock_rate", "clock_source", "clock_mode", "aes50_a", "aes50_b", "expansion_card_sync"]
        result: dict[str, str] = {}
        for key in keys:
            result[key] = str(self.transport.request(f"/-stat/{key}").arguments[0])
        return result

    def routing(self) -> dict[str, object]:
        return {"inputs": self.node("/routing/in"), "outputs": self.node("/routing/out")}
