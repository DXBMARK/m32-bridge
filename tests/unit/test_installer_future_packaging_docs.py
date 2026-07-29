from __future__ import annotations

from pathlib import Path


QUICKSTART = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-cross-platform-installers-and-first-run-setup"
    / "quickstart.md"
)


def test_future_packaging_items_are_documented_future_only():
    text = QUICKSTART.read_text(encoding="utf-8").lower()

    required = [
        ".exe",
        ".msi",
        ".app",
        ".pkg",
        ".dmg",
        ".deb",
        ".rpm",
        "appimage",
        "raspberry pi service/image",
        ".mcpb",
        ".dxt",
        "usb portable kit",
        "code signing",
        "checksums",
        "github releases",
    ]
    assert "future-only" in text
    for item in required:
        assert item in text


def test_future_packaging_docs_do_not_claim_current_binary_availability():
    text = QUICKSTART.read_text(encoding="utf-8").lower()

    forbidden = [
        "download the .exe",
        "download the .msi",
        "install the .dmg",
        "install the .pkg",
        "apt install m32-bridge",
        "rpm -i m32-bridge",
        "appimage is available",
        "claude .mcpb is available",
        "published checksums",
    ]
    for phrase in forbidden:
        assert phrase not in text
