# Data Model: Cross-Platform Installers and First-Run Setup

## InstallationTarget

Represents the OS and shell environment where installation runs.

**Fields**:

- `os_family`: `macos`, `linux`, `wsl`, `windows`, or `raspberry_pi_os`
- `shell_family`: `posix`, `powershell`, or `cmd_launcher`
- `architecture`: detected CPU architecture when available
- `is_interactive`: whether stdin supports prompting
- `supports_user_local_install`: boolean
- `recommendation`: user-facing OS-specific guidance

**Validation Rules**:

- WSL must be classified distinctly from native Linux.
- Raspberry Pi OS must be classified distinctly from generic Linux.
- Unsupported OS cases must return clear guidance rather than silent partial success.

## InstallLocation

Represents app and launcher paths for a user-local install.

**Fields**:

- `app_path`: user-local application directory
- `launcher_path`: stable launcher path
- `path_visibility`: visible now, requires shell restart, or needs manual PATH action
- `requires_admin`: defaults to `false`

**Defaults**:

- POSIX app path: `~/.m32-bridge/app`
- POSIX launcher path: `~/.local/bin/m32-bridge`
- Windows app path: `%LOCALAPPDATA%\M32Bridge\app`
- Windows launcher path: `%LOCALAPPDATA%\M32Bridge\bin\m32-bridge.cmd`
- Raspberry Pi OS uses POSIX user-local defaults.

## RuntimeManagerState

Represents availability of the managed runtime.

**Fields**:

- `uv_status`: `present`, `installed_user_local`, `blocked`, or `manual_action_required`
- `global_py_required`: always `false`
- `manual_guidance`: next steps when automatic user-local runtime setup is blocked
- `error`: structured failure details when applicable

**Validation Rules**:

- Global `py` must never be required.
- Blocked runtime installation must not be reported as success.

## InstallationState

Represents installer lifecycle status.

**Fields**:

- `status`: `fresh_install`, `existing_install`, `repair`, `update`, `already_current`, `partial_failure`, or `failed`
- `previous_version`: optional previous installed version
- `target_version`: desired version
- `actions_planned`: user-facing list of actions
- `actions_completed`: user-facing list of completed actions
- `rollback_or_recovery`: recovery guidance for partial failures
- `osc_writes_sent`: always `0`
- `hardware_verified`: always `false` for installer evidence
- `production_live_ready`: always `false`

**State Transitions**:

- `fresh_install` -> `first_run_setup_offered`
- `existing_install` -> `already_current`, `repair`, or `update`
- `partial_failure` -> `repair` or `failed`
- Any failure -> clear manual recovery guidance

## StableLauncher

Represents the installed `m32-bridge` launcher.

**Fields**:

- `command`: `m32-bridge`
- `launcher_path`: path from `InstallLocation`
- `shells_supported`: POSIX shell, PowerShell, and CMD where applicable
- `health_command`: `m32-bridge health`
- `mcp_command`: `m32-bridge mcp-server`

**Validation Rules**:

- Launcher must not depend on global `py`.
- Windows install must include CMD-compatible launcher behavior.

## FirstRunSetupSession

Represents first-run setup after installation.

**Fields**:

- `detected_os`: from `InstallationTarget`
- `recommended_mode`: OS-aware recommendation
- `host`: user-provided console host
- `port`: user-provided port, default `10023`
- `label`: user-provided label or environment name
- `intended_target_type`: user-provided target type
- `attempted_path`: `/info`
- `classification`: endpoint classification
- `save_confirmed`: boolean
- `non_interactive`: boolean
- `osc_writes_sent`: always `0`
- `hardware_verified`: `false` unless later physical hardware evidence exists

**Validation Rules**:

- Setup must not scan or guess a missing host.
- Setup must not send `/set` or state-changing OSC packets.
- Configuration is saved only after confirmation.
- Non-TTY setup must not hang.

## VerificationCommand

Represents the post-install command checklist.

**Fields**:

- `command`: one of `m32-bridge health`, `m32-bridge setup`, `m32-bridge get-info`, `m32-bridge detect-device`, `m32-bridge doctor-runtime`
- `requires_console_config`: boolean
- `expected_write_count`: always `0`
- `success_output`: expected success summary
- `failure_output`: expected structured failure guidance

## MCPGuidanceSnippet

Represents manual-copy MCP host guidance.

**Fields**:

- `command`: `m32-bridge`
- `args`: includes `mcp-server`
- `manual_copy_only`: `true`
- `embeds_host_port_by_default`: `false`
- `advanced_override_examples`: optional host/port examples clearly labeled as advanced/manual

**Validation Rules**:

- Guidance must not automatically modify Claude Desktop config.
- Default snippets must not embed host/port.

## LifecycleAction

Represents update, repair, and uninstall guidance.

**Fields**:

- `action`: `update`, `repair`, or `uninstall`
- `app_path`: from `InstallLocation`
- `launcher_path`: from `InstallLocation`
- `config_handling`: retain, remove, or ask
- `requires_admin`: defaults to `false`
- `result_status`: clear success or failure state

## FuturePackagingItem

Represents explicitly deferred packaging scope.

**Fields**:

- `kind`: `.exe`, `.msi`, `.app`, `.pkg`, `.dmg`, `.deb`, `.rpm`, `AppImage`, Raspberry Pi service/image, Claude `.mcpb`/`.dxt`, USB portable kit, signing/checksums, or GitHub Releases
- `status`: always `future_only` for this feature
- `implemented_now`: always `false`

**Validation Rules**:

- Future packaging items must not be described as current availability.
