from __future__ import annotations

import argparse
import json
import os
import platform as py_platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .dependency_failures import (
    classify_install_failure,
    locked_wheel_message as _locked_wheel_message,
    write_install_diagnostic_log as _write_install_diagnostic_log,
)
from .application_version import resolve_staged_application_version
from .install_metadata import (
    assert_same_tag_immutable,
    build_install_metadata,
    build_official_release_urls,
    install_metadata_path,
    normalize_source_commit,
    read_install_metadata,
    validate_release_tag,
    version_from_release_tag,
    write_install_metadata,
)
from .planner import plan_dry_run_install
from .runtime_manager import (
    APPROVED_PYTHON_MINOR,
    PROJECT_PYTHON_RANGE,
    RuntimeManagerState,
    detect_uv_status,
    inspect_runtime,
    managed_python_policy,
    platform_information,
)
from .support_matrix import InstallerTarget, target_for_installer_platform
from .release_download import ReleasePreflightError, preflight_release_install
from .release_selection import (
    InstallationSelection,
    ReleaseResolution,
    ReleaseResolutionError,
    ReleaseResolver,
    ReleaseSelectionError,
    resolve_installation_selection,
)

IDEMPOTENCY_STATES = (
    "fresh_install",
    "existing_install",
    "repair",
    "update",
    "already_current",
    "partial_failure",
    "failed",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M32 Bridge user-local installer runtime")
    parser.add_argument("--surface", choices=("posix", "windows"), required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--platform", choices=("macos", "linux", "wsl", "raspberry_pi_os", "windows_powershell", "windows_cmd"))
    parser.add_argument("--version", help="Install one specific v-prefixed GitHub Release tag")
    parser.add_argument("--channel", choices=("stable", "prerelease", "main"), help="Select stable, prerelease, or explicit main development source")
    parser.add_argument("--ref", help="Install one immutable full 40-character commit SHA")
    parser.add_argument("--local", action="store_true", help="Install the current local checkout without network access")
    parser.add_argument("--current-version")
    parser.add_argument("--target-version", default=os.environ.get("M32_INSTALL_APPLICATION_VERSION"), help=argparse.SUPPRESS)
    parser.add_argument("--install-source", help=argparse.SUPPRESS)
    parser.add_argument("--source-url", default=os.environ.get("M32_INSTALL_SOURCE_URL"), help=argparse.SUPPRESS)
    parser.add_argument("--source-ref", default=os.environ.get("M32_INSTALL_SOURCE_REF"), help=argparse.SUPPRESS)
    parser.add_argument("--release-tag", default=os.environ.get("M32_INSTALL_RELEASE_TAG"), help=argparse.SUPPRESS)
    parser.add_argument("--source-commit", default=os.environ.get("M32_INSTALL_SOURCE_COMMIT"), help=argparse.SUPPRESS)
    parser.add_argument("--source-root", default=os.environ.get("M32_INSTALL_SOURCE_ROOT"), help=argparse.SUPPRESS)
    parser.add_argument("--archive-path", default=os.environ.get("M32_INSTALL_ARCHIVE_PATH"), help=argparse.SUPPRESS)
    parser.add_argument("--manifest-path", default=os.environ.get("M32_INSTALL_MANIFEST_PATH"), help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-plan", default=os.environ.get("M32_INSTALL_BOOTSTRAP_PLAN"), help=argparse.SUPPRESS)
    parser.add_argument("--confirm-dependency-actions", action="store_true")
    parser.add_argument("--bootstrap-apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--uv-bin", default=os.environ.get("M32_INSTALL_UV_BIN"), help=argparse.SUPPRESS)
    parser.add_argument("--tty", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--color", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    source_root = Path(args.source_root).resolve(strict=False) if args.source_root else _repo_root()
    bootstrap_plan: dict[str, Any] | None = None
    try:
        if args.bootstrap_plan:
            bootstrap_plan = _load_bootstrap_plan(
                Path(args.bootstrap_plan),
                surface=args.surface,
                source_root=source_root,
                version=args.version,
                channel=args.channel,
                ref=args.ref,
                local=args.local or None,
            )
            selection, resolution = _selection_and_resolution_from_bootstrap_plan(bootstrap_plan)
        else:
            selection = resolve_installation_selection(
                version=args.version,
                channel=args.channel,
                ref=args.ref,
                local=args.local or None,
                source_root=source_root,
            )
            resolution = ReleaseResolver().resolve(selection)
    except (ReleaseSelectionError, ReleaseResolutionError, ValueError, OSError) as exc:
        code = getattr(exc, "code", "INSTALL_SELECTION_CONFLICT")
        payload = _early_selection_failure(args.surface, code, str(exc))
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json_output else payload["message"])
        return 1
    try:
        _assert_internal_selection_compatible(args, selection, resolution)
    except ReleaseSelectionError as exc:
        payload = _early_selection_failure(args.surface, exc.code, str(exc))
        print(json.dumps(payload, indent=2, sort_keys=True) if args.json_output else payload["message"])
        return 1
    result = build_install_result(
        surface=args.surface,
        platform=args.platform,
        dry_run=args.dry_run,
        json_output=args.json_output,
        confirmed_dependency_actions=args.confirm_dependency_actions,
        home=os.environ.get("HOME"),
        local_app_data=os.environ.get("LOCALAPPDATA"),
        current_version=args.current_version,
        target_version=args.target_version,
        install_source=(bootstrap_plan or {}).get("install_source") or args.install_source,
        source_url=(bootstrap_plan or {}).get("source_archive_url") or args.source_url,
        source_ref=(bootstrap_plan or {}).get("source_ref") or args.source_ref,
        release_tag=(bootstrap_plan or {}).get("release_tag") or args.release_tag,
        source_commit=(bootstrap_plan or {}).get("source_commit") or args.source_commit,
        selection=selection,
        release_resolution=resolution,
        staged_source_root=source_root,
    )
    archive_path = (bootstrap_plan or {}).get("archive_path") or args.archive_path
    manifest_path = (bootstrap_plan or {}).get("manifest_path") or args.manifest_path
    if archive_path:
        result["_archive_path"] = archive_path
    if manifest_path:
        result["_manifest_path"] = manifest_path
    if bootstrap_plan is not None:
        result["_bootstrap_plan_status"] = bootstrap_plan["status"]
    tty_mode = bool(args.tty or (sys.stdin.isatty() and sys.stdout.isatty() and not args.json_output))
    if not args.dry_run:
        if not result["installer_can_continue"]:
            if args.json_output:
                print(json.dumps(result, indent=2, sort_keys=True))
            elif tty_mode:
                _print_plain(args.surface, result, dry_run=args.dry_run)
            else:
                _print_plain(args.surface, result, dry_run=args.dry_run, tty=tty_mode, color=args.color)
            return 1
        result = perform_apply_install(
            args.surface,
            result,
            bootstrap_apply=args.bootstrap_apply,
            uv_bin=args.uv_bin,
        )

    if args.json_output:
        print(json.dumps(_without_private_fields(result), indent=2, sort_keys=True))
    elif tty_mode and result.get("runtime_info", {}).get("application_runtime_ready"):
        try:
            return handoff_to_installed_runtime(args.surface, result)
        except (OSError, RuntimeError) as exc:
            diagnostic_log = _write_install_diagnostic_log(
                _diagnostic_log_dir(result),
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
            )
            failure = _controlled_install_failure(
                args.surface,
                result,
                error_code="INSTALLED_RUNTIME_HANDOFF_FAILED",
                failed_step="runtime_tty_handoff",
                message="The installed Runtime Console could not be started.",
                recovery_action=f"Run the installed launcher directly: {result['launcher_path']} run",
                diagnostic_log_path=str(diagnostic_log),
            )
            _print_plain(args.surface, failure, dry_run=False)
            return 1
    else:
        _print_plain(args.surface, result, dry_run=args.dry_run)
    return 0 if result["ok"] else 1



_BOOTSTRAP_PLAN_FIELDS = frozenset(
    {
        "schema_version",
        "ok",
        "status",
        "surface",
        "dry_run",
        "requested_selection",
        "selection_kind",
        "release_channel",
        "release_tag",
        "source_commit",
        "source_ref",
        "install_source",
        "manifest_status",
        "manifest_schema_version",
        "archive_checksum_status",
        "staged_application_version",
        "application_version",
        "identity_status",
        "source_archive_url",
        "source_archive_sha256",
        "installer_asset_url",
        "installer_asset_sha256",
        "manifest_path",
        "archive_path",
        "source_root",
        "user_local",
        "admin_required",
        "system_python_modified",
        "network_scan",
        "console_probe",
        "osc_writes_sent",
        "hardware_verified",
        "production_live_ready",
    }
)
_BOOTSTRAP_PLAN_MAX_BYTES = 256 * 1024


def _load_bootstrap_plan(
    path: Path,
    *,
    surface: str,
    source_root: Path,
    version: str | None,
    channel: str | None,
    ref: str | None,
    local: bool | None,
) -> dict[str, Any]:
    if local:
        raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "A verified remote bootstrap plan cannot be combined with --local.")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Verified bootstrap plan is unavailable.") from exc
    if not payload or len(payload) > _BOOTSTRAP_PLAN_MAX_BYTES:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Verified bootstrap plan size is invalid.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Verified bootstrap plan JSON is invalid.") from exc
    if not isinstance(document, dict) or set(document) != _BOOTSTRAP_PLAN_FIELDS:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Verified bootstrap plan fields are invalid.")
    if (
        document.get("schema_version") != "1"
        or document.get("ok") is not True
        or document.get("dry_run") is not False
        or document.get("surface") != surface
        or document.get("status") not in {"release_preflight_complete", "commit_preflight_complete"}
        or document.get("user_local") is not True
        or document.get("admin_required") is not False
        or document.get("system_python_modified") is not False
        or document.get("network_scan") != "not_run"
        or document.get("console_probe") != "not_run"
        or document.get("osc_writes_sent") != 0
        or document.get("identity_status") != "validated"
    ):
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Verified bootstrap plan state is invalid.")
    plan_dir = path.parent.expanduser().resolve(strict=False)
    plan_root = Path(str(document.get("source_root") or "")).expanduser()
    if not plan_root.is_absolute() or plan_root.resolve(strict=False) != source_root.resolve(strict=False):
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap plan source root does not match --source-root.")
    try:
        plan_root.resolve(strict=False).relative_to(plan_dir)
    except ValueError as exc:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap plan source root escapes its staging directory.") from exc
    required = (plan_root / "pyproject.toml", plan_root / "uv.lock", plan_root / "src" / "m32_bridge")
    if not required[0].is_file() or not required[1].is_file() or not required[2].is_dir():
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap plan source root is incomplete.")
    commit = normalize_source_commit(document.get("source_commit"))
    if document.get("source_ref") != commit:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap plan source_ref does not match source_commit.")
    if document.get("staged_application_version") != document.get("application_version"):
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap plan application version fields disagree.")
    install_source = document.get("install_source")
    kind = document.get("selection_kind")
    if install_source == "github_release_asset":
        tag = validate_release_tag(document.get("release_tag"))
        if kind not in {"stable", "version", "prerelease"}:
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Release bootstrap selection kind is invalid.")
        if document.get("manifest_status") != "validated" or document.get("archive_checksum_status") != "verified":
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Release bootstrap verification is incomplete.")
        for field in ("manifest_path", "archive_path"):
            candidate = Path(str(document.get(field) or ""))
            if not candidate.is_absolute() or not candidate.is_file():
                raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", f"Bootstrap plan {field} is unavailable.")
            try:
                candidate.resolve(strict=False).relative_to(plan_dir)
            except ValueError as exc:
                raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", f"Bootstrap plan {field} escapes staging.") from exc
        archive_name = "m32-bridge-source.zip" if surface == "windows" else "m32-bridge-source.tar.gz"
        installer_name = "install.ps1" if surface == "windows" else "install.sh"
        expected_archive_url = f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/{archive_name}"
        expected_installer_url = f"https://github.com/DXBMARK/m32-bridge/releases/download/{tag}/{installer_name}"
        if document.get("source_archive_url") != expected_archive_url or document.get("installer_asset_url") != expected_installer_url:
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap Release asset URLs do not match tag and platform.")
        if document.get("application_version") != version_from_release_tag(tag):
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap Release version does not match release_tag.")
        for field in ("source_archive_sha256", "installer_asset_sha256"):
            value = document.get(field)
            if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", f"Bootstrap plan {field} is invalid.")
        if version and validate_release_tag(version) != tag:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Bootstrap release tag conflicts with --version.")
        if channel and kind != channel:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Bootstrap release channel conflicts with --channel.")
        if ref:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Release bootstrap plan conflicts with --ref.")
    elif install_source in {"github_commit_archive", "github_main"}:
        expected_kind = "commit" if install_source == "github_commit_archive" else "main"
        if kind != expected_kind or document.get("release_tag") is not None:
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Commit bootstrap identity is invalid.")
        archive = Path(str(document.get("archive_path") or ""))
        if not archive.is_absolute() or not archive.is_file():
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap commit archive is unavailable.")
        try:
            archive.resolve(strict=False).relative_to(plan_dir)
        except ValueError as exc:
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap commit archive escapes staging.") from exc
        expected_source_url = build_official_release_urls(surface, commit)["source_archive_url"]
        if document.get("source_archive_url") != expected_source_url:
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap commit archive URL does not match source_commit.")
        if document.get("manifest_path") is not None or document.get("manifest_status") != "not_applicable":
            raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Commit bootstrap plan must not claim Release manifest provenance.")
        if ref and normalize_source_commit(ref) != commit:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Bootstrap commit conflicts with --ref.")
        if channel and channel != expected_kind:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Bootstrap commit mode conflicts with --channel.")
        if version:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Commit bootstrap plan conflicts with --version.")
    else:
        raise ReleaseSelectionError("BOOTSTRAP_PLAN_INVALID", "Bootstrap install_source is invalid.")
    return document


def _selection_and_resolution_from_bootstrap_plan(
    plan: dict[str, Any],
) -> tuple[InstallationSelection, ReleaseResolution]:
    kind = str(plan["selection_kind"])
    tag = plan.get("release_tag")
    commit = normalize_source_commit(plan.get("source_commit"))
    selection = InstallationSelection(
        requested_selection=str(plan["requested_selection"]),
        kind=kind,
        channel=plan.get("release_channel") if kind != "version" else None,
        version=tag[1:] if kind == "version" and isinstance(tag, str) else None,
        release_tag=tag if kind == "version" else None,
        source_commit=commit if kind == "commit" else None,
        install_source=str(plan["install_source"]),
        origin="verified_bootstrap_plan",
    )
    resolution = ReleaseResolution(
        requested_selection=str(plan["requested_selection"]),
        selection_kind=kind,
        release_channel=plan.get("release_channel"),
        release_tag=tag,
        source_commit=commit,
        source_ref=commit,
        install_source=str(plan["install_source"]),
        published_at=None,
        manifest_asset_url=plan.get("manifest_path"),
    )
    return selection, resolution

def _prepare_install_preflight(surface: str, result: dict[str, Any]) -> dict[str, Any]:
    """Finish all source identity checks before any install target is touched."""

    source_root = Path(str(result.get("_source_root") or _repo_root())).resolve(strict=False)
    install_source = str(result.get("install_source") or "local_checkout")
    if install_source == "github_release_asset":
        raw_resolution = result.get("_release_resolution")
        if not isinstance(raw_resolution, dict):
            raise ReleasePreflightError("RELEASE_RESPONSE_INVALID", "Resolved Release identity is unavailable.")
        resolution = ReleaseResolution(**raw_resolution)
        manifest_document: bytes | None = None
        manifest_path = result.get("_manifest_path")
        if manifest_path:
            try:
                manifest_document = Path(str(manifest_path)).read_bytes()
            except OSError as exc:
                raise ReleasePreflightError("RELEASE_MANIFEST_MISSING", "Staged Release manifest is unavailable.") from exc
        preflight = preflight_release_install(
            resolution,
            platform="windows" if surface == "windows" else "posix",
            manifest_document=manifest_document,
            archive_path=result.get("_archive_path"),
            requested_version=(resolution.release_tag if resolution.selection_kind == "version" else None),
        )
        result.update(preflight.as_dict())
        result.update(
            {
                "application_version": preflight.staged_application_version,
                "application_version_source": "staged_pyproject",
                "release_tag": preflight.resolved_release_tag,
                "source_commit": preflight.resolved_source_commit,
                "source_ref": preflight.resolved_source_commit,
                "_source_root": preflight.staged_source_root,
            }
        )
    else:
        staged = resolve_staged_application_version(source_root)
        if staged.status != "resolved":
            raise ReleasePreflightError("RELEASE_VERSION_MISMATCH", "Selected source has no valid staged pyproject.toml version.")
        assertion = result.get("target_version")
        if assertion and str(assertion) != staged.version:
            raise ReleasePreflightError("RELEASE_VERSION_MISMATCH", "Requested version assertion does not match staged source truth.")
        if install_source in {"github_commit_archive", "github_main"}:
            commit = result.get("source_commit") or result.get("source_ref")
            from .install_metadata import build_official_release_urls, normalize_source_commit

            commit = normalize_source_commit(commit)
            result["source_commit"] = commit
            result["source_ref"] = commit
            result["source_url"] = build_official_release_urls(surface, commit)["source_archive_url"]
        elif install_source != "local_checkout":
            raise ReleasePreflightError("SOURCE_BOUNDARY_REJECTED", "Unsupported installation source.")
        result.update(
            {
                "selection_state": result.get("selection") or "local",
                "resolved_release_tag": None,
                "resolved_source_commit": result.get("source_commit"),
                "manifest_status": "not_applicable",
                "manifest_schema_version": None,
                "archive_checksum_status": "not_applicable" if install_source == "local_checkout" else "verified_by_commit_source",
                "staged_application_version": staged.version,
                "identity_status": "validated",
                "application_version": staged.version,
                "application_version_source": "staged_pyproject",
                "_source_root": str(source_root),
            }
        )

    existing = read_install_metadata(install_metadata_path(app_path=Path(str(result["app_path"]))))
    if existing.get("status") == "metadata_valid":
        assert_same_tag_immutable(
            existing.get("data") or {},
            {"release_tag": result.get("release_tag"), "source_commit": result.get("source_commit")},
        )
    return result


def _early_selection_failure(surface: str, code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed",
        "error_code": code,
        "message": message,
        "surface": surface,
        "application_runtime_ready": False,
        "full_tty_allowed": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _assert_internal_selection_compatible(
    args: argparse.Namespace,
    selection: InstallationSelection,
    resolution: ReleaseResolution,
) -> None:
    if args.release_tag and args.release_tag != resolution.release_tag:
        raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Internal release_tag conflicts with public selection.")
    if args.source_commit and str(args.source_commit).lower() != str(resolution.source_commit or "").lower():
        raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Internal source_commit conflicts with public selection.")
    if args.install_source and args.install_source != resolution.install_source:
        legacy = {
            "github_release_or_archive": "github_release_asset",
            "github_raw": "github_commit_archive",
        }.get(args.install_source, args.install_source)
        if legacy != resolution.install_source:
            raise ReleaseSelectionError("INSTALL_SELECTION_CONFLICT", "Internal install_source conflicts with public selection.")


def perform_apply_install(
    surface: str,
    result: dict[str, Any],
    *,
    bootstrap_apply: bool = False,
    uv_bin: str | None = None,
) -> dict[str, Any]:
    bootstrap_apply = bool(bootstrap_apply or result.get("bootstrap_apply"))
    uv_bin = uv_bin or result.get("uv_bin") or os.environ.get("M32_INSTALL_UV_BIN")
    install_metadata_status = "not_attempted"
    metadata_warning: str | None = None
    try:
        _prepare_install_preflight(surface, result)
        pending_metadata = build_install_metadata(surface, result)
    except (ReleasePreflightError, ReleaseSelectionError, ReleaseResolutionError, ValueError) as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code=getattr(exc, "code", str(exc).split(":", 1)[0]),
            failed_step="release_preflight",
            message=str(exc),
            recovery_action="Review the selected Release identity and rerun the installer; no installed files were replaced.",
        )
    try:
        resolved_uv_bin = _resolve_uv_executable(surface, uv_bin)
        result["bootstrap_apply"] = bootstrap_apply
        _apply_user_local_install(surface, result, uv_bin=resolved_uv_bin)
        candidate_readiness = result.pop("_candidate_readiness", None)
        runtime_readiness = dict(
            candidate_readiness
            or (
                _synchronize_application_runtime(surface, result, uv_bin=resolved_uv_bin)
                if bootstrap_apply
                else {
                    "ready": True,
                    "managed_python_version": result.get("runtime_info", {}).get("managed_python_version") or "3.13.x",
                    "required_imports": "not_run_internal_call",
                }
            )
        )
        if not runtime_readiness.get("ready"):
            raise InstallStepError(
                error_code="APPLICATION_RUNTIME_NOT_READY",
                failed_step="application_runtime_readiness",
                message=str(runtime_readiness.get("message") or "Required application imports did not pass."),
                recovery_action="Rerun the installer to repair the user-local application environment.",
            )
        # Metadata is provenance evidence, not part of application readiness.
        # Persist it only after all materialization/readiness gates have passed.
        try:
            write_install_metadata(
                pending_metadata,
                app_path=Path(str(result["app_path"])),
            )
            (Path(str(result["app_path"])) / ".install-provenance-pending").unlink(missing_ok=True)
            install_metadata_status = "written"
        except OSError as exc:
            install_metadata_status = "write_failed"
            metadata_warning = "Install metadata could not be written; source provenance is unavailable."
            _best_effort_metadata_diagnostic(result, exc)
    except OSError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code="APP_MATERIALIZATION_FAILED",
            failed_step="application_install",
            message=f"Application files could not be installed: {exc}",
            recovery_action="Rerun the installer to repair the user-local application files.",
            partial=False,
        )
    except ValueError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code="INSTALL_BOUNDARY_REJECTED",
            failed_step="install_boundary",
            message=str(exc),
            recovery_action="Review the user-local target paths and rerun the installer.",
        )
    except InstallStepError as exc:
        return _controlled_install_failure(
            surface,
            result,
            error_code=exc.error_code,
            failed_step=exc.failed_step,
            message=exc.message,
            recovery_action=exc.recovery_action,
            partial=False,
            dependency_package=exc.dependency_package,
            target_platform=exc.target_platform,
            python_version=exc.python_version,
            diagnostic_log_path=exc.diagnostic_log_path,
        )

    status = "already_current" if result["status"] in {"fresh_install", "repair", "update"} else result["status"]
    guidance_warning: str | None = None
    try:
        mcp_guidance, lifecycle_guidance = _post_install_guidance(
            surface,
            result,
            status=status,
        )
    except Exception as exc:
        guidance_warning = (
            "Post-install guidance was deferred; "
            "the installed application remains ready."
        )
        _best_effort_post_install_guidance_diagnostic(
            result,
            exc,
        )
        mcp_guidance = _deferred_mcp_guidance(
            result,
            warning=guidance_warning,
        )
        lifecycle_guidance = {
            "ok": True,
            "status": "LIFECYCLE_GUIDANCE_DEFERRED",
            "result_status": status,
            "network_scan": "not_run",
            "console_probe": "not_run",
            "osc_writes_sent": 0,
        }
    public_result = _without_private_fields(result)
    public_result.pop("source_status", None)
    runtime_info = {
        **dict(public_result.get("runtime_info") or {}),
        "application_runtime_ready": True,
        "full_tty_allowed": True,
        "managed_python_version": runtime_readiness.get("managed_python_version", "3.13.x"),
        "required_imports": runtime_readiness.get("required_imports", "ok"),
        "admin_used": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
        "install_metadata_status": install_metadata_status,
        "post_install_guidance_status": str(mcp_guidance.get("status") or "unknown"),
    }
    completed = {
        **public_result,
        "ok": True,
        "status": status,
        "path_updated": False,
        "runtime_info": runtime_info,
        "first_run_setup": {
            "offered": True,
            "interactive": False,
            "attempted_path": "not_attempted",
            "classification": None,
            "osc_writes_sent": 0,
            "hardware_verified": False,
        },
        "runtime_handoff": {
            "launcher_path": str(public_result["launcher_path"]),
            "subcommand": "run",
            "installed_runtime": True,
            "bootstrap_runtime_tty": False,
            "implicit_sync": False,
        },
        "verification_guidance": {
            "offered": True,
            "commands": [
                "m32-bridge health",
                "m32-bridge setup",
                "m32-bridge get-info",
                "m32-bridge detect-device",
                "m32-bridge doctor-runtime",
            ],
            "osc_writes_sent": 0,
            "hardware_verified": False,
            "production_live_ready": False,
        },
        "mcp_guidance": mcp_guidance,
        "lifecycle_guidance": lifecycle_guidance,
        "message": _message({**result, "status": status}),
        "hardware_verified": False,
        "production_live_ready": False,
        "osc_writes_sent": 0,
    }
    if guidance_warning:
        completed["runtime_info"]["post_install_guidance_warning"] = guidance_warning
        completed["recommendations"] = [
            *list(completed.get("recommendations") or []),
            guidance_warning,
        ]
    if metadata_warning:
        completed["runtime_info"]["install_metadata_warning"] = metadata_warning
        completed["recommendations"] = [
            *list(completed.get("recommendations") or []),
            metadata_warning,
        ]
    return completed


class InstallStepError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        failed_step: str,
        message: str,
        recovery_action: str,
        dependency_package: str | None = None,
        target_platform: str | None = None,
        python_version: str | None = None,
        diagnostic_log_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.failed_step = failed_step
        self.message = message
        self.recovery_action = recovery_action
        self.dependency_package = dependency_package
        self.target_platform = target_platform
        self.python_version = python_version
        self.diagnostic_log_path = diagnostic_log_path


def _resolve_uv_executable(surface: str, uv_bin: str | None) -> str:
    if not uv_bin:
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message="The absolute uv executable path is required before launcher creation.",
            recovery_action="Rerun the installer so it can pass the detected user-local uv path to the launcher.",
        )
    candidate = Path(uv_bin).expanduser()
    if not candidate.is_absolute() or not candidate.is_file():
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message=f"The uv executable path is unavailable or not absolute: {uv_bin}",
            recovery_action="Rerun the installer so it can verify the user-local uv executable before launcher creation.",
        )
    if surface != "windows" and not os.access(candidate, os.X_OK):
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message=f"The uv executable is not executable: {candidate}",
            recovery_action="Restore execute permission on the user-local uv binary, then rerun the installer.",
        )
    return str(candidate.resolve())


def _controlled_install_failure(
    surface: str,
    result: dict[str, Any],
    *,
    error_code: str,
    failed_step: str,
    message: str,
    recovery_action: str,
    partial: bool = False,
    dependency_package: str | None = None,
    target_platform: str | None = None,
    python_version: str | None = None,
    diagnostic_log_path: str | None = None,
) -> dict[str, Any]:
    from .lifecycle import render_lifecycle_guidance

    status = "partial_failure" if partial else "failed"
    public_result = _without_private_fields(result)
    runtime_info = {
        **dict(public_result.get("runtime_info") or {}),
        "application_runtime_ready": False,
        "full_tty_allowed": False,
        "failed_step": failed_step,
        "recovery_action": recovery_action,
        "admin_used": False,
        "network_scan": "not_run",
        "console_probe": "not_run",
        "dependency_package": dependency_package,
        "target_platform": target_platform,
        "python_version": python_version,
        "diagnostic_log_path": diagnostic_log_path,
    }
    payload = {
        **public_result,
        "ok": False,
        "status": status,
        "error_code": error_code,
        "failed_step": failed_step,
        "message": message,
        "installer_can_continue": False,
        "runtime_info": runtime_info,
        "system_python_modified": False,
        "recovery_action": recovery_action,
        "lifecycle_guidance": render_lifecycle_guidance(surface=surface, install_status=status),
        "hardware_verified": False,
        "production_live_ready": False,
        "osc_writes_sent": 0,
    }
    optional = {
        "dependency_package": dependency_package,
        "target_platform": target_platform,
        "python_version": python_version,
        "diagnostic_log_path": diagnostic_log_path,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    return payload


def _synchronize_application_runtime(surface: str, result: dict[str, Any], *, uv_bin: str | None = None) -> dict[str, Any]:
    uv_bin = Path(str(uv_bin or os.environ.get("M32_INSTALL_UV_BIN") or ""))
    if not str(uv_bin) or not uv_bin.is_file() or not os.access(uv_bin, os.X_OK):
        raise InstallStepError(
            error_code="UV_EXECUTABLE_UNAVAILABLE",
            failed_step="uv_reuse",
            message="The user-local uv executable could not be used by the current installer process.",
            recovery_action="Rerun the installer; no shell restart or PATH export should be required.",
        )
    app_path = Path(result["app_path"])
    target = _target_for_result(result)
    diagnostic_log_dir = _diagnostic_log_dir(result)
    if target is not None and not target.release_supported:
        diagnostic_log = _write_install_diagnostic_log(
            diagnostic_log_dir,
            stdout="",
            stderr=target.support_blocker,
        )
        raise InstallStepError(
            error_code="LOCKED_WHEEL_UNAVAILABLE",
            failed_step="application_sync",
            message=_locked_wheel_message(),
            recovery_action="Install a corrected M32 Bridge release or provide the diagnostic log to support.",
            dependency_package=target.blocked_dependency,
            target_platform=target.target_id,
            python_version=target.python_version,
            diagnostic_log_path=str(diagnostic_log),
        )
    base = [str(uv_bin), "--directory", str(app_path)]
    env = dict(os.environ)
    env["UV_MANAGED_PYTHON"] = "1"
    env["UV_NO_BUILD"] = "1"
    source_path = str(app_path / "src")
    env["PYTHONPATH"] = source_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    target_id = target.target_id if target is not None else str(result.get("platform") or "unknown")
    sync = _run_install_command(
        [
            *base,
            "sync",
            "--frozen",
            "--managed-python",
            "--python",
            APPROVED_PYTHON_MINOR,
            "--no-build",
            "--no-install-project",
        ],
        env=env,
        error_code="APPLICATION_SYNC_FAILED",
        failed_step="application_sync",
        recovery_action="Rerun the installer to repair the frozen application environment.",
        diagnostic_log_dir=diagnostic_log_dir,
        target_platform=target_id,
        python_version=APPROVED_PYTHON_MINOR,
    )
    del sync
    smoke_code = "import yaml, mcp, pydantic, m32_bridge; print('READY')"
    smoke = _run_install_command(
        [
            *base,
            "run",
            "--frozen",
            "--managed-python",
            "--python",
            APPROVED_PYTHON_MINOR,
            "--no-build",
            "--no-sync",
            "python",
            "-c",
            smoke_code,
        ],
        env=env,
        error_code="REQUIRED_IMPORT_SMOKE_FAILED",
        failed_step="required_import_smoke",
        recovery_action="Rerun the installer to restore application dependencies.",
        diagnostic_log_dir=diagnostic_log_dir,
        target_platform=target_id,
        python_version=APPROVED_PYTHON_MINOR,
    )
    version = _run_install_command(
        [
            *base,
            "run",
            "--frozen",
            "--managed-python",
            "--python",
            APPROVED_PYTHON_MINOR,
            "--no-build",
            "--no-sync",
            "python",
            "-c",
            "import platform; print(platform.python_version())",
        ],
        env=env,
        error_code="MANAGED_PYTHON_CHECK_FAILED",
        failed_step="managed_python_check",
        recovery_action="Rerun the installer to repair managed CPython 3.13.",
        diagnostic_log_dir=diagnostic_log_dir,
        target_platform=target_id,
        python_version=APPROVED_PYTHON_MINOR,
    )
    launcher = Path(result["launcher_path"])
    ready = app_path.is_dir() and (app_path / ".venv").is_dir() and launcher.is_file() and smoke.stdout.strip() == "READY"
    return {
        "ready": ready,
        "managed_python_version": version.stdout.strip(),
        "required_imports": "ok" if smoke.stdout.strip() == "READY" else "failed",
    }


def _without_private_fields(result: dict[str, Any]) -> dict[str, Any]:
    identity_keys = {
        "application_version",
        "application_version_source",
        "selection",
        "requested_selection",
        "release_channel",
        "release_tag",
        "source_commit",
        "selection_state",
        "resolved_release_tag",
        "resolved_source_commit",
        "manifest_status",
        "manifest_schema_version",
        "archive_checksum_status",
        "staged_application_version",
        "identity_status",
        "source_archive_url",
        "source_archive_sha256",
        "installer_asset_url",
        "installer_asset_sha256",
    }
    public = {
        key: value
        for key, value in result.items()
        if not key.startswith("_") and key not in {"bootstrap_apply", "uv_bin"} and key not in identity_keys
    }
    identity = {key: result.get(key) for key in identity_keys if key in result}
    if identity:
        public["runtime_info"] = {**dict(public.get("runtime_info") or {}), "release_preflight": identity}
    public["install_source"] = {
        "github_release_asset": "release_archive",
        "github_commit_archive": "github_release_or_archive",
        "github_main": "github_release_or_archive",
    }.get(str(result.get("install_source")), result.get("install_source"))
    return public


def _run_install_command(
    argv: list[str],
    *,
    env: dict[str, str],
    error_code: str,
    failed_step: str,
    recovery_action: str,
    diagnostic_log_dir: Path,
    target_platform: str,
    python_version: str,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, env=env)
    except OSError as exc:
        diagnostic_log = _write_install_diagnostic_log(diagnostic_log_dir, stdout="", stderr=str(exc))
        raise InstallStepError(
            error_code=error_code,
            failed_step=failed_step,
            message=f"{failed_step} could not start: {exc}",
            recovery_action=recovery_action,
            target_platform=target_platform,
            python_version=python_version,
            diagnostic_log_path=str(diagnostic_log),
        ) from None
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        classification = classify_install_failure(output, default_error_code=error_code)
        diagnostic_log = _write_install_diagnostic_log(
            diagnostic_log_dir,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        is_missing_wheel = classification.error_code == "LOCKED_WHEEL_UNAVAILABLE"
        raise InstallStepError(
            error_code=classification.error_code,
            failed_step=failed_step,
            message=_locked_wheel_message() if is_missing_wheel else f"{failed_step} failed. See the diagnostic log for complete command output.",
            recovery_action=(
                "Install a corrected M32 Bridge release or provide the diagnostic log to support."
                if is_missing_wheel
                else recovery_action
            ),
            dependency_package=classification.dependency_package,
            target_platform=target_platform,
            python_version=python_version,
            diagnostic_log_path=str(diagnostic_log),
        )
    return completed


def _target_for_result(result: dict[str, Any]) -> InstallerTarget | None:
    platform = str(result.get("platform") or "")
    architecture = result.get("architecture") or (result.get("platform_info") or {}).get("architecture")
    return target_for_installer_platform(platform, str(architecture) if architecture else None)


def _diagnostic_log_dir(result: dict[str, Any]) -> Path:
    if result.get("_diagnostic_log_dir_override"):
        return Path(str(result["_diagnostic_log_dir_override"]))
    return Path(result["app_path"]).parent / "logs"


def _best_effort_metadata_diagnostic(result: dict[str, Any], exc: BaseException) -> None:
    try:
        _write_install_diagnostic_log(
            _diagnostic_log_dir(result),
            stdout="",
            stderr=f"install metadata {type(exc).__name__}: {exc}",
        )
    except Exception:
        # Diagnostic persistence must never reverse a ready application state.
        return


def _best_effort_post_install_guidance_diagnostic(
    result: dict[str, Any],
    exc: Exception,
) -> None:
    try:
        _write_install_diagnostic_log(
            _diagnostic_log_dir(result),
            stdout="",
            stderr=(
                "post-install guidance "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    except Exception:
        return


def _deferred_mcp_guidance(
    result: dict[str, Any],
    *,
    warning: str,
) -> dict[str, Any]:
    launcher_path = str(result.get("launcher_path") or "")
    return {
        "ok": True,
        "status": "MCP_GUIDANCE_DEFERRED",
        "product": "X32-Bridge MCP",
        "version": str(
            result.get("target_version")
            or result.get("application_version")
            or VERSION
        ),
        "server_name": "x32-bridge-mcp",
        "launcher_path": launcher_path,
        "command": launcher_path,
        "args": ["mcp-server"],
        "runtime_config_inspection": "not_checked",
        "console_configured": None,
        "configured_host": None,
        "configured_port": None,
        "manual_copy_only": True,
        "automatic_client_config_write": False,
        "reads_saved_user_config_by_default": True,
        "warning": warning,
        "network_scan": False,
        "console_probe": "not_run",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
    }


def _post_install_guidance(surface: str, result: dict[str, Any], *, status: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from .lifecycle import render_lifecycle_guidance
    from .mcp_guidance import render_mcp_guidance

    launcher_path = Path(str(result.get("launcher_path", "")))
    launcher_root = launcher_path.parents[2] if len(launcher_path.parents) >= 3 else None
    mcp_guidance = render_mcp_guidance(
        os_family="windows" if surface == "windows" else None,
        home=None if surface == "windows" else launcher_root,
        local_app_data=launcher_root if surface == "windows" else None,
        version=str(
            result.get("target_version")
            or result.get("application_version")
            or VERSION
        ),
        read_runtime_config=False,
    )
    return mcp_guidance, render_lifecycle_guidance(surface=surface, install_status=status)


def _run_tty_app(surface: str, result: dict[str, Any], *, dry_run: bool, color: bool) -> None:
    from .tty_app import run_tty_app

    run_tty_app(surface, result, dry_run=dry_run, color=color)


def installer_contact_text(*args: Any, **kwargs: Any) -> str:
    from .tty_app import installer_contact_text as render

    return render(*args, **kwargs)


def installer_help_text(*args: Any, **kwargs: Any) -> str:
    from .tty_app import installer_help_text as render

    return render(*args, **kwargs)


def render_tty_installer(*args: Any, **kwargs: Any) -> str:
    from .tty_app import render_tty_installer as render

    return render(*args, **kwargs)


def build_install_result(
    *,
    surface: str,
    platform: str | None = None,
    dry_run: bool = True,
    json_output: bool = False,
    confirmed_dependency_actions: bool = False,
    home: Path | str | None = None,
    local_app_data: Path | str | None = None,
    uv_state: RuntimeManagerState | None = None,
    current_version: str | None = None,
    target_version: str | None = None,
    install_source: str | None = None,
    source_url: str | None = None,
    source_ref: str | None = None,
    release_tag: str | None = None,
    source_commit: str | None = None,
    selection: InstallationSelection | None = None,
    release_resolution: ReleaseResolution | None = None,
    staged_source_root: Path | str | None = None,
) -> dict[str, Any]:
    surface_platform = platform or _detect_platform(surface)
    source_root = Path(staged_source_root).resolve(strict=False) if staged_source_root is not None else _repo_root()
    explicit_install_source = install_source
    selection = selection or resolve_installation_selection(source_root=source_root)
    if release_resolution is None:
        if explicit_install_source and explicit_install_source != selection.install_source:
            release_resolution = ReleaseResolution(
                selection.requested_selection,
                selection.kind,
                selection.channel,
                release_tag,
                source_commit,
                source_ref,
                explicit_install_source,
            )
        elif selection.kind == "local":
            release_resolution = ReleaseResolution("local", "local", None, None, None, None, "local_checkout")
        else:
            release_resolution = ReleaseResolution(
                selection.requested_selection,
                selection.kind,
                selection.channel,
                release_tag,
                source_commit,
                source_ref,
                explicit_install_source or selection.install_source,
            )
    install_source = release_resolution.install_source
    release_tag = release_resolution.release_tag or release_tag
    source_commit = release_resolution.source_commit or source_commit
    source_ref = release_resolution.source_ref or source_ref
    if install_source == "local_checkout":
        version_resolution = resolve_staged_application_version(source_root)
        if version_resolution.status != "resolved":
            raise ValueError("PROJECT_VERSION_INVALID: local checkout pyproject.toml is invalid.")
        application_version = version_resolution.version
        version_source = "local_checkout_pyproject"
    else:
        # Remote source truth is finalized only after extraction in preflight.
        application_version = None
        version_source = None
    app_exists, launcher_exists = _detect_existing_state(surface, home=home, local_app_data=local_app_data)
    runtime = uv_state or _uv_state_from_environment()
    uv_detected = runtime.uv_status in {"present", "installed_user_local"}
    required_actions = [] if uv_detected else [_uv_required_action(surface, _dependency_target_root(surface, home, local_app_data))]

    result = plan_dry_run_install(
        platform=surface_platform,
        home=home or os.environ.get("HOME"),
        local_app_data=local_app_data or os.environ.get("LOCALAPPDATA"),
        uv_state=runtime,
        current_version=current_version,
        target_version=application_version,
        app_exists=app_exists,
        launcher_exists=launcher_exists,
        partial_failure_marker=_partial_failure_marker(surface, home=home, local_app_data=local_app_data),
    )

    missing_uv = not uv_detected
    if missing_uv:
        result["status"] = "RUNTIME_SETUP_REQUIRED" if dry_run or json_output else "UV_MISSING"
        result["ok"] = False
        result["error_code"] = "RUNTIME_SETUP_REQUIRED" if dry_run or json_output else "UV_MISSING_CONFIRMATION_REQUIRED"
    if result.get("status") == "partial_failure":
        result["ok"] = False
        result["error_code"] = result.get("error_code") or "PARTIAL_FAILURE_RECOVERY_REQUIRED"
    platform_info = platform_information()
    result.update(
        {
            "dry_run": dry_run,
            "install_source": install_source,
            "source_url": source_url,
            "source_ref": source_ref,
            "target_version": target_version,
            "application_version": application_version,
            "application_version_source": version_source,
            "selection": selection.requested_selection,
            "requested_selection": selection.requested_selection,
            "release_channel": release_resolution.release_channel,
            "uv_required": True,
            "uv_detected": uv_detected,
            "python_required": True,
            "global_python_required": False,
            "python_managed_by_uv": True,
            "managed_python_policy": managed_python_policy(),
            "approved_python_minor": APPROVED_PYTHON_MINOR,
            "project_python_range": PROJECT_PYTHON_RANGE,
            "runtime_info": inspect_runtime(),
            "platform_info": platform_info,
            "architecture": result.get("architecture") or platform_info.get("architecture"),
            "system_python_modified": False,
            "global_python_installed": False,
            "default_python_aliases_installed": False,
            "installer_can_continue": uv_detected and (not required_actions or confirmed_dependency_actions),
            "confirmation_required": bool(required_actions),
            "required_actions": required_actions,
            "_source_root": str(source_root),
            "_release_resolution": asdict(release_resolution),
        }
    )
    if release_tag:
        result["release_tag"] = release_tag
    if source_commit:
        result["source_commit"] = source_commit
    result["lifecycle_guidance"] = _lifecycle_guidance(surface, result)
    result["message"] = _message(result)
    result["recommendations"] = _recommendations(surface, result)
    _assert_user_local_result(surface, result)
    if dry_run:
        plan_keys = {
            "application_version",
            "application_version_source",
            "selection",
            "requested_selection",
            "release_channel",
            "release_tag",
            "source_commit",
        }
        plan = {key: result.pop(key) for key in tuple(plan_keys) if key in result}
        result.pop("_source_root", None)
        result.pop("_release_resolution", None)
        result["runtime_info"] = {**dict(result.get("runtime_info") or {}), "release_selection_plan": plan}
    return result


def _lifecycle_guidance(surface: str, result: dict[str, Any]) -> dict[str, Any]:
    from .lifecycle import render_lifecycle_guidance

    return render_lifecycle_guidance(
        surface=surface,
        install_status=str(result.get("status") or "already_current"),
        app_path=result.get("app_path"),
        launcher_path=result.get("launcher_path"),
    )


def _detect_platform(surface: str) -> str:
    if surface == "windows":
        return "windows_powershell"
    if _is_wsl():
        return "wsl"
    system = py_platform.system().lower()
    if system == "darwin":
        return "macos"
    if _is_raspberry_pi_os():
        return "raspberry_pi_os"
    return "linux"


def _is_wsl() -> bool:
    text = ""
    try:
        text = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass
    return "microsoft" in text.lower() or "WSL_DISTRO_NAME" in os.environ


def _is_raspberry_pi_os() -> bool:
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        os_release = ""
    return "raspbian" in os_release or "raspberry pi os" in os_release


def _uv_state_from_environment() -> RuntimeManagerState:
    if os.environ.get("M32_INSTALL_UV_BLOCKED") == "1":
        return RuntimeManagerState(
            uv_status="blocked",
            manual_guidance="uv setup is blocked. Install uv in user space, then rerun the installer.",
            error="UV_BLOCKED",
        )
    # Test-only override; production detection comes from the actual PATH.
    if os.environ.get("M32_INSTALL_ASSUME_UV") == "installed_user_local":
        return RuntimeManagerState(uv_status="installed_user_local")
    return detect_uv_status(allow_user_install=False)


def _detect_existing_state(surface: str, *, home: Path | str | None = None, local_app_data: Path | str | None = None) -> tuple[bool, bool]:
    if surface == "windows":
        base = Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        app = base / "M32Bridge" / "app"
        launcher = base / "M32Bridge" / "bin" / "m32-bridge.cmd"
    else:
        home_path = Path(home or os.environ.get("HOME") or Path.home())
        app = home_path / ".m32-bridge" / "app"
        launcher = home_path / ".local" / "bin" / "m32-bridge"
    return app.exists(), launcher.exists()


def _partial_failure_marker(surface: str, *, home: Path | str | None = None, local_app_data: Path | str | None = None) -> bool:
    if surface == "windows":
        base = Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "M32Bridge" / ".partial_failure").exists()
    home_path = Path(home or os.environ.get("HOME") or Path.home())
    return (home_path / ".m32-bridge" / ".partial_failure").exists()


def _apply_user_local_install(surface: str, result: dict[str, Any], *, uv_bin: str) -> None:
    _assert_user_local_result(surface, result)
    resolved_uv_bin = _resolve_uv_executable(surface, uv_bin)
    app_path = Path(result["app_path"])
    launcher_path = Path(result["launcher_path"])
    source_root = Path(str(result.get("_source_root") or ""))
    _assert_materialization_source(source_root)
    app_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".m32-bridge-candidate-", dir=app_path.parent))
    candidate_app = staging / "app"
    candidate_launcher = staging / launcher_path.name
    backup_app = staging / "previous-app"
    backup_launcher = staging / "previous-launcher"
    app_swapped = False
    launcher_swapped = False
    try:
        _materialize_app(candidate_app, source_root=source_root)
        (candidate_app / ".install-provenance-pending").write_text("pending\n", encoding="utf-8")
        _write_launcher(surface, candidate_launcher, final_app_path=app_path, final_launcher_path=launcher_path, uv_bin=resolved_uv_bin)
        candidate_result = {
            **result,
            "app_path": str(candidate_app),
            "launcher_path": str(candidate_launcher),
            "_diagnostic_log_dir_override": str(app_path.parent / "logs"),
        }
        readiness = (
            _synchronize_application_runtime(surface, candidate_result, uv_bin=resolved_uv_bin)
            if result.get("bootstrap_apply")
            else {
                "ready": True,
                "managed_python_version": result.get("runtime_info", {}).get("managed_python_version") or "3.13.x",
                "required_imports": "not_run_internal_call",
            }
        )
        if not readiness.get("ready"):
            raise InstallStepError(
                error_code="APPLICATION_RUNTIME_NOT_READY",
                failed_step="application_runtime_readiness",
                message=str(readiness.get("message") or "Required application imports did not pass."),
                recovery_action="Rerun the installer to repair the user-local application environment.",
            )
        if app_path.exists():
            os.replace(app_path, backup_app)
        os.replace(candidate_app, app_path)
        app_swapped = True
        if launcher_path.exists():
            os.replace(launcher_path, backup_launcher)
        os.replace(candidate_launcher, launcher_path)
        launcher_swapped = True
        if surface != "windows":
            launcher_path.chmod(0o755)
        result["_candidate_readiness"] = readiness
    except Exception:
        if launcher_swapped and launcher_path.exists():
            launcher_path.unlink(missing_ok=True)
        if backup_launcher.exists():
            os.replace(backup_launcher, launcher_path)
        if app_swapped and app_path.exists():
            shutil.rmtree(app_path)
        if backup_app.exists():
            os.replace(backup_app, app_path)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _write_launcher(
    surface: str,
    launcher_path: Path,
    *,
    final_app_path: Path,
    final_launcher_path: Path,
    uv_bin: str,
) -> None:
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    if surface == "windows":
        app_value = _cmd_assignment_value(str(final_app_path))
        uv_value = _cmd_assignment_value(uv_bin)
        launcher_path.write_text(
            "@echo off\r\n"
            f"set \"M32_BRIDGE_APP_DIR={app_value}\"\r\n"
            f"set \"UV_BIN={uv_value}\"\r\n"
            f"set \"M32_BRIDGE_LAUNCHER={_cmd_assignment_value(str(final_launcher_path))}\"\r\n"
            "set \"M32_BRIDGE_UV_BIN=%UV_BIN%\"\r\n"
            "set \"PYTHONPATH=%M32_BRIDGE_APP_DIR%\\src;%PYTHONPATH%\"\r\n"
            "set \"UV_MANAGED_PYTHON=1\"\r\n"
            "set \"M32_BRIDGE_INSTALLED_RUNTIME=1\"\r\n"
            "cd /d \"%M32_BRIDGE_APP_DIR%\"\r\n"
            "\"%UV_BIN%\" run --frozen --managed-python --python 3.13 --no-build --no-sync --project \"%M32_BRIDGE_APP_DIR%\" python -m m32_bridge.__main__ %*\r\n",
            encoding="utf-8",
        )
    else:
        launcher_path.write_text(
            "#!/bin/sh\n"
            f"APP_DIR={shlex.quote(str(final_app_path))}\n"
            f"UV_BIN={shlex.quote(uv_bin)}\n"
            f"M32_BRIDGE_LAUNCHER={shlex.quote(str(final_launcher_path))}\n"
            "M32_BRIDGE_UV_BIN=\"$UV_BIN\"\n"
            "cd \"$APP_DIR\"\n"
            "PYTHONPATH=\"$APP_DIR/src${PYTHONPATH:+:$PYTHONPATH}\"\n"
            "UV_MANAGED_PYTHON=1\n"
            "M32_BRIDGE_INSTALLED_RUNTIME=1\n"
            "export M32_BRIDGE_APP_DIR=\"$APP_DIR\" M32_BRIDGE_LAUNCHER M32_BRIDGE_UV_BIN PYTHONPATH UV_MANAGED_PYTHON M32_BRIDGE_INSTALLED_RUNTIME\n"
            "exec \"$UV_BIN\" run --frozen --managed-python --python 3.13 --no-build --no-sync --project \"$APP_DIR\" python -m m32_bridge.__main__ \"$@\"\n",
            encoding="utf-8",
        )
        launcher_path.chmod(0o755)


def handoff_to_installed_runtime(
    surface: str,
    result: dict[str, Any],
    *,
    exec_replace: Any = os.execve,
    runner: Any = subprocess.run,
) -> int:
    launcher = Path(str(result.get("launcher_path") or "")).expanduser()
    app_path = Path(str(result.get("app_path") or "")).expanduser()
    if not launcher.is_absolute() or not launcher.is_file():
        raise RuntimeError("Installed runtime launcher is unavailable for TTY handoff.")
    if not app_path.is_absolute() or not app_path.is_dir() or not (app_path / ".venv").is_dir():
        raise RuntimeError("Installed application runtime is unavailable for TTY handoff.")
    launcher = launcher.resolve()
    app_path = app_path.resolve()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "M32_BRIDGE_INSTALLED_RUNTIME": "1",
            "M32_BRIDGE_APP_DIR": str(app_path),
            "UV_MANAGED_PYTHON": "1",
        }
    )
    argv = [str(launcher), "run"]
    if surface == "windows":
        completed = runner(argv, check=False, env=environment)
        return_code = int(completed.returncode)
        if return_code != 0:
            raise RuntimeError(f"Installed runtime TTY handoff failed with exit code {return_code}.")
        return 0
    result_code = exec_replace(str(launcher), argv, environment)
    return int(result_code or 0)


def _cmd_assignment_value(value: str) -> str:
    if any(character in value for character in ('"', "\r", "\n")):
        raise ValueError("Windows launcher path contains an unsupported character")
    return value.replace("%", "%%")


def _materialize_app(app_path: Path, *, source_root: Path | None = None) -> None:
    source = source_root or _repo_root()
    _assert_materialization_source(source)
    app_path.mkdir(parents=True, exist_ok=True)
    for filename in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
        src = source / filename
        if src.is_file():
            shutil.copy2(src, app_path / filename)
    _copy_tree_filtered(source / "src", app_path / "src")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _assert_materialization_source(source: Path) -> None:
    required = [source / "pyproject.toml", source / "uv.lock", source / "src" / "m32_bridge"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise OSError(f"materialization source missing required files: {', '.join(missing)}")


def _copy_tree_filtered(source: Path, destination: Path) -> None:
    if not source.exists():
        raise OSError(f"required source tree missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if _should_skip_materialized_path(child):
            continue
        target = destination / child.name
        if child.is_dir():
            _copy_tree_filtered(child, target)
        elif child.is_file():
            shutil.copy2(child, target)


def _should_skip_materialized_path(path: Path) -> bool:
    name = path.name
    if name in {
        ".git",
        ".venv",
        ".pytest_cache",
        ".DS_Store",
        "__pycache__",
        "tests",
        ".env",
        ".env.local",
        "config.local.yaml",
        "config.yaml",
    }:
        return True
    if name.endswith((".pyc", ".pyo")):
        return True
    return False


def _dependency_target_root(surface: str, home: Path | str | None, local_app_data: Path | str | None) -> Path:
    if surface == "windows":
        return Path(local_app_data or os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return Path(home or os.environ.get("HOME") or Path.home())


def _uv_required_action(surface: str, target_root: Path) -> dict[str, Any]:
    if surface == "windows":
        command_preview = "Invoke-RestMethod downloads https://astral.sh/uv/install.ps1 to a temporary file; run only after exact INSTALL confirmation; then uv python install 3.13"
        target_paths = [str(target_root / "M32Bridge" / "runtime" / "uv")]
    else:
        command_preview = "curl downloads https://astral.sh/uv/install.sh to a temporary file (wget/manual fallback); run only after exact INSTALL confirmation; then uv python install 3.13"
        target_paths = [str(target_root / ".local" / "bin" / "uv")]
    return {
        "action_id": "INSTALL_UV_USER_LOCAL",
        "title": "Install uv in user space",
        "reason": "M32 Bridge uses uv-managed CPython 3.13 without changing system Python or installing default aliases.",
        "command_preview": command_preview,
        "requires_confirmation": True,
        "risk_level": "user_local",
        "target_paths": target_paths,
        "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
        "user_can_skip": False,
    }


def _assert_user_local_result(surface: str, result: dict[str, Any]) -> None:
    paths = [Path(result["app_path"]), Path(result["launcher_path"]), Path(result.get("install_root") or result["app_path"])]
    for action in result.get("required_actions") or []:
        for target in action.get("target_paths", []):
            paths.append(Path(target))
        preview = action.get("command_preview", "").lower()
        forbidden_preview = ["sudo", "runas", "start-process -verb runas", "rm -rf", "del /", "rmdir /s", "format "]
        if any(token in preview for token in forbidden_preview):
            raise ValueError("dependency action contains forbidden admin or destructive command")
    for path in paths:
        if _is_system_path(surface, path):
            raise ValueError(f"system path rejected for user-local installer boundary: {path}")


def _is_system_path(surface: str, path: Path) -> bool:
    text = str(path)
    lower = text.lower().replace("\\", "/")
    if surface == "windows":
        return lower.startswith("c:/windows") or lower.startswith("c:/program files")
    return text in {"/", "/usr", "/usr/local", "/opt", "/etc", "/bin", "/sbin", "/var"} or lower.startswith(
        ("/usr/", "/usr/local/", "/opt/", "/etc/", "/bin/", "/sbin/")
    )


def _message(result: dict[str, Any]) -> str:
    state = result["status"]
    if state == "fresh_install":
        return "fresh_install planned for user-local app and launcher paths."
    if state == "existing_install":
        return "existing_install detected; inspect user-local files before changing them."
    if state == "repair":
        return "repair planned; restore missing user-local launcher without deleting saved config."
    if state == "update":
        return "update planned; preserve saved config unless the user changes it later."
    if state == "already_current":
        return "already_current; run m32-bridge health in a new terminal if PATH changed."
    if state == "partial_failure":
        return "partial_failure detected; use recovery guidance before reporting success."
    if state == "failed":
        return "failed; no silent success was reported."
    if state == "UV_MISSING":
        return "UV_MISSING: uv is required before install can continue; confirm guided action explicitly."
    if state == "RUNTIME_SETUP_REQUIRED":
        return "RUNTIME_SETUP_REQUIRED: uv is missing; review required_actions before applying install."
    return "installer status is available."


def _recommendations(surface: str, result: dict[str, Any]) -> list[str]:
    common = [
        "Run m32-bridge health after install.",
        "Post-install verification commands: m32-bridge health, m32-bridge setup, m32-bridge get-info, m32-bridge detect-device, m32-bridge doctor-runtime.",
        "Run m32-bridge setup later for console endpoint setup.",
        "TTY installer output uses DXBMARK styled sections; JSON stays machine-readable.",
        "No /set, OSC writes, hardware verification, or production/live readiness is performed by install evidence.",
        "Manual-copy MCP guidance: use m32-bridge mcp-server as a local stdio command; no Claude, ChatGPT, Gemini, Antigravity, Codex, VS Code, or Cursor config is written automatically.",
        "Lifecycle guidance covers update, repair, and uninstall for user-local app and launcher paths; retain saved config by default.",
    ]
    if surface == "windows":
        common.append("Use PowerShell irm / Invoke-RestMethod guidance; CMD usage is through m32-bridge.cmd after install.")
    else:
        common.append("Download with curl when available, wget fallback, or manual download; inspect before running.")
    if result.get("uv_status") == "manual_action_required":
        common.append("uv requires user-local setup guidance; global py is not required and confirmation is required.")
    if result.get("status") == "partial_failure":
        common.append("Recovery: repair the user-local app and launcher, or remove incomplete user-local files.")
    return common


def _print_plain(surface: str, result: dict[str, Any], *, dry_run: bool, tty: bool = False, color: bool = False) -> None:
    if tty:
        from .tty_app import render_tty_installer

        print(render_tty_installer(surface, result, dry_run=dry_run, color=color))
        return
    print("M32 Bridge installer status")
    print(f"surface: {surface}")
    print(f"mode: {'dry-run' if dry_run else 'apply'}")
    print(f"status: {result['status']}")
    print(f"version: {result.get('application_version') or result.get('version') or 'unknown'}")
    print(f"install_source: {result.get('install_source', 'local_checkout')}")
    print(f"install_root: {result.get('install_root')}")
    print(f"app_path: {result['app_path']}")
    print(f"launcher_path: {result['launcher_path']}")
    print("user_local: true")
    print("admin_required=false")
    print("requires_admin=false")
    print("global_py_required=false")
    print("hardware_verified=false")
    print("production_live_ready=false")
    print("osc_writes_sent=0")
    if not result.get("ok") and result.get("error_code"):
        print(f"error_code: {result['error_code']}")
        print(f"failed_step: {result.get('failed_step') or (result.get('runtime_info') or {}).get('failed_step')}")
        print(f"dependency_package: {result.get('dependency_package') or 'unknown'}")
        print(f"target_platform: {result.get('target_platform') or result.get('platform')}")
        print(f"python_version: {result.get('python_version') or APPROVED_PYTHON_MINOR}")
        print(f"recovery_action: {result.get('recovery_action') or (result.get('runtime_info') or {}).get('recovery_action')}")
        print(f"diagnostic_log_path: {result.get('diagnostic_log_path') or 'not_available'}")
    lifecycle = result.get("lifecycle_guidance") or {}
    if lifecycle:
        print("lifecycle_guidance: update repair uninstall")
        print(f"config_path: {lifecycle.get('config_path')}")
        print("config_handling: retain saved config by default; remove only after explicit confirmation")
    print(f"message: {result.get('message')}")
    for recommendation in result.get("recommendations", []):
        print(f"- {recommendation}")


if __name__ == "__main__":
    raise SystemExit(main())
