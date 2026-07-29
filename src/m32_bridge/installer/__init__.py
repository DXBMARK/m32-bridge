"""User-local installer planning primitives.

This package contains dry-run/status helpers only. It does not execute installer
scripts, edit host application config, or contact console endpoints.
"""

from .output import build_installer_output
from .planner import plan_dry_run_install
from .service import installer_status

__all__ = ["build_installer_output", "installer_status", "plan_dry_run_install"]

