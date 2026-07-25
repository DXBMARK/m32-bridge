"""Strict OSC packet codec for the supported MVP value types."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


class OscCodecError(ValueError):
    """Raised when an OSC packet is malformed or unsupported."""


@dataclass(frozen=True)
class OscMessage:
    address: str
    arguments: tuple[Any, ...] = ()


def _pad(data: bytes) -> bytes:
    padding = (-len(data)) % 4
    return data + (b"\x00" * padding)


def _read_padded_string(packet: bytes, offset: int) -> tuple[str, int]:
    end = packet.find(b"\x00", offset)
    if end < 0:
        raise OscCodecError("unterminated OSC string")
    raw = packet[offset:end]
    next_offset = end + 1
    next_offset += (-next_offset) % 4
    if next_offset > len(packet):
        raise OscCodecError("OSC string padding exceeds packet length")
    try:
        return raw.decode("utf-8"), next_offset
    except UnicodeDecodeError as exc:
        raise OscCodecError("OSC string is not valid UTF-8") from exc


def pack_message(address: str, *arguments: Any) -> bytes:
    if not address.startswith("/"):
        raise OscCodecError("OSC address must start with /")
    tags = [","]
    payload = bytearray()
    for arg in arguments:
        if isinstance(arg, bool):
            tags.append("T" if arg else "F")
        elif isinstance(arg, int) and not isinstance(arg, bool):
            tags.append("i")
            payload.extend(struct.pack(">i", arg))
        elif isinstance(arg, float):
            tags.append("f")
            payload.extend(struct.pack(">f", arg))
        elif isinstance(arg, str):
            if "\x00" in arg:
                raise OscCodecError("OSC strings cannot contain NUL bytes")
            tags.append("s")
            try:
                encoded = arg.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise OscCodecError("OSC strings must be valid UTF-8") from exc
            payload.extend(_pad(encoded + b"\x00"))
        elif isinstance(arg, (bytes, bytearray)):
            blob = bytes(arg)
            tags.append("b")
            payload.extend(struct.pack(">i", len(blob)))
            payload.extend(_pad(blob))
        else:
            raise OscCodecError(f"unsupported OSC argument type: {type(arg).__name__}")
    return _pad(address.encode("utf-8") + b"\x00") + _pad("".join(tags).encode("ascii") + b"\x00") + bytes(payload)


def unpack_message(packet: bytes) -> OscMessage:
    if len(packet) < 8 or len(packet) % 4 != 0:
        raise OscCodecError("OSC packet length must be a positive multiple of 4")
    address, offset = _read_padded_string(packet, 0)
    if not address.startswith("/"):
        raise OscCodecError("OSC address must start with /")
    tags, offset = _read_padded_string(packet, offset)
    if not tags.startswith(","):
        raise OscCodecError("OSC type tag string must start with comma")
    args: list[Any] = []
    for tag in tags[1:]:
        if tag == "i":
            if offset + 4 > len(packet):
                raise OscCodecError("truncated int argument")
            args.append(struct.unpack(">i", packet[offset : offset + 4])[0])
            offset += 4
        elif tag == "f":
            if offset + 4 > len(packet):
                raise OscCodecError("truncated float argument")
            args.append(struct.unpack(">f", packet[offset : offset + 4])[0])
            offset += 4
        elif tag == "s":
            value, offset = _read_padded_string(packet, offset)
            args.append(value)
        elif tag == "b":
            if offset + 4 > len(packet):
                raise OscCodecError("truncated blob length")
            size = struct.unpack(">i", packet[offset : offset + 4])[0]
            offset += 4
            if size < 0 or offset + size > len(packet):
                raise OscCodecError("invalid blob length")
            args.append(packet[offset : offset + size])
            offset += size
            offset += (-offset) % 4
        elif tag == "T":
            args.append(True)
        elif tag == "F":
            args.append(False)
        else:
            raise OscCodecError(f"unsupported OSC tag: {tag}")
    if offset != len(packet):
        raise OscCodecError("trailing bytes after OSC arguments")
    return OscMessage(address=address, arguments=tuple(args))


def quantize_to_grid(value: float, grid: float) -> float:
    if grid <= 0:
        raise ValueError("grid must be positive")
    return round(round(value / grid) * grid, 6)


def format_db(value: float) -> str:
    return f"{value:+.1f} dB"
