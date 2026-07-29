# Quickstart: Cross-Platform Installers and First-Run Setup

This guide describes future validation scenarios for the installer feature. It is not an implementation guide and does not create installer scripts, binary packages, services, or hardware-write tests.

## Scope Guard

- Do not run real hardware writes.
- Do not run external safe-write tests.
- Do not require administrator privileges by default.
- Do not modify Claude Desktop configuration automatically.
- Do not claim `hardware_verified=true` from emulator, Fake M32, or install-time evidence.
- Do not claim `production_live_ready=true`.

## Validate POSIX Installer Behavior

Target platforms:

- macOS
- Linux
- WSL
- Raspberry Pi OS

Expected default paths:

```text
App: ~/.m32-bridge/app
Launcher: ~/.local/bin/m32-bridge
```

Validation expectations:

- `install.sh` supports user-local install.
- No administrator privileges are required by default.
- The installer does not assume global `py`.
- The installer verifies `uv` or gives clear manual guidance.
- WSL is reported distinctly from native Linux.
- Raspberry Pi OS receives a distinct recommendation.
- Re-running the installer reports a clear idempotency state.

## Validate Windows Installer Behavior

Target platforms:

- Windows PowerShell
- Windows CMD launcher usage after install

Expected default paths:

```text
App: %LOCALAPPDATA%\M32Bridge\app
Launcher: %LOCALAPPDATA%\M32Bridge\bin\m32-bridge.cmd
```

Validation expectations:

- `install.ps1` supports user-local install.
- No administrator privileges are required by default.
- PowerShell execution-policy issues produce clear next steps.
- The CMD-compatible launcher can run `m32-bridge health`.
- The installer does not assume global `py`.

## Validate First-Run Setup

Interactive flow expectations:

1. Installer offers first-run setup when stdin is a TTY.
2. Setup shows detected OS and recommended mode.
3. Setup asks for host, port default `10023`, label/environment, and intended target type.
4. Setup probes `/info` only.
5. Setup sends no `/set` and no state-changing OSC writes.
6. Setup displays endpoint classification.
7. Setup saves config only after confirmation.

Non-interactive flow expectations:

- Installer/setup does not hang.
- Output is structured or clearly actionable.
- Guidance suggests explicit commands such as `m32-bridge setup`, `m32-bridge health`, and `m32-bridge doctor-runtime`.

## Validate Post-Install Commands

After a future implementation, validation should include:

```text
m32-bridge health
m32-bridge setup
m32-bridge get-info
m32-bridge detect-device
m32-bridge doctor-runtime
```

Expected results:

- `health` works without console connectivity.
- `setup`, `get-info`, `detect-device`, and `doctor-runtime` report `osc_writes_sent=0`.
- Missing host returns setup guidance instead of guessing or scanning.
- Emulator classification never sets `hardware_verified=true`.

## Validate MCP Guidance

Default snippet expectation:

```json
{
  "command": "m32-bridge",
  "args": ["mcp-server"]
}
```

Expected behavior:

- Manual-copy only.
- No automatic Claude config modification.
- No host or port embedded by default.
- Saved user config is the default source for endpoint settings.
- Advanced/manual host/port overrides are labeled as such.

## Validate Install Command UX

Safer recommended path:

1. Download script.
2. Inspect script.
3. Run script locally.

Future convenience examples may be shown:

```text
curl -fsSL <url>/scripts/install.sh | sh
curl -LsSf <url>/install.sh | sh
powershell -ExecutionPolicy Bypass -c "irm <url>/install.ps1 | iex"
```

Expected documentation behavior:

- Safer path is clearly recommended.
- Convenience path is clearly labeled.
- Neither path implies official binary packaging exists.

## US1 MVP Validation Results

Recorded for T029 on 2026-07-28. Scope: installer script MVP only; no first-run wizard implementation, no external emulator, no hardware tests, no binary packaging, no WebUI, no database, no service, no remote MCP, and no automatic host configuration writes.

Commands run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/cross_platform/test_posix_installer_dry_run.py tests/unit/test_posix_installer_runtime_manager.py tests/unit/test_posix_installer_idempotency.py tests/cross_platform/test_posix_launcher_contract.py tests/cross_platform/test_windows_installer_dry_run.py tests/cross_platform/test_windows_cmd_launcher_contract.py tests/unit/test_windows_installer_runtime_manager.py tests/unit/test_windows_installer_idempotency.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_output_schema.py tests/unit/test_installer_contract_docs.py tests/unit/test_installer_mcp_guidance_contract.py tests/unit/test_installer_feature_scope_guard.py tests/unit/test_installer_module_boundaries.py -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Focused US1 installer tests passed: 24 passed.
- Installer contract and scope regression passed: 21 passed.
- `scripts/install.sh --dry-run --json` returned status-only structured output with `user_local=true`, `admin_required=false`, `hardware_verified=false`, `production_live_ready=false`, and `osc_writes_sent=0`.
- POSIX installer surface supports curl-first guidance, wget fallback, and manual download fallback.
- Windows installer surface uses PowerShell `irm` / `Invoke-RestMethod` guidance as the official download path; `curl.exe` is not the official path.
- DXBMARK style reference was added at `references/dxbmark-interactive-terminal-cli-style.md`; full wizard implementation remains deferred.

## Validate Lifecycle Guidance

## US2 First-Run Setup Validation Results

Recorded for T040 on 2026-07-28. Scope: first-run setup wizard only; no T041 post-install verification work, no external emulator, no real hardware tests, no `/set`, no automatic IDE/MCP client config writes, and no production/live readiness or hardware verification claims.

Commands run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit tests/cross_platform tests/integration_fake_m32 -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Initial sandboxed pytest run reached product tests but local UDP binding was blocked for FakeM32 with `PermissionError: [Errno 1] Operation not permitted`.
- Rerunning the same pytest command with local UDP permission passed: 301 passed.
- First-run setup renders DXBMARK TTY brand tokens, `/help`, `/contact`, green/grey client status, and plain/JSON fallback behavior.
- Non-TTY setup returns structured output and does not guess host addresses or scan.
- Setup probes `/info` only, keeps `osc_writes_sent=0`, and never sends `/set`.
- Config save remains confirmation-gated.
- Emulator and candidate classifications keep `hardware_verified=false` and `production_live_ready=false`.

## US3 Post-Install Verification Validation Results

Recorded for T050 on 2026-07-28. Scope: post-install verification commands only; no T051 MCP guidance work, no external emulator, no hardware tests, no `/set`, no OSC writes beyond read-only `/info` where explicitly requested, and no automatic IDE/MCP host configuration writes.

Commands run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_verification_guidance.py tests/e2e_mcp/test_installed_launcher_health.py tests/integration_fake_m32/test_installer_verification_no_write.py tests/unit/test_installer_verification_missing_host.py tests/unit/test_installer_verification_emulator_honesty.py tests/unit/test_posix_installer_runtime_manager.py tests/unit/test_windows_installer_runtime_manager.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_output_schema.py tests/unit/test_installer_feature_scope_guard.py tests/unit/test_installer_module_boundaries.py tests/unit/test_installer_contract_docs.py tests/unit/test_installer_mcp_guidance_contract.py tests/unit/test_installer_first_run_tty.py tests/unit/test_installer_first_run_non_tty.py tests/unit/test_installer_first_run_classification.py tests/unit/test_installer_first_run_save_confirmation.py tests/unit/test_runtime_output_schema.py tests/unit/test_runtime_config_missing_host.py tests/e2e_mcp/test_stdio_clean_output.py tests/e2e_mcp/test_mcp_stdio_no_network_port.py -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Focused US3 verification tests passed: 23 passed.
- Installer, first-run, runtime config/schema, and MCP stdio safety regression passed: 53 passed.
- Post-install guidance includes `m32-bridge health`, `m32-bridge setup`, `m32-bridge get-info`, `m32-bridge detect-device`, and `m32-bridge doctor-runtime`.
- `install-status` and `verify-install` return structured JSON-compatible metadata without console probing by default.
- `get-info`, `setup`, `detect-device`, and `doctor-runtime` verification paths preserve `/info`-only read behavior, `osc_writes_sent=0`, `hardware_verified=false`, and `production_live_ready=false`.
- Missing host returns structured setup guidance without guessing or scanning.

## US4 MCP Guidance Validation Results

Recorded for T058 on 2026-07-28. Scope: manual-copy MCP/IDE guidance only; no T059 lifecycle work, no external emulator, no hardware tests, no `/set`, no OSC writes, no IDE app opening, and no automatic Claude/Gemini/Antigravity/ChatGPT/Codex/VS Code/Cursor config writes.

Commands run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_mcp_guidance.py tests/unit/test_installer_mcp_advanced_overrides.py tests/unit/test_installer_mcp_no_auto_config_write.py tests/unit/test_installer_mcp_forbidden_surfaces.py tests/unit/test_installer_mcp_guidance_contract.py tests/unit/test_mcp_launch_guidance.py tests/e2e_mcp/test_mcp_stdio_no_network_port.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_output_schema.py tests/unit/test_installer_feature_scope_guard.py tests/unit/test_installer_module_boundaries.py tests/unit/test_installer_contract_docs.py tests/unit/test_installer_first_run_tty.py tests/unit/test_installer_first_run_non_tty.py tests/unit/test_installer_first_run_classification.py tests/unit/test_installer_first_run_save_confirmation.py tests/unit/test_runtime_output_schema.py tests/unit/test_runtime_config_missing_host.py tests/e2e_mcp/test_stdio_clean_output.py tests/e2e_mcp/test_mcp_stdio_no_network_port.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit tests/cross_platform tests/e2e_mcp -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/e2e_mcp -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit tests/cross_platform tests/e2e_mcp -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Focused US4 MCP guidance tests passed: 18 passed.
- Non-UDP installer, first-run, runtime config/schema, and MCP stdio safety regression passed: 49 passed.
- MCP guidance uses `m32-bridge` with `args=["mcp-server"]` over local stdio.
- Default snippets are manual-copy only and do not embed console host or port.
- Advanced host/port examples are clearly labelled as manual-only overrides.
- Detected MCP clients are listed best-effort with structured active/inactive status.
- Guidance reports no client config writes, no app opens, no network port, no remote MCP surface, no raw OSC surface, `osc_writes_sent=0`, `hardware_verified=false`, and `production_live_ready=false`.
- Broad regression was also attempted. The managed sandbox run hit FakeM32 UDP bind failures with `PermissionError: [Errno 1] Operation not permitted`; rerunning `tests/e2e_mcp` with local UDP permission passed: 66 passed.
- The requested broad regression with local UDP permission reached 344 passed and 1 failed. The remaining failure is `tests/unit/test_cli_setup.py::test_setup_json_contract_for_invalid_host_returns_invalid_host`, where `setup --host ""` currently returns `NO_CONSOLE_HOST` through the first-run path instead of `INVALID_HOST`. This is outside US4 MCP guidance implementation.

Expected lifecycle cases:

- Fresh install
- Existing install
- Repair
- Update
- Already current
- Partial failure recovery
- Uninstall

Expected documentation:

- App path is identified.
- Launcher path is identified.
- Config retention/removal choice is documented.
- PATH restart/manual action is documented when needed.

## US5 Lifecycle and Packaging Validation Results

Recorded for T068 on 2026-07-28. Scope: lifecycle guidance, partial failure recovery, installer command UX documentation, and future-only packaging documentation. No T069 work, no external emulator, no hardware tests, no `/set`, no OSC writes, no IDE app opening, no MCP client config writes, no binary installer artifacts, no WebUI, no DB, no service/daemon, no remote MCP, and no ChatGPT tunnel.

Commands to run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_lifecycle_guidance.py tests/unit/test_installer_partial_failure_recovery.py tests/unit/test_installer_future_packaging_docs.py tests/unit/test_installer_command_ux_docs.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit tests/cross_platform tests/e2e_mcp tests/integration_fake_m32 -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Focused US5 lifecycle, partial failure recovery, future-only packaging, and command UX tests passed: 10 passed.
- Targeted US5 plus installer idempotency/runtime/contract regression passed: 44 passed.
- Broad regression in the managed sandbox hit local UDP bind failures from FakeM32. Rerunning the same command with local UDP permission passed: 410 passed.

Expected lifecycle guidance:

- Update: rerun the inspected user-local installer source, update app files, preserve saved runtime config, and open a new terminal if PATH visibility changed.
- Repair: restore missing user-local app or launcher files, do not delete saved runtime config, and run `m32-bridge health`.
- Uninstall: identify the user-local app path and launcher path, retain saved config and audit files by default, and remove config/audit files only after explicit confirmation.
- Partial failure: report `ok=false`, avoid any success claim, recommend repair first, and provide manual recovery steps without destructive cleanup.

Installer command UX and release guidance:

- Recommended workflow: download-inspect-run.
- Convenience examples remain secondary:
  - POSIX: `curl -LsSf <url>/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy Bypass -c "irm <url>/install.ps1 | iex"`
- GitHub public repo after push: `https://github.com/DXBMARK/m32-bridge`.
- Stable install command stays based on `scripts/install.sh` and `scripts/install.ps1`.
- Version/tag guidance: use a released version/tag only after the public repository has the installer changes pushed.
- Raw live install test is deferred until after commit/push.

## Future-Only Packaging Scope

These items must remain documented as future-only unless separately approved:

- macOS `.app`, `.pkg`, `.dmg`
- Windows `.exe`, `.msi`
- Linux `.deb`, `.rpm`, AppImage
- Raspberry Pi service/image
- Claude Desktop `.mcpb` or `.dxt`
- USB portable kit
- Code signing, checksums, GitHub Releases

## Final Gate Validation Results

Recorded for T073 and T074 on 2026-07-28. Scope: final safety, cross-platform, schema, documentation drift, MCP stdio, FakeM32 local integration, and hardware-acceptance data-only tests. No GitHub raw live install test, no commit, no push, no external emulator, no hardware write test, no `/set`, no OSC writes from installer/setup/guidance, no IDE opening, no MCP client config write, no binary installer generation, no WebUI, no DB, no service/daemon, no remote MCP, and no tunnel.

Commands run:

```text
env UV_CACHE_DIR=/private/tmp/uv-cache uv run python -m compileall src tests
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_installer_output_schema.py tests/unit/test_installer_feature_scope_guard.py tests/cross_platform/test_installer_cross_platform_gate.py tests/unit/test_installer_docs_drift.py tests/unit/test_installer_contract_docs.py tests/unit/test_installer_command_ux_docs.py tests/unit/test_installer_future_packaging_docs.py tests/unit/test_installer_lifecycle_guidance.py tests/unit/test_installer_partial_failure_recovery.py -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit tests/cross_platform tests/e2e_mcp tests/integration_fake_m32 -q -p no:cacheprovider
env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/hardware_acceptance -q -p no:cacheprovider
```

Results:

- Compileall passed for `src` and `tests`.
- Targeted final gate tests passed: 41 passed.
- Full local regression hit local UDP bind failures in the managed sandbox. Rerunning the same command with local UDP permission passed: 423 passed.
- Hardware-acceptance data-only tests passed: 15 passed. These tests do not prove real hardware readiness and do not set `hardware_verified=true`.
- Final safety inventory confirmed no binary installers, signed release availability claim, WebUI, DB, service/daemon, remote/cloud MCP, tunnel, Claude auto-config write, production/live readiness claim, or emulator/FakeM32 hardware verification claim was added.
- GitHub raw live install test remains deferred until after commit/push.
