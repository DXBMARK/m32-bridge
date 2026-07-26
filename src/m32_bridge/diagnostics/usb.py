"""Best-effort USB evidence collection for diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def inspect_usb_evidence(
    *,
    platform_name: str,
    backend: Callable[[], list[dict[str, Any]]] | None = None,
    timeout_s: float = 0.25,
) -> dict[str, Any]:
    del timeout_s
    if backend is None:
        return {
            "usb_detected": None,
            "usb_device_name": None,
            "vendor_id": None,
            "product_id": None,
            "usb_confidence": "unavailable",
            "inspection_status": "unsupported_os" if platform_name.lower() not in {"darwin", "linux", "windows"} else "unavailable",
            "limitations": ["USB inspection backend unavailable; continuing without USB evidence."],
            "usb_control_supported": False,
        }

    try:
        devices = backend()
    except PermissionError as exc:
        return {
            "usb_detected": None,
            "usb_device_name": None,
            "vendor_id": None,
            "product_id": None,
            "usb_confidence": "unavailable",
            "inspection_status": "blocked",
            "limitations": [f"USB inspection blocked: {exc}"],
            "usb_control_supported": False,
        }
    except Exception as exc:
        return {
            "usb_detected": None,
            "usb_device_name": None,
            "vendor_id": None,
            "product_id": None,
            "usb_confidence": "unavailable",
            "inspection_status": "unavailable",
            "limitations": [f"USB inspection unavailable: {type(exc).__name__}"],
            "usb_control_supported": False,
        }

    match = _find_console_device(devices)
    if match is None:
        return {
            "usb_detected": False,
            "usb_device_name": None,
            "vendor_id": None,
            "product_id": None,
            "usb_confidence": "none",
            "inspection_status": "checked",
            "limitations": ["No M32/X32 USB evidence found."],
            "usb_control_supported": False,
        }

    return {
        "usb_detected": True,
        "usb_device_name": match.get("name") or match.get("usb_device_name"),
        "vendor_id": match.get("vendor_id"),
        "product_id": match.get("product_id"),
        "usb_confidence": "high",
        "inspection_status": "checked",
        "limitations": [],
        "usb_control_supported": False,
    }


def _find_console_device(devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    for device in devices:
        name = str(device.get("name") or device.get("usb_device_name") or "").lower()
        if "m32" in name or "x32" in name:
            return device
    return None
