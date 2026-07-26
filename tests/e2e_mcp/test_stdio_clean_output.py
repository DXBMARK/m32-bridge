from __future__ import annotations

import os
import subprocess
import time
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_stdio_startup_keeps_stdout_protocol_clean_before_client_messages():
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/private/tmp/uv-cache")
    process = subprocess.Popen(
        ["uv", "run", "m32-bridge", "mcp-server"],
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.4)
        assert process.poll() is None
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)

    assert stdout == ""
    assert "{" not in stderr
    assert "traceback" not in stderr.lower()


def test_stdio_logging_contract_routes_diagnostics_to_stderr_not_stdout():
    from m32_bridge.config.logging import configure_logging

    configure_logging()
    logger = logging.getLogger()

    assert logger.handlers
    assert any(getattr(handler, "stream", None) is sys.stderr for handler in logger.handlers)
    assert all(getattr(handler, "stream", None) is not sys.stdout for handler in logger.handlers)
