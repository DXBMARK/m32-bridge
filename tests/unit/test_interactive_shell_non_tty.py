from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m32_bridge_without_subcommand_non_tty_returns_structured_error_without_hanging():
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    completed = subprocess.run(
        ["uv", "run", "m32-bridge"],
        cwd=PROJECT_ROOT,
        env=env,
        input="",
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode != 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["error_code"] == "NON_INTERACTIVE_SHELL_REQUIRED"
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert "interactive terminal" in payload["message"].lower()
    assert "m32-bridge setup" in payload["recommendations"]
    assert "m32-bridge health" in payload["recommendations"]
    assert "m32-bridge mcp-server" in payload["recommendations"]


def test_non_tty_guard_has_no_prompt_text_or_blocking_stdin_behavior():
    from m32_bridge.interactive_shell import non_interactive_shell_required

    payload = non_interactive_shell_required(stdin_is_tty=False)

    assert payload["status"] == "NON_INTERACTIVE_SHELL_REQUIRED"
    assert payload["started"] is False
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
