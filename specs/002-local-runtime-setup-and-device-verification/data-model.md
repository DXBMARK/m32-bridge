# Data Model: Local Runtime Setup and Device Verification

## RuntimeConfig

Represents non-secret local bridge configuration.

**Fields**:

- `schema_version`: config schema version string.
- `host`: optional console hostname or IP address.
- `port`: integer port, defaulting to `10023` only when `host` is present.
- `label`: optional human label.
- `environment`: optional environment label such as `home`, `lab`, `venue`, or `dev`.
- `intended_target_type`: `emulator`, `hardware`, or `unknown`.
- `config_path`: resolved file path.
- `config_scope`: `user` or `project_dev_test`.
- `last_validated_at`: optional timestamp.
- `last_probe_summary`: optional `/info` probe summary.

**Validation Rules**:

- `host` is required for commands that probe a console.
- Missing host returns `NO_CONSOLE_HOST`; it must not trigger guessing or scanning.
- `port` must be a valid UDP port and must remain user-editable.
- Config must not contain secrets, access tokens, raw OSC paths, or host-app private configuration.
- Project-local config is valid only in explicit development or test context.

## ConfigResolution

Explains where the effective endpoint came from.

**Fields**:

- `cli_args_present`: boolean.
- `env_overrides_present`: boolean.
- `user_config_present`: boolean.
- `project_local_config_present`: boolean.
- `effective_host`: optional string.
- `effective_port`: optional integer.
- `source_by_field`: map of field name to `cli`, `env`, `user_config`, `project_local_dev_test`, or `default`.
- `error_code`: optional validation or missing-host code.

**Precedence**:

1. CLI arguments.
2. Environment variables.
3. Saved user config.
4. Project-local config only in development or test context.

## InfoProbeResult

Represents the bounded `/info` read-only connectivity probe.

**Fields**:

- `attempted_path`: always `/info` for setup and get-info probes.
- `configured_host`: optional string.
- `configured_port`: optional integer.
- `connected`: boolean.
- `response_address`: optional host/port response address.
- `latency_ms`: number or null.
- `status`: `CONNECTED`, `NOT_CONNECTED`, `NO_CONSOLE_HOST`, `INVALID_CONFIG`, or `UNEXPECTED_RESPONSE_ADDRESS`.
- `exception_type`: optional exception class name for failures.
- `osc_writes_sent`: always `0`.

## SetupResult

Represents setup command outcome.

**Fields**:

- `status`: `SAVED`, `NOT_SAVED`, `FAILED`, or `NO_CONSOLE_HOST`.
- `config_path`: target user-local or project-local path.
- `saved`: boolean.
- `config_resolution`: `ConfigResolution`.
- `info_probe`: `InfoProbeResult`.
- `classification`: optional `DeviceClassification`.
- `recommendations`: list of next manual actions.
- `osc_writes_sent`: always `0`.
- `hardware_verified`: always `false` unless later hardware acceptance evidence exists.

## DeviceIdentityReport

Represents endpoint identity and safety classification.

**Fields**:

- `classification`: `NOT_CONFIGURED`, `EMULATOR_CONNECTED`, `CONNECTED_UNVERIFIED`, `HARDWARE_CANDIDATE`, or `HARDWARE_VERIFIED`.
- `connected`: boolean.
- `configured_host`: optional string.
- `configured_port`: optional integer.
- `response_address`: optional value.
- `latency_ms`: number or null.
- `model_family`: optional string.
- `firmware_version`: optional string.
- `api_version`: optional string.
- `capability_map`: map of optional capability name to support status.
- `unsupported_or_timeout_paths`: list of optional OSC paths that failed or timed out.
- `usb_evidence`: optional `UsbEvidence`.
- `hardware_verified`: boolean, default `false`.
- `production_live_ready`: boolean, default `false`.
- `osc_writes_sent`: always `0` for detection.

**Rules**:

- `connected=true` does not imply `hardware_verified=true`.
- Emulator evidence never produces `HARDWARE_VERIFIED`.
- `HARDWARE_VERIFIED` requires later physical hardware acceptance evidence.
- Optional capability failures are limitations when `/info` succeeds, not connection loss.

## UsbEvidence

Represents best-effort physical USB evidence.

**Fields**:

- `usb_detected`: boolean or null when inspection is unavailable.
- `usb_device_name`: optional string.
- `vendor_id`: optional string.
- `product_id`: optional string.
- `usb_confidence`: `none`, `low`, `medium`, `high`, or `unavailable`.
- `inspection_status`: `checked`, `unavailable`, `blocked`, or `unsupported_os`.
- `limitations`: list of strings.
- `usb_control_supported`: always `false` by default.

**Rules**:

- USB absence or inspection failure does not fail setup.
- USB evidence alone cannot authorize control or hardware verification.

## InteractiveShellSession

Represents a local operator shell session.

**Fields**:

- `stdin_is_tty`: boolean.
- `started`: boolean.
- `structured_error`: optional runtime output when not started.
- `slash_command`: current slash command string.
- `mapped_cli_equivalent`: optional CLI equivalent.
- `result`: common runtime output envelope.
- `local_write_lock_state`: local-only lock state.

**Rules**:

- Shell starts only when no subcommand is provided and stdin is a TTY.
- Slash commands are shell-only and must be documented that way.
- No slash command may expose raw OSC, arbitrary OSC path, shell execution, firmware, shutdown, phantom power, sample-rate, or clock controls.

## UnlockDecision

Represents local unlock evaluation.

**Fields**:

- `requested_action`: `lock` or `unlock`.
- `allowed`: boolean.
- `denial_reason`: optional error code.
- `runtime_mode`: `OFFLINE`, `OBSERVE`, `SOUNDCHECK`, `LIVE`, or `EMERGENCY`.
- `connected`: boolean.
- `state_stale`: boolean.
- `reconciled`: boolean.
- `emergency_active`: boolean.
- `policy_allows_write_readiness`: boolean.
- `osc_writes_sent`: always `0`.

**Rules**:

- Unlock is denied when disconnected, stale, unreconciled, in EMERGENCY, or blocked by existing write governance.
- Unlock does not send OSC writes and does not modify executor, rollback, proposal, or policy behavior.

## OsRecommendation

Represents platform-specific setup guidance.

**Fields**:

- `os_family`: `macos`, `windows`, `linux`, `raspberry_pi_os`, or `unknown`.
- `recommended_launcher`: `m32-bridge`.
- `user_local_default`: boolean.
- `admin_required`: `no`, `optional`, or `out_of_scope`.
- `usb_detection`: `best_effort`.
- `future_packaging_notes`: list of future-only packaging paths.
- `warnings`: list of scope or safety notes.

## McpLaunchGuidance

Represents manual-copy local MCP host guidance.

**Fields**:

- `transport`: `stdio`.
- `command`: `m32-bridge`.
- `args`: normally `["mcp-server"]`.
- `manual_copy_required`: boolean.
- `embeds_host_port`: boolean, normally `false`.
- `advanced_env_override_example`: optional clearly labelled example.
- `stdout_protocol_clean`: boolean.
- `logs_to_stderr`: boolean.
- `opens_network_port`: boolean, always `false` for default local stdio.
