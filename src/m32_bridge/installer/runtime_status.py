"""Runtime-only command contract and shared local status snapshots."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

from m32_bridge.runtime_preconditions import evaluate_console_precondition

from .application_version import application_version, resolve_installed_application_version
from .install_metadata import (
    OFFICIAL_REPOSITORY_URL,
    PRODUCT_NAME,
    build_official_release_urls,
    canonical_source_url,
    is_commit_ref,
    install_metadata_path,
    is_official_source_url,
    read_install_metadata,
)
from .runtime_manager import (
    OFFICIAL_RAW_INSTALLER_URLS,
    OFFICIAL_SOURCE_ARCHIVE_URLS,
    local_runtime_diagnostics,
    platform_information,
)


@dataclass(frozen=True)
class RuntimeCommandSpec:
    command: str
    description: str
    handler_id: str
    view: str
    shell_equivalent: str
    requires_console_config: bool
    read_only: bool
    safe_to_retry_after_setup: bool
    network_scope: str
    visible_in_picker: bool = True


def _spec(
    command: str,
    description: str,
    handler_id: str,
    view: str,
    shell_equivalent: str,
    network_scope: str,
    *,
    requires_console_config: bool = False,
    read_only: bool = True,
    safe_to_retry_after_setup: bool = False,
) -> RuntimeCommandSpec:
    return RuntimeCommandSpec(
        command=command,
        description=description,
        handler_id=handler_id,
        view=view,
        shell_equivalent=shell_equivalent,
        requires_console_config=requires_console_config,
        read_only=read_only,
        safe_to_retry_after_setup=safe_to_retry_after_setup,
        network_scope=network_scope,
    )


RUNTIME_COMMAND_SPECS = (
    _spec("/help", "Runtime command and safety reference", "runtime_help", "help", "m32-bridge --help", "none"),
    _spec("/status", "Full local and cached system status", "runtime_status", "status", "m32-bridge status", "none"),
    _spec("/status refresh", "Refresh official GitHub source status", "runtime_status_refresh", "status", "m32-bridge status --refresh", "official_source_https_only"),
    _spec("/health", "Local application health and readiness", "runtime_health", "health", "m32-bridge health", "none"),
    _spec("/setup", "Save a known endpoint, then verify with one read-only /info", "runtime_setup", "setup", "m32-bridge setup", "one_read_only_info_after_save", read_only=False),
    _spec("/get-info", "Read /info from the configured endpoint", "runtime_get_info", "get_info", "m32-bridge get-info", "configured_endpoint_read_only", requires_console_config=True, safe_to_retry_after_setup=True),
    _spec("/verify-device", "Read-only endpoint classification", "runtime_verify_device", "verify_device", "m32-bridge detect-device", "configured_endpoint_read_only", requires_console_config=True, safe_to_retry_after_setup=True),
    _spec("/doctor-runtime", "Deep local runtime diagnostics", "runtime_doctor", "doctor", "m32-bridge doctor-runtime", "none"),
    _spec("/mcp-config", "Manual MCP client setup guidance; no writes", "runtime_mcp_config", "mcp", "m32-bridge mcp-config", "none"),
    _spec("/contact", "Product and support information", "runtime_contact", "contact", "runtime-only", "none"),
    _spec("/clear", "Return to the Runtime dashboard", "runtime_clear", "main", "runtime-only", "none"),
    _spec("/exit", "Return to the parent shell", "runtime_exit", "exit", "runtime-only", "none"),
)
RUNTIME_COMMAND_REGISTRY = {spec.command: spec for spec in RUNTIME_COMMAND_SPECS}
RUNTIME_PICKER_ORDER = tuple(spec.command for spec in RUNTIME_COMMAND_SPECS if spec.visible_in_picker)
RUNTIME_SOURCE_USER_AGENT = "X32-Bridge-MCP-Runtime"
_application_version = application_version


def command_contract_table() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in RUNTIME_COMMAND_SPECS]


def build_runtime_status(
    result: dict[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    refresh: bool = False,
    source_checker: Callable[[str, float], str] | None = None,
    metadata_path: Path | None = None,
    timeout: float = 1.5,
) -> dict[str, Any]:
    """Build a probe-free status snapshot shared by CLI and Runtime TTY."""

    state = result if result is not None else {}
    env = dict(os.environ if environ is None else environ)
    app_path = str(state.get("app_path") or env.get("M32_BRIDGE_APP_DIR") or "")
    launcher_path = str(state.get("launcher_path") or env.get("M32_BRIDGE_LAUNCHER") or "")
    runtime = dict(state.get("runtime_info") or {})
    if not runtime:
        runtime_env = dict(env)
        installed_uv = runtime_env.get("M32_BRIDGE_UV_BIN")
        if installed_uv:
            runtime_env["PATH"] = str(Path(installed_uv).parent) + os.pathsep + runtime_env.get("PATH", "")
        runtime = local_runtime_diagnostics(
            environ=runtime_env,
            app_path=app_path or None,
            launcher_path=launcher_path or None,
        )
    platform_data = dict(state.get("platform_info") or platform_information(environ=env))
    metadata_target = metadata_path or install_metadata_path(
        surface="windows" if str(platform_data.get("os", "")).lower().startswith("win") else "posix",
        app_path=app_path or None,
        environ=env,
    )
    metadata = read_install_metadata(metadata_target)
    metadata_data = dict(metadata.get("data") or {})
    version_resolution = resolve_installed_application_version(app_path or None, environ=env)
    current_application_version = (
        version_resolution.version
        if _application_version is application_version
        else str(_application_version())
    )
    metadata_write_warning = (
        state.get("install_metadata_status") in {"write_failed", "validation_failed"}
        or runtime.get("install_metadata_status") in {"write_failed", "validation_failed"}
        or bool(app_path and (Path(app_path) / ".install-provenance-pending").is_file())
    )
    metadata_stale = bool(
        metadata["status"] == "metadata_valid"
        and (
            metadata_write_warning
            or (
                metadata_data.get("application_version") not in {None, "", "unknown", "not_available"}
                and current_application_version not in {"", "unknown", "not_available"}
                and metadata_data.get("application_version") != current_application_version
            )
        )
    )
    if metadata_stale:
        metadata = {**metadata, "status": "metadata_stale"}
    source_status = _cached_source_status(state.get("source_status"))
    if metadata_stale:
        source_status = _unrefreshed_source_status("metadata_stale")
    refresh_state = "not_run"
    if refresh:
        if metadata["status"] == "metadata_missing":
            source_status = _unrefreshed_source_status("metadata_missing")
            refresh_state = "not_run_metadata_missing"
        elif metadata["status"] == "metadata_invalid":
            source_status = _unrefreshed_source_status("metadata_invalid")
            refresh_state = "not_run_metadata_invalid"
        elif metadata["status"] == "metadata_stale":
            source_status = _unrefreshed_source_status("metadata_stale")
            refresh_state = "not_run_metadata_stale"
        elif metadata_data.get("install_source") == "custom":
            source_status = _unrefreshed_source_status("custom_source_not_refreshed")
            refresh_state = "not_run_custom_source"
        elif metadata_data.get("install_source") == "local_checkout":
            source_status = _unrefreshed_source_status("local_source_not_refreshed")
            refresh_state = "not_run_local_source"
        else:
            source_status, refresh_state = refresh_official_source_status(
                metadata_data,
                platform_data=platform_data,
                checker=source_checker,
                timeout=timeout,
            )
        state["source_status"] = dict(source_status)

    precondition = evaluate_console_precondition(environ=env)
    resolution = precondition.resolution
    configuration_state = {
        "setup_required": "missing",
        "config_invalid": "invalid",
        "ready": "valid",
    }[precondition.state]
    endpoint_host = resolution.effective_host if precondition.state == "ready" and resolution else None
    endpoint_port = resolution.effective_port if precondition.state == "ready" and resolution else None
    current_fingerprint = (
        endpoint_fingerprint(
            endpoint_host,
            endpoint_port,
            precondition.config_path,
            resolution.effective_intended_target_type if resolution else None,
        )
        if precondition.state == "ready"
        else None
    )
    checked_fingerprint = state.get("last_console_config_fingerprint")
    connection_state = str(state.get("console_connection_status") or state.get("connection_state") or "not_checked")
    endpoint_verified = bool(state.get("endpoint_verified", False))
    if configuration_state != "valid" or not checked_fingerprint or checked_fingerprint != current_fingerprint:
        connection_state = "not_checked"
        endpoint_verified = False
    if connection_state not in {"not_checked", "reachable", "unreachable"}:
        connection_state = "not_checked"
    application_checks = _application_checks(app_path, launcher_path, runtime)
    application_health = _application_health(runtime, state, application_checks)
    if version_resolution.status in {"version_source_mismatch", "project_metadata_invalid"}:
        application_health = "action_required"
    operational_state = _operational_state(configuration_state, connection_state)
    device_state = _device_verification_state(state, connection_state)
    trusted_metadata_data = {} if metadata_stale else metadata_data
    product_version = current_application_version
    source_ref = trusted_metadata_data.get("source_ref") or (state.get("source_ref") if metadata["status"] == "metadata_missing" else None) or "not_available"
    install_source = trusted_metadata_data.get("install_source") or (state.get("install_source") if metadata["status"] == "metadata_missing" else None) or "unknown"
    repository_url = trusted_metadata_data.get("repository_url") or (state.get("repository_url") if metadata["status"] == "metadata_missing" else None) or ("not_persisted" if install_source == "custom" else "not_available")
    top_status = "ok" if application_health == "healthy" else ("error" if application_health == "error" else "action_required")
    snapshot = {
        "ok": application_health == "healthy",
        "status": top_status,
        "snapshot_complete": True,
        "application_health": application_health,
        "configuration_state": configuration_state,
        "connection_state": connection_state,
        "operational_state": operational_state,
        "device_verification_state": device_state,
        "application": {
            "product": trusted_metadata_data.get("product") or PRODUCT_NAME,
            "version": product_version,
            "version_source": version_resolution.source,
            "version_status": version_resolution.status,
            "version_mismatch": version_resolution.mismatch,
            "app_path": trusted_metadata_data.get("app_path") or app_path or "not_available",
            "launcher_path": trusted_metadata_data.get("launcher_path") or launcher_path or "not_available",
            "runtime_provenance": (runtime.get("import_provenance") or {}).get("m32_bridge_path") or runtime.get("python_source") or "not_checked",
            "install_metadata_status": metadata["status"],
            "install_metadata_path": metadata["path"],
            "install_metadata_warning": state.get("install_metadata_status") if state.get("install_metadata_status") in {"write_failed", "validation_failed"} else "none",
            "health_checks": application_checks,
        },
        "platform": platform_data,
        "python_runtime": {
            "uv_detected": bool(runtime.get("uv_detected")),
            "uv_version": runtime.get("uv_version") or "not_detected",
            "uv_path": runtime.get("uv_path") or "not_detected",
            "managed_python_version": runtime.get("managed_python_version") or runtime.get("python_version") or "not_detected",
            "managed_python_path": runtime.get("python_path") or "not_detected",
            "python_source": runtime.get("python_source") or "not_detected",
            "approved_minor": runtime.get("approved_minor") or "3.13",
            "project_required_range": runtime.get("project_required_range") or ">=3.11,<3.14",
            "frozen_launcher": "enabled",
            "system_python_version": runtime.get("system_python_version") or "not_checked",
            "system_python_path": runtime.get("system_python_path") or "not_checked",
            "system_python_used": False,
            "system_python_modified": False,
        },
        "installation_source": {
            "install_source": install_source,
            "repository_url": repository_url,
            "source_ref": source_ref,
            "release_tag": trusted_metadata_data.get("release_tag") or "not_available",
            "source_commit": trusted_metadata_data.get("source_commit") or "not_available",
            "application_version": product_version,
            "application_version_source": version_resolution.source,
            "requested_selection": trusted_metadata_data.get("selection") or "not_available",
            "release_channel": trusted_metadata_data.get("release_channel") or "not_available",
            "manifest_status": trusted_metadata_data.get("manifest_status") or "not_available",
            "archive_checksum_status": (
                "verified" if trusted_metadata_data.get("source_archive_sha256") else "not_available"
            ),
            "installed_at": trusted_metadata_data.get("installed_at") or "not_available",
            "raw_installer_url": trusted_metadata_data.get("raw_installer_url") or trusted_metadata_data.get("source_url_status") or "not_available",
            "source_archive_url": trusted_metadata_data.get("source_archive_url") or trusted_metadata_data.get("source_url_status") or "not_available",
            "last_source_check": source_status["last_checked"],
        },
        "source_connectivity": source_status,
        "console_configuration": {
            "configuration_state": configuration_state,
            "configured": configuration_state == "valid",
            "host": endpoint_host or "not_configured",
            "port": endpoint_port or "not_configured",
            "host_source": (resolution.source_by_field.get("host") if resolution else None) or "not_configured",
            "port_source": (resolution.source_by_field.get("port") if resolution else None) or "not_configured",
            "config_file": precondition.config_path or "not_configured",
            "label": (resolution.effective_label if resolution else None) or "not_set",
            "intended_target": (resolution.effective_intended_target_type if resolution else None) or "unknown",
        },
        "console_connection": {
            "connection_state": connection_state,
            "last_attempted_path": state.get("last_console_attempted_path") or "not_attempted",
            "last_error_code": state.get("last_console_error_code") or "none",
            "last_latency_ms": state.get("last_console_latency_ms") if state.get("last_console_latency_ms") is not None else "not_available",
            "last_check_at": state.get("last_console_check_at") or "not_checked",
            "endpoint_verified": endpoint_verified,
            "current_endpoint_fingerprint": current_fingerprint or "not_available",
            "checked_endpoint_fingerprint": checked_fingerprint or "not_available",
        },
        "safety": {
            "osc_writes_sent": 0,
            "set_command": "not_sent",
            "network_scan": "not_run",
            "console_probe": "not_run",
            "internet_source_refresh": refresh_state,
            "attempted_path": "not_attempted",
            "admin_elevation": "not_used",
            "system_python_modified": False,
            "hardware_verified": bool(state.get("hardware_verified") is True),
            "production_live_ready": False,
        },
    }
    state.update(
        application_health=application_health,
        configuration_state=configuration_state,
        connection_state=connection_state,
        operational_state=operational_state,
        device_verification_state=device_state,
    )
    state["runtime_status_snapshot"] = snapshot
    return snapshot


def build_runtime_health(
    result: dict[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    status = build_runtime_status(result, environ=environ, refresh=False)
    runtime = status["python_runtime"]
    application = status["application"]
    checks = application.get("health_checks") or _application_checks(
        application["app_path"], application["launcher_path"], runtime
    )
    imports = checks["required_import_details"]
    connection = status["console_connection"]
    return {
        "ok": status["application_health"] == "healthy",
        "status": "ok" if status["application_health"] == "healthy" else "action_required",
        "application_health": status["application_health"],
        "configuration_state": status["configuration_state"],
        "connection_state": status["connection_state"],
        "operational_state": status["operational_state"],
        "application": {
            "application_runtime": status["application_health"],
            "managed_python": "ready" if runtime["managed_python_version"] != "not_detected" else "action_required",
            "required_imports": "available" if all(detail["status"] == "available" for detail in imports.values()) else "action_required",
            "required_import_details": imports,
            "frozen_launcher": runtime["frozen_launcher"],
            "app_files": checks["app_files"],
            "venv": checks["venv"],
            "launcher_executable": checks["launcher_executable"],
        },
        "configuration_readiness": {
            "configuration_state": status["configuration_state"],
            "console_configured": status["configuration_state"] == "valid",
            "operational_state": status["operational_state"],
            "next_action": _next_action(status["operational_state"]),
        },
        "last_known_connection": connection,
        "safety": {
            "attempted_path": "not_attempted",
            "console_probe": "not_run",
            "network_scan": "not_run",
            "osc_writes_sent": 0,
        },
    }


def build_runtime_doctor(
    result: dict[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    state = result if result is not None else {}
    status = build_runtime_status(state, environ=environ, refresh=False)
    app = status["application"]
    runtime = status["python_runtime"]
    metadata_status = app["install_metadata_status"]
    config_state = status["configuration_state"]
    log_root = Path(str(app["app_path"])).parent / "logs" if app["app_path"] != "not_available" else Path.home() / ".m32-bridge" / "logs"
    writable_parent = log_root if log_root.exists() else log_root.parent
    return {
        "ok": status["application_health"] == "healthy",
        "status": "ok" if status["application_health"] == "healthy" else "action_required",
        "runtime": runtime,
        "required_imports": (app.get("health_checks") or _application_checks(app["app_path"], app["launcher_path"], runtime))["required_import_details"],
        "installation": {
            "app_files": "available" if app["app_path"] != "not_available" and Path(str(app["app_path"])).exists() else "not_found",
            "launcher_file": "available" if app["launcher_path"] != "not_available" and Path(str(app["launcher_path"])).exists() else "not_found",
            "launcher_executable": _launcher_executable(app["launcher_path"]),
            "path_visibility": _path_visible(app["launcher_path"], environ),
            "install_metadata_readability": metadata_status,
            "config_readability": config_state,
            "log_directory_writable": bool(writable_parent.exists() and os.access(writable_parent, os.W_OK)),
        },
        "policy": {
            "approved_python": "3.13",
            "project_required_range": runtime["project_required_range"],
            "admin_elevation": "not_used",
            "system_python_used": False,
            "system_python_modified": False,
        },
        "safety": {
            "attempted_path": "not_attempted",
            "console_probe": "not_run",
            "network_scan": "not_run",
            "internet_source_refresh": "not_run",
            "osc_writes_sent": 0,
        },
    }


def record_console_result(result: dict[str, Any], payload: Mapping[str, Any]) -> None:
    attempted = str(payload.get("attempted_path") or "not_attempted")
    verification_attempted = attempted != "not_attempted"
    connected = bool(payload.get("connected"))
    result["console_connection_status"] = "reachable" if connected else ("unreachable" if verification_attempted else "not_checked")
    result["last_console_attempted_path"] = attempted
    result["last_console_error_code"] = payload.get("error_code") or payload.get("verification_status") or (None if connected else payload.get("status"))
    result["last_console_latency_ms"] = payload.get("latency_ms") if payload.get("latency_ms") is not None else payload.get("latency")
    result["last_console_check_at"] = datetime.now(timezone.utc).isoformat() if verification_attempted else None
    host = payload.get("configured_host") or payload.get("host")
    port = payload.get("configured_port") or payload.get("port")
    config_path = payload.get("config_path")
    intended_target = payload.get("intended_target_type")
    result["last_console_host"] = host
    result["last_console_port"] = port
    result["last_console_config_path"] = str(Path(str(config_path)).expanduser().resolve(strict=False)) if config_path else None
    result["last_console_config_fingerprint"] = endpoint_fingerprint(host, port, config_path, intended_target)
    result["endpoint_verified"] = bool(payload.get("endpoint_verified", connected))
    result["configuration_state"] = "valid" if payload.get("config_saved") or payload.get("saved") else result.get("configuration_state", "missing")
    result["connection_state"] = result["console_connection_status"]
    result["operational_state"] = _operational_state(result["configuration_state"], result["connection_state"])


def endpoint_fingerprint(host: Any, port: Any, config_path: Any, intended_target: Any = None) -> str | None:
    """Bind cached connection evidence to one non-secret runtime endpoint."""

    if host in {None, ""} or port in {None, ""} or config_path in {None, ""}:
        return None
    try:
        port_value = int(port)
    except (TypeError, ValueError):
        return None
    normalized_path = str(Path(str(config_path)).expanduser().resolve(strict=False))
    material = "\n".join((str(host).strip().lower(), str(port_value), normalized_path, str(intended_target or "unknown").strip().lower()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def refresh_official_source_status(
    metadata: Mapping[str, Any],
    *,
    platform_data: Mapping[str, Any],
    checker: Callable[[str, float], str] | None = None,
    timeout: float = 1.5,
) -> tuple[dict[str, str], str]:
    """Refresh only allow-listed DXBMARK GitHub endpoints."""

    if metadata.get("install_source") not in {"github_raw", "github_release_or_archive", "github_release_asset", "github_commit_archive", "github_main"}:
        raise ValueError("Trusted official provenance is required for source refresh.")
    windows = str(platform_data.get("os") or "").lower().startswith("win")
    key = "windows" if windows else "posix"
    raw_url = str(metadata.get("installer_asset_url") or metadata.get("raw_installer_url") or "")
    archive_url = str(metadata.get("source_archive_url") or "")
    urls = {
        "network_https_route": "https://github.com/",
        "github_repository": OFFICIAL_REPOSITORY_URL,
        "raw_installer": raw_url,
        "source_archive": archive_url,
    }
    initial_allowed_urls = frozenset(urls.values())
    redirect_allowed_urls = _redirect_allowed_urls(metadata, archive_url=archive_url)
    if len(initial_allowed_urls) != 4 or any(canonical_source_url(url) != url or not _is_refresh_source_url(url, initial_allowed_urls) for url in urls.values()):
        raise ValueError("Source refresh URL is outside the official GitHub allow-list.")
    check = checker or _bounded_https_status
    statuses: dict[str, str] = {}
    for name, url in urls.items():
        try:
            statuses[name] = str(
                _bounded_https_status(
                    url,
                    timeout,
                    initial_allowed_urls=initial_allowed_urls,
                    redirect_allowed_urls=redirect_allowed_urls,
                )
                if checker is None
                else check(url, timeout)
            )
        except Exception:
            statuses[name] = "check_failed"
    statuses["dns"] = _derive_dns_status(statuses.values())
    statuses["last_checked"] = datetime.now(timezone.utc).isoformat()
    return statuses, "run"


def _cached_source_status(value: Any) -> dict[str, str]:
    defaults = {
        "network_https_route": "not_checked",
        "dns": "not_checked",
        "github_repository": "not_checked",
        "raw_installer": "not_checked",
        "source_archive": "not_checked",
        "last_checked": "not_checked",
    }
    if isinstance(value, Mapping):
        defaults.update({key: str(value.get(key) or default) for key, default in defaults.items()})
    return defaults


def _unrefreshed_source_status(state: str) -> dict[str, str]:
    values = _cached_source_status(None)
    for key in values:
        values[key] = "not_checked" if key == "last_checked" else state
    return values


def _bounded_https_status(
    url: str,
    timeout: float,
    *,
    initial_allowed_urls: frozenset[str] | None = None,
    redirect_allowed_urls: frozenset[str] | None = None,
    allowed_urls: frozenset[str] | None = None,
) -> str:
    initial = initial_allowed_urls or allowed_urls or frozenset({url})
    redirects = redirect_allowed_urls or frozenset()
    if not _is_refresh_source_url(url, initial):
        raise ValueError("Only official HTTPS source URLs may be refreshed.")
    opener = urllib.request.build_opener(_NoRedirect())
    current = url
    for _ in range(4):
        request = urllib.request.Request(current, method="HEAD", headers={"User-Agent": RUNTIME_SOURCE_USER_AGENT})
        try:
            with opener.open(request, timeout=timeout) as response:
                return "reachable" if 200 <= getattr(response, "status", 200) < 300 else "http_error"
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                return "http_error"
            location = exc.headers.get("Location")
            candidate = urljoin(current, location or "")
            destination = canonical_source_url(candidate) or _canonical_codeload_url(candidate)
            if destination is None or destination not in redirects:
                return "redirect_rejected"
            current = destination
            continue
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.gaierror):
                return "dns_error"
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return "timeout"
            if isinstance(reason, ssl.SSLError):
                return "tls_error"
            return "unreachable"
        except (TimeoutError, socket.timeout):
            return "timeout"
        except ssl.SSLError:
            return "tls_error"
    return "redirect_rejected"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _redirect_allowed_urls(metadata: Mapping[str, Any], *, archive_url: str) -> frozenset[str]:
    if metadata.get("release_tag"):
        source_commit = metadata.get("source_commit")
        if str(metadata.get("source_ref") or "").lower() != str(source_commit or "").lower():
            return frozenset()
        try:
            platform = "windows" if urlsplit(archive_url).path.endswith(".zip") else "posix"
            expected = build_official_release_urls(platform, source_commit)
        except ValueError:
            return frozenset()
        if archive_url != expected["source_archive_url"]:
            return frozenset()
        return frozenset({expected["allowed_redirect_url"]})
    source_ref = str(metadata.get("source_ref") or "")
    if source_ref != "main" and not is_commit_ref(source_ref):
        return frozenset()
    archive = urlsplit(archive_url).path
    if archive.endswith(".tar.gz"):
        suffix = f"tar.gz/{source_ref}" if source_ref != "main" else "tar.gz/refs/heads/main"
    elif archive.endswith(".zip"):
        suffix = f"zip/{source_ref}" if source_ref != "main" else "zip/refs/heads/main"
    else:
        return frozenset()
    return frozenset({f"https://codeload.github.com/DXBMARK/m32-bridge/{suffix}"})


def _canonical_codeload_url(url: str) -> str | None:
    if not isinstance(url, str) or "%" in url or "\\" in url:
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or port not in {None, 443}:
        return None
    if (parsed.hostname or "").lower().rstrip(".") != "codeload.github.com":
        return None
    if any(part in {".", ".."} for part in parsed.path.split("/")):
        return None
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    if not re.fullmatch(r"/DXBMARK/m32-bridge/(?:tar\.gz|zip)/(?:refs/heads/main|[0-9A-Fa-f]{7,40})", path):
        return None
    return urlunsplit(("https", "codeload.github.com", path, "", ""))


def _required_imports(*, include_paths: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in ("yaml", "mcp", "pydantic", "m32_bridge"):
        try:
            module = importlib.import_module(name)
            origin = getattr(module, "__file__", None) or "built_in"
            values[name] = {"status": "available", "path": origin} if include_paths else {"status": "available"}
        except Exception:
            values[name] = {"status": "import_failed", **({"path": "not_available"} if include_paths else {})}
    return values


def _is_refresh_source_url(url: str, allowed_urls: frozenset[str] | None = None) -> bool:
    canonical = canonical_source_url(url)
    if canonical is None or canonical != url:
        return False
    if allowed_urls is not None:
        return url in allowed_urls
    return url == "https://github.com/" or is_official_source_url(url)


def _application_health(runtime: Mapping[str, Any], state: Mapping[str, Any], checks: Mapping[str, Any]) -> str:
    runtime_state = str(runtime.get("status") or "").lower()
    if runtime_state == "error":
        return "error"
    if runtime_state == "action_required" or runtime.get("application_runtime_ready") is False:
        return "action_required"
    if any(
        checks.get(key) not in {"available", "executable", "compatible", "enabled"}
        for key in ("app_files", "venv", "launcher_file", "launcher_executable", "managed_python", "uv", "import_provenance", "frozen_launcher")
    ):
        return "action_required"
    if any(detail.get("status") != "available" for detail in checks.get("required_import_details", {}).values()):
        return "action_required"
    explicit = str(state.get("application_health") or "")
    if explicit in {"healthy", "action_required", "error"}:
        return explicit
    return "healthy"


def _application_checks(app_path: Any, launcher_path: Any, runtime: Mapping[str, Any]) -> dict[str, Any]:
    installed_runtime = bool(app_path or launcher_path)
    app = Path(str(app_path)) if app_path else Path.cwd()
    launcher = Path(str(launcher_path)) if launcher_path else None
    expected = ("pyproject.toml", "src/m32_bridge/__init__.py")
    app_files = bool(app and app.is_dir() and all((app / relative).is_file() for relative in expected))
    imports = _required_imports(include_paths=True)
    bridge_path = str(imports.get("m32_bridge", {}).get("path") or "")
    normalized_bridge = bridge_path.replace("\\", "/").lower()
    bootstrap_source = any(marker in normalized_bridge for marker in ("/tmp/bootstrap", "/private/tmp/bootstrap", "/m32-bootstrap"))
    managed_version = str(runtime.get("managed_python_version") or runtime.get("python_version") or "")
    return {
        "app_files": "available" if app_files else "not_found",
        "venv": "available" if app and (app / ".venv").is_dir() else "not_found",
        "launcher_file": "available" if (not installed_runtime or (launcher and launcher.is_file())) else "not_found",
        "launcher_executable": "executable" if (not installed_runtime or _launcher_executable(launcher)) else "not_executable",
        "managed_python": "compatible" if managed_version.startswith("3.13.") or managed_version == "3.13" else "not_compatible",
        "uv": "available" if runtime.get("uv_detected") and runtime.get("uv_path") else "not_available",
        "required_import_details": imports,
        "import_provenance": "rejected_bootstrap" if bootstrap_source else "available",
        "frozen_launcher": "enabled" if "--frozen" in str(runtime.get("launcher") or "--frozen") else "unknown",
    }


def _operational_state(configuration_state: str, connection_state: str) -> str:
    if configuration_state == "missing":
        return "setup_required"
    if configuration_state == "invalid":
        return "config_invalid"
    if connection_state == "reachable":
        return "console_connected"
    if connection_state == "unreachable":
        return "console_unreachable"
    return "console_not_checked"


def _device_verification_state(state: Mapping[str, Any], connection_state: str) -> str:
    if state.get("hardware_verified") is True:
        return "hardware_verified"
    classification = str(state.get("device_verification_status") or "").lower()
    if "mismatch" in classification:
        return "mismatch"
    if connection_state == "reachable":
        return "connected_unverified"
    if connection_state == "unreachable":
        return "unavailable"
    return "not_checked"


def _next_action(operational_state: str) -> str:
    return {
        "setup_required": "Run m32-bridge setup",
        "config_invalid": "Repair the saved configuration or run m32-bridge setup",
        "console_not_checked": "Run m32-bridge get-info when endpoint verification is needed",
        "console_unreachable": "Check console power, configured IP, UDP port, and network route",
        "console_connected": "none",
    }[operational_state]


def _launcher_executable(path: Any) -> bool:
    if not path or path == "not_available":
        return False
    candidate = Path(str(path))
    return candidate.exists() and (os.name == "nt" or os.access(candidate, os.X_OK))


def _path_visible(path: Any, environ: Mapping[str, str] | None) -> bool:
    if not path or path == "not_available":
        return False
    env = dict(os.environ if environ is None else environ)
    return str(Path(str(path)).parent) in env.get("PATH", "").split(os.pathsep)


def _derive_dns_status(statuses: Any) -> str:
    values = [str(value) for value in statuses]
    if any(value in {"reachable", "http_error", "tls_error"} for value in values):
        return "resolved"
    if any(value == "dns_error" for value in values):
        return "dns_error"
    return "not_determined"
