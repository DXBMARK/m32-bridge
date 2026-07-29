from __future__ import annotations

from pathlib import Path


CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-cross-platform-installers-and-first-run-setup"
    / "contracts"
    / "mcp-guidance-contract.md"
)


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_mcp_guidance_contract_uses_manual_copy_stdio_snippet():
    text = _contract()

    assert '"command": "m32-bridge"' in text
    assert '"args": ["mcp-server"]' in text
    assert "manual-copy only" in text.lower()


def test_mcp_guidance_contract_omits_host_port_by_default():
    text = _contract()

    assert "Default snippets do not embed host or port" in text
    assert "saved user-local configuration" in text


def test_mcp_guidance_contract_labels_advanced_overrides_and_forbids_auto_write():
    text = _contract()

    assert "advanced/manual examples" in text
    assert "automatically write Claude Desktop configuration" in text
    assert "must not claim it has modified Claude Desktop configuration" in text


def test_mcp_guidance_contract_forbids_shell_remote_and_raw_surfaces():
    text = _contract().lower()

    for forbidden in [
        "raw osc",
        "arbitrary osc paths",
        "shell execution",
        "remote/cloud mcp",
        "chatgpt tunnel",
        "firmware",
        "shutdown",
        "phantom",
        "sample-rate",
        "clock",
    ]:
        assert forbidden in text
