from __future__ import annotations

from m32_bridge.installer.first_run import contact_text, environment_summary, help_text, interactive_wizard, render_tty_intro
from m32_bridge.installer.ide_detector import detect_ide_clients


def test_tty_wizard_renders_dxbmark_brand_tokens(tmp_path):
    summary = environment_summary(environ={"SHELL": "/bin/zsh"}, home=tmp_path)
    clients = detect_ide_clients(environ={"CODEX_HOME": str(tmp_path)}, home=tmp_path)

    text = render_tty_intro(summary, clients)

    assert "DXBMARK" in text
    assert "#243947" in text
    assert "#F97E1A" in text
    assert "ASCII DXBMARK banner" in text
    assert "full raw-mode TUI is not enabled" in text
    assert "[System]" in text
    assert "[Runtime]" in text
    assert "[Clients]" in text
    assert "[Console Setup]" in text
    assert "[Help]" in text
    assert "/help" in text
    assert "/contact" in text
    assert "Recommended mode:" in text
    assert "green" in text
    assert "grey" in text


def test_tty_wizard_prompt_contract_uses_port_default_label_and_target(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_setup_probe(**kwargs):
        captured.update(kwargs)
        return {"ok": False, "status": "TEST_CAPTURED"}

    monkeypatch.setattr("m32_bridge.installer.first_run.run_setup_probe", fake_run_setup_probe)
    answers = iter(["192.0.2.10", "", "soundcheck", "hardware", "yes"])
    prompts: list[str] = []

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    output: list[str] = []
    result = interactive_wizard(
        input_func=fake_input,
        output_func=output.append,
        environ={"SHELL": "/bin/bash"},
    )

    assert result["status"] == "TEST_CAPTURED"
    assert captured["host"] == "192.0.2.10"
    assert captured["port"] == 10023
    assert captured["label"] == "soundcheck"
    assert captured["target_type"] == "hardware"
    assert captured["confirm_save"] is True
    assert any("Console IP" in prompt for prompt in prompts)
    assert any("Port [10023]" in prompt for prompt in prompts)


def test_help_explains_setup_commands_for_non_expert():
    text = help_text()

    assert "/help" in text
    assert "/contact" in text
    assert "Console IP" in text
    assert "will not guess or scan" in text
    assert "10023" in text
    assert "Save" in text


def test_contact_shows_dxbmark_branded_contact():
    text = contact_text()

    assert "DXBMARK" in text
    assert "https://www.dxbmark.com" in text
    assert "support@" in text
