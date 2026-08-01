from __future__ import annotations

import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)([^\s]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s]+)"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[:=]\s*)([^\s]+)"),
    re.compile(r"(?i)(://[^\s:/]+:)([^@\s]+)(@)"),
)


def _new_log_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"runtime-{timestamp}-{uuid4().hex}.log"


def write_runtime_diagnostic_log(log_dir: Path, exc: BaseException) -> Path | None:
    """Create one private, non-overwriting diagnostic log or fail closed."""

    fd: int | None = None
    created = False
    path = log_dir / _new_log_name()
    try:
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            log_dir.chmod(0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        created = True
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(_redact(detail))
        return path
    except (OSError, ValueError):
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            if created and path.is_file() and not path.is_symlink():
                path.unlink()
        except OSError:
            pass
        return None


def _redact(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 3:
            redacted = pattern.sub(r"\1[REDACTED]\3", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted
