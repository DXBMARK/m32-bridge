"""OS-aware local runtime setup recommendations."""

from __future__ import annotations

from typing import Any


def build_os_recommendations(*, platform_name: str) -> dict[str, Any]:
    os_family = _os_family(platform_name)
    recommendations = _recommendations(os_family)
    return {
        "os_family": os_family,
        "recommended_launcher": "m32-bridge",
        "user_local_default": True,
        "admin_required": "optional" if os_family in {"windows", "linux", "raspberry_pi_os"} else "no",
        "usb_detection": "best_effort",
        "future_packaging_notes": _future_notes(os_family),
        "warnings": _warnings(os_family),
        "recommendations": recommendations,
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def future_installation_strategy() -> dict[str, Any]:
    return {
        "current_strategy": "development_or_user_local_launcher",
        "packaging_implemented": False,
        "installer_created": False,
        "remote_mcp_implemented": False,
        "chatgpt_tunnel_implemented": False,
        "webui_added": False,
        "database_added": False,
        "future_packaging_notes": [
            "future os packages",
            "future raspberry pi service/image",
            "future mcp extension bundle",
            "future portable kit",
        ],
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def usb_recommendation(*, usb_evidence: dict[str, Any]) -> dict[str, Any]:
    status = str(usb_evidence.get("inspection_status", "unavailable"))
    limited = status in {"blocked", "unavailable", "unsupported_os"}
    return {
        "status": "USB_INSPECTION_LIMITED" if limited else "USB_INSPECTION_CHECKED",
        "blocking": False,
        "usb_control_supported": False,
        "limitations": list(usb_evidence.get("limitations", [])),
        "recommendations": [
            "Continuing with network/runtime diagnostics; USB evidence is best-effort only."
            if limited
            else "USB evidence is informational and does not authorize control."
        ],
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _os_family(platform_name: str) -> str:
    value = platform_name.lower()
    if value in {"darwin", "mac", "macos"}:
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value in {"raspberry_pi_os", "raspbian"}:
        return "raspberry_pi_os"
    if value.startswith("linux"):
        return "linux"
    return "unknown"


def _recommendations(os_family: str) -> list[str]:
    common = ["Use local stdio MCP with m32-bridge mcp-server.", "Keep setup user-local by default."]
    if os_family == "macos":
        return ["Use Claude Desktop stdio with a user-local launcher.", *common]
    if os_family == "windows":
        return ["Use a user install or future executable launcher.", *common]
    if os_family == "linux":
        return ["Use a user-local install/package path.", *common]
    if os_family == "raspberry_pi_os":
        return ["Use future dedicated bridge mode for Raspberry Pi OS.", *common]
    return common


def _future_notes(os_family: str) -> list[str]:
    notes = ["future OS packages", "future MCP extension bundle", "future portable kit"]
    if os_family == "raspberry_pi_os":
        notes.append("future Raspberry Pi service/image")
    return notes


def _warnings(os_family: str) -> list[str]:
    warnings = ["No cloud exposure by default.", "Packaging and installers are future-only."]
    if os_family == "linux":
        warnings.append("Use no cloud bridge unless a later secure transport spec exists.")
    return warnings
