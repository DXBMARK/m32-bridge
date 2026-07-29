from __future__ import annotations

from dataclasses import dataclass
from shutil import which
from typing import Literal


UvStatus = Literal["present", "installed_user_local", "blocked", "manual_action_required"]


@dataclass(frozen=True)
class RuntimeManagerState:
    uv_status: UvStatus
    global_py_required: bool = False
    manual_guidance: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.uv_status in {"present", "installed_user_local"}


def detect_uv_status(*, allow_user_install: bool = False, uv_executable: str | None = None) -> RuntimeManagerState:
    if uv_executable or which("uv"):
        return RuntimeManagerState(uv_status="present")
    if allow_user_install:
        return RuntimeManagerState(
            uv_status="manual_action_required",
            manual_guidance="Install uv in user space, then rerun the installer.",
        )
    return RuntimeManagerState(
        uv_status="manual_action_required",
        manual_guidance="uv is required. Install uv manually or use an approved user-local install path.",
    )

