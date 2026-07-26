# Quickstart: Planning Validation Scenarios

This quickstart describes the expected future behavior for the feature. It is not an implementation guide and does not start installer, setup-wizard implementation, remote MCP, or hardware-write work.

## 1. Safe Setup With Explicit Endpoint

Example future command:

```text
m32-bridge setup --host <console-host> --port 10023 --target-type emulator --json
```

Expected outcome:

- Probes `/info` only.
- Reports `configured_host`, `configured_port`, `attempted_path="/info"`, `latency_ms`, and response address when available.
- Reports `osc_writes_sent=0`.
- Saves user-local config only after operator confirmation.
- Keeps `hardware_verified=false` and `production_live_ready=false` for emulator evidence.

## 2. Missing Host

Example future command:

```text
m32-bridge doctor-runtime --json
```

Expected outcome when no host exists in CLI, environment, user config, or allowed development/test config:

- Returns `NO_CONSOLE_HOST`.
- Does not guess, scan, or infer a host.
- Suggests `m32-bridge setup`.
- Reports `osc_writes_sent=0` where applicable.

## 3. Read-Only Info Probe

Example future command:

```text
m32-bridge get-info --json
```

Expected outcome:

- Sends a read-only `/info` probe.
- Returns structured success or failure.
- Includes `configured_host`, `configured_port`, `attempted_path="/info"`, `latency_ms`, and `exception_type` on failure.
- Reports `osc_writes_sent=0`.

## 4. Device Detection

Example future command:

```text
m32-bridge detect-device --json
```

Expected emulator outcome:

- `classification="EMULATOR_CONNECTED"`.
- `connected=true`.
- `hardware_verified=false`.
- `production_live_ready=false`.
- Optional capability failures appear as limitations, not as connection loss when `/info` succeeds.

Expected hardware-candidate outcome:

- `classification="HARDWARE_CANDIDATE"` or `CONNECTED_UNVERIFIED` unless later physical hardware acceptance evidence exists.
- `hardware_verified=false` by default.

## 5. Config Validation and Precedence

Example future commands:

```text
m32-bridge config show --json
m32-bridge config validate --json
m32-bridge config set --host <console-host> --port <port> --json
```

Expected outcome:

- Shows non-secret config location and effective values.
- Validates host and port.
- Resolves `CLI > environment > user config > project-local dev/test`.
- Keeps project-local config development/test-only.

## 6. Non-Interactive Shell Guard

Example future non-interactive launch:

```text
printf "" | m32-bridge
```

Expected outcome:

- Does not open the interactive shell.
- Does not wait for input.
- Returns structured help/error such as `NON_INTERACTIVE_SHELL_REQUIRED`.
- Suggests explicit commands: `m32-bridge setup`, `m32-bridge health`, and `m32-bridge mcp-server`.

## 7. Interactive Shell

Example future shell launch:

```text
m32-bridge
```

Inside the shell only:

```text
/help
/runsetup
/getinfo
/config
/config set host <host>
/config set port <port>
/test
/doctor
/detect
/mcp
/claude
/mode
/lock
/unlock
/exit
```

Expected outcome:

- Help clearly states slash commands work only inside the `m32-bridge` shell.
- `/runsetup`, `/getinfo`, `/config`, `/test`, `/doctor`, and `/detect` send zero OSC writes.
- `/lock` and `/unlock` affect local write-lock state only and send zero OSC writes.
- No slash command exposes raw OSC, arbitrary paths, shell execution, firmware, shutdown, phantom, sample-rate, clock, or approval-token bypasses.

## 8. Unlock Denial

Example future shell command:

```text
/unlock
```

Expected outcome when disconnected, stale, unreconciled, or in EMERGENCY:

- Unlock is denied.
- Denial reason is explicit.
- Existing reconciliation, runtime mode, EMERGENCY, and write-governance rules remain authoritative.
- `osc_writes_sent=0`.

## 9. Local Stdio MCP

Normal future MCP snippet:

```json
{
  "command": "m32-bridge",
  "args": ["mcp-server"]
}
```

Expected outcome:

- Local MCP host launches the bridge as a subprocess.
- MCP protocol uses stdin/stdout.
- Logs go to stderr.
- No local MCP network port is opened by default.
- Normal snippets do not embed host or port; bridge reads saved user config.
- Any environment host/port override is clearly labelled advanced/manual.

## 10. OS Recommendations

Future recommendation output should cover:

- macOS: user-local launcher or future app/launcher, Claude Desktop stdio, best-effort USB detection, no administrator privileges by default.
- Windows: user install or future executable launcher, best-effort USB detection, administrator privileges only for optional service/system-wide cases.
- Linux: user-local install/package, best-effort USB/audio subsystem detection, optional user service guidance, no cloud exposure by default.
- Raspberry Pi OS: future dedicated bridge mode, optional service operation, fixed FOH/local bridge suitability, no cloud exposure by default.

## 11. USB Best-Effort Detection

Expected outcome:

- Reports `usb_detected`, `usb_device_name`, vendor/product when available, `usb_confidence`, and inspection limitations.
- Reports `usb_control_supported=false` by default.
- Does not fail setup if USB inspection is unavailable, blocked, or inconclusive.
- Does not authorize control or hardware verification from USB evidence alone.

## 12. Future Packaging Notes

Documentation may distinguish:

- Current development install.
- Current/future user-local launcher.
- Future OS packages.
- Future Raspberry Pi service/image.
- Future MCP extension bundle.
- Future portable kit.

No packaging or installer implementation is part of this feature planning phase.
