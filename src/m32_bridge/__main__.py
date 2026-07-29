"""Package entry point for local operator controls."""

from __future__ import annotations

import platform
import sys
from typing import Any

from m32_bridge.cli import main


def startup_verification() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_approved": sys.version_info[:2] == (3, 13),
        "python_313": sys.version_info[:2] == (3, 13),
        "project_python_range": ">=3.11,<3.14",
        "system_python_modified": False,
        "platform": platform.system(),
        "local_process": True,
        "webui": False,
        "database": False,
        "microservices": False,
        "network_side_effects": False,
        "public_network_exposure": False,
        "external_emulator": False,
        "production_live_ready": False,
        "stdout": "json_only_for_operator_commands",
    }


if __name__ == "__main__":
    raise SystemExit(main())
