"""Logging policy for MCP stdio transport.

stdout is reserved for MCP protocol messages; diagnostics and logs go to stderr.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

