from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class FailureClassification:
    error_code: str
    dependency_package: str | None = None


def classify_install_failure(output: str, *, default_error_code: str) -> FailureClassification:
    lowered = output.lower()
    wheel_patterns = (
        "has no usable wheels",
        "wheels are required",
        "building from source is disabled",
        "source distributions are disabled",
        "no binary distribution",
    )
    if any(pattern in lowered for pattern in wheel_patterns):
        package_match = re.search(r"because\s+([a-z0-9_.-]+==[^\s,]+)\s+has no usable wheels", output, re.IGNORECASE)
        return FailureClassification(
            error_code="LOCKED_WHEEL_UNAVAILABLE",
            dependency_package=package_match.group(1) if package_match else None,
        )
    if any(pattern in lowered for pattern in ("dns error", "failed to lookup address", "name or service not known")):
        return FailureClassification("DNS_RESOLUTION_FAILED")
    if "timed out" in lowered or "timeout" in lowered:
        return FailureClassification("DOWNLOAD_TIMEOUT")
    if any(pattern in lowered for pattern in ("tls certificate", "certificate verify failed", "ssl certificate")):
        return FailureClassification("TLS_CERTIFICATE_FAILED")
    if "no space left on device" in lowered or "disk full" in lowered:
        return FailureClassification("DISK_SPACE_INSUFFICIENT")
    if "permission denied" in lowered or "operation not permitted" in lowered:
        return FailureClassification("PERMISSION_DENIED")
    return FailureClassification(default_error_code)


def locked_wheel_message() -> str:
    return (
        "A pre-built dependency wheel is unavailable for this supported platform. "
        "No compiler or system package was installed. "
        "Install a corrected M32 Bridge release or provide the diagnostic log to support."
    )


def write_install_diagnostic_log(log_dir: Path, *, stdout: str, stderr: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        log_dir.chmod(0o700)
    except OSError:
        pass
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    path = log_dir / f"install-{timestamp}.log"
    safe_stdout = _redact_sensitive_text(stdout)
    safe_stderr = _redact_sensitive_text(stderr)
    path.write_text(f"stdout:\n{safe_stdout}\nstderr:\n{safe_stderr}\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def _redact_sensitive_text(text: str) -> str:
    text = re.sub(r"(https?://)[^/\s:@]+:[^@\s/]+@", r"\1[REDACTED]@", text, flags=re.IGNORECASE)
    text = re.sub(
        r"([?&](?:token|key|password|secret)=)[^&\s]+",
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"(authorization:\s*(?:bearer|basic)\s+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
