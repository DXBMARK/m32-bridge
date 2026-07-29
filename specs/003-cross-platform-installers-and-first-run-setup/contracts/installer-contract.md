# Installer Contract: Cross-Platform Installers and First-Run Setup

This planning contract defines expected user-facing installer behavior. It does not implement installer scripts.

## Installer Entry Points

| Platform | Entry Point | Default Scope | Admin Required By Default |
| --- | --- | --- | --- |
| macOS | `install.sh` | user-local | no |
| Linux | `install.sh` | user-local | no |
| WSL | `install.sh` | user-local | no |
| Raspberry Pi OS | `install.sh` | user-local | no |
| Windows PowerShell | `install.ps1` | user-local | no |
| Windows CMD | `m32-bridge.cmd` launcher after install | user-local | no |

## Documented Command UX

The safer recommended path is:

1. Download the installer script.
2. Inspect it.
3. Run it locally.

Future convenience examples may be documented as convenience paths:

```text
curl -LsSf <url>/install.sh | sh
powershell -ExecutionPolicy Bypass -c "irm <url>/install.ps1 | iex"
```

Convenience examples must not be presented as safer than download-inspect-run.

## Default Install Locations

| Platform | App Path | Launcher Path |
| --- | --- | --- |
| macOS/Linux/WSL/Raspberry Pi OS | `~/.m32-bridge/app` | `~/.local/bin/m32-bridge` |
| Windows | `%LOCALAPPDATA%\M32Bridge\app` | `%LOCALAPPDATA%\M32Bridge\bin\m32-bridge.cmd` |

The default installer must not write to system-wide paths.

## Runtime Manager Behavior

The installer must:

- not rely on global Python or global `py`;
- verify whether `uv` is available;
- install or guide installation of `uv` in user space when allowed;
- return clear manual guidance if `uv` installation is blocked;
- avoid silent partial success.

## Idempotency States

Installers must distinguish:

- `fresh_install`
- `existing_install`
- `repair`
- `update`
- `already_current`
- `partial_failure`
- `failed`

Each state must include user-facing status and next steps.

## First-Run Setup Contract

After install, interactive terminals should offer setup. The setup flow must:

- show detected OS;
- show recommended mode;
- ask for host;
- ask for port with default `10023`;
- ask for label/environment;
- ask for intended target type;
- probe `/info` only;
- send no `/set` or state-changing OSC packets;
- display endpoint classification;
- save config only after confirmation;
- support non-interactive structured mode;
- never hang in non-TTY environments.

## Verification Commands

Post-install guidance must include:

```text
m32-bridge health
m32-bridge setup
m32-bridge get-info
m32-bridge detect-device
m32-bridge doctor-runtime
```

All install/setup/detect verification paths must report or prove `osc_writes_sent=0`.

## Safety Requirements

The installer contract forbids:

- `/set` or state-changing OSC writes during install/setup/detect;
- real hardware writes;
- emulator-based hardware verification;
- `production_live_ready=true` claims;
- admin OS privileges by default;
- automatic Claude config edits;
- shell execution exposed through MCP tools.

## Lifecycle Guidance Contract

Update, repair, and uninstall guidance must identify:

- app path;
- launcher path;
- configuration retention/removal options;
- whether a new terminal is required for PATH changes;
- manual recovery steps for partial failure.
