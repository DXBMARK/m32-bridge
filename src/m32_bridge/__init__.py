"""M32 MCP Bridge package."""

from __future__ import annotations

from typing import Any

__all__ = ["__version__"]


def __getattr__(name: str) -> Any:
    """Resolve compatibility attributes without duplicating project metadata."""

    if name == "__version__":
        from m32_bridge.installer.application_version import application_version

        return application_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
