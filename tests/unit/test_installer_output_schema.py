from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "003-cross-platform-installers-and-first-run-setup"
    / "contracts"
    / "installer-output.schema.json"
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _minimal_payload() -> dict:
    return {
        "ok": True,
        "status": "fresh_install",
        "platform": "macos",
        "app_path": "/Users/operator/.m32-bridge/app",
        "launcher_path": "/Users/operator/.local/bin/m32-bridge",
        "requires_admin": False,
        "global_py_required": False,
        "uv_status": "present",
        "osc_writes_sent": 0,
        "hardware_verified": False,
        "production_live_ready": False,
        "recommendations": ["Run m32-bridge health"],
    }


def test_installer_output_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(_schema())


def test_minimal_installer_output_matches_schema():
    Draft202012Validator(_schema()).validate(_minimal_payload())


def test_optional_installer_metadata_fields_match_schema():
    payload = {
        **_minimal_payload(),
        "version": "0.1.0",
        "install_source": "local_checkout",
        "path_updated": True,
        "shell_profile": "/Users/operator/.zshrc",
        "detected_shell": "zsh",
        "wsl_distribution": None,
        "architecture": "arm64",
        "uv_required": True,
        "uv_detected": False,
        "python_required": True,
        "global_python_required": False,
        "python_managed_by_uv": True,
        "installer_can_continue": False,
        "confirmation_required": True,
        "required_actions": [
            {
                "action_id": "INSTALL_UV_USER_LOCAL",
                "title": "Install uv in user space",
                "reason": "M32 Bridge uses uv to manage Python without global py.",
                "command_preview": "curl -LsSf https://astral.sh/uv/install.sh",
                "requires_confirmation": True,
                "risk_level": "user_local",
                "target_paths": ["/Users/operator/.local/bin/uv"],
                "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
                "user_can_skip": False,
            }
        ],
        "first_run_setup": {
            "offered": True,
            "interactive": True,
            "attempted_path": "/info",
            "classification": "NOT_CONFIGURED",
            "osc_writes_sent": 0,
            "hardware_verified": False,
        },
    }

    Draft202012Validator(_schema()).validate(payload)


def test_installer_output_rejects_extra_properties():
    payload = {**_minimal_payload(), "admin_token": "not allowed"}
    errors = list(Draft202012Validator(_schema()).iter_errors(payload))

    assert errors
    assert any("Additional properties" in error.message for error in errors)


def test_installer_output_requires_safety_constants():
    payload = {
        **_minimal_payload(),
        "requires_admin": True,
        "global_py_required": True,
        "osc_writes_sent": 1,
        "hardware_verified": True,
        "production_live_ready": True,
    }
    errors = list(Draft202012Validator(_schema()).iter_errors(payload))

    assert len(errors) >= 5


def test_envelope_builder_outputs_schema_valid_safe_payload():
    from m32_bridge.installer.output import build_installer_output

    payload = build_installer_output(
        status="fresh_install",
        platform="macos",
        app_path="/Users/operator/.m32-bridge/app",
        launcher_path="/Users/operator/.local/bin/m32-bridge",
        uv_status="present",
        recommendations=["Run m32-bridge health"],
    )

    Draft202012Validator(_schema()).validate(payload)
    assert payload["osc_writes_sent"] == 0
    assert payload["hardware_verified"] is False
    assert payload["production_live_ready"] is False


def test_installer_output_required_actions_are_structured():
    from m32_bridge.installer.output import build_installer_output

    payload = build_installer_output(
        ok=False,
        status="UV_MISSING",
        platform="macos",
        app_path="/Users/operator/.m32-bridge/app",
        launcher_path="/Users/operator/.local/bin/m32-bridge",
        uv_status="manual_action_required",
        uv_required=True,
        uv_detected=False,
        python_required=True,
        global_python_required=False,
        python_managed_by_uv=True,
        installer_can_continue=False,
        confirmation_required=True,
        required_actions=[
            {
                "action_id": "INSTALL_UV_USER_LOCAL",
                "title": "Install uv in user space",
                "reason": "uv is required before M32 Bridge can be installed.",
                "command_preview": "curl -LsSf https://astral.sh/uv/install.sh",
                "requires_confirmation": True,
                "risk_level": "user_local",
                "target_paths": ["/Users/operator/.local/bin/uv"],
                "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
                "user_can_skip": False,
            }
        ],
    )

    Draft202012Validator(_schema()).validate(payload)
    assert payload["ok"] is False
    assert payload["required_actions"][0]["requires_confirmation"] is True


def test_representative_installer_outputs_match_schema(tmp_path):
    from m32_bridge.installer.runtime_manager import RuntimeManagerState
    from m32_bridge.installer.script_runtime import build_install_result, perform_apply_install

    schema = Draft202012Validator(_schema())
    posix = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=tmp_path / "posix",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    windows = build_install_result(
        surface="windows",
        platform="windows_powershell",
        dry_run=True,
        local_app_data=tmp_path / "LocalAppData",
        uv_state=RuntimeManagerState(uv_status="present"),
    )
    setup_required = build_install_result(
        surface="posix",
        platform="macos",
        dry_run=True,
        home=tmp_path / "setup-required",
        uv_state=RuntimeManagerState(uv_status="manual_action_required"),
    )
    failed = perform_apply_install(
        "posix",
        {
            **posix,
            "app_path": "/usr/local/m32-bridge/app",
            "launcher_path": str(tmp_path / "bin" / "m32-bridge"),
            "install_root": "/usr/local/m32-bridge",
        },
    )
    marker_root = tmp_path / "partial"
    (marker_root / ".m32-bridge").mkdir(parents=True)
    (marker_root / ".m32-bridge" / ".partial_failure").write_text("failed", encoding="utf-8")
    partial = build_install_result(
        surface="posix",
        platform="linux",
        dry_run=True,
        home=marker_root,
        uv_state=RuntimeManagerState(uv_status="present"),
    )

    for payload in (posix, windows, setup_required, failed, partial):
        schema.validate(payload)
        assert payload["osc_writes_sent"] == 0
        assert payload["hardware_verified"] is False
        assert payload["production_live_ready"] is False
