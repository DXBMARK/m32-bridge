from __future__ import annotations

from pathlib import Path
from typing import Any

from .planner import plan_dry_run_install


def installer_status(
    *,
    platform: str = "macos",
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
    dry_run: bool = True,
    current_version: str | None = None,
    target_version: str | None = None,
) -> dict[str, Any]:
    if not dry_run:
        return {
            **plan_dry_run_install(
                platform=platform,
                home=home,
                local_app_data=local_app_data,
                current_version=current_version,
                target_version=target_version,
            ),
            "ok": False,
            "status": "failed",
            "error_code": "DRY_RUN_ONLY",
            "message": "Installer service boundary is dry-run only until script implementation tasks begin.",
        }
    return plan_dry_run_install(
        platform=platform,
        home=home,
        local_app_data=local_app_data,
        current_version=current_version,
        target_version=target_version,
    )

