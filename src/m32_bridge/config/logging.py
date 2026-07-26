"""Logging policy for MCP stdio transport.

stdout is reserved for MCP protocol messages; diagnostics and logs go to stderr.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    for handler in list(root.handlers):
        if getattr(handler, "stream", None) is sys.stdout:
            root.removeHandler(handler)

    if not any(getattr(handler, "stream", None) is sys.stderr for handler in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        root.addHandler(handler)
