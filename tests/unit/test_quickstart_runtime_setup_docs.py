from __future__ import annotations

from pathlib import Path


QUICKSTART_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-local-runtime-setup-and-device-verification"
    / "quickstart.md"
)


def _quickstart() -> str:
    return QUICKSTART_PATH.read_text(encoding="utf-8")


def test_quickstart_documents_slash_commands_as_shell_only():
    text = _quickstart()

    assert "Inside the shell only:" in text
    assert "Help clearly states slash commands work only inside the `m32-bridge` shell." in text
    assert "No slash command exposes raw OSC" in text
    assert "/runsetup" in text
    assert "/unlock" in text


def test_quickstart_preserves_future_only_packaging_scope():
    text = _quickstart()

    assert "Future Packaging Notes" in text
    assert "Current development install." in text
    assert "Future OS packages." in text
    assert "Future Raspberry Pi service/image." in text
    assert "Future MCP extension bundle." in text
    assert "No packaging or installer implementation is part of this feature" in text


def test_quickstart_does_not_present_slash_commands_as_os_terminal_commands():
    text = _quickstart()
    shell_section = text.split("## 7. Interactive Shell", maxsplit=1)[1].split("## 8.", maxsplit=1)[0]

    assert "Inside the shell only:" in shell_section
    assert "m32-bridge /runsetup" not in shell_section
    assert "m32-bridge /unlock" not in shell_section
