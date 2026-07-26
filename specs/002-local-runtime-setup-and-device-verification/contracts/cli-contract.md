# CLI and Runtime Contract

This contract defines the expected public runtime shape for the local setup and device-verification feature. It is a planning artifact only and does not implement commands.

## Launcher

The stable end-user command is:

```text
m32-bridge
```

Normal documentation and MCP snippets must not require a global `py` command. Development-only notes may describe development runners separately.

## Normal CLI Commands

| Command | Purpose | OSC Writes |
| --- | --- | --- |
| `m32-bridge help` | Show normal CLI help | 0 |
| `m32-bridge --help` | Show normal CLI help without entering shell | 0 |
| `m32-bridge --version` | Show version without entering shell | 0 |
| `m32-bridge health` | Local runtime health summary | 0 |
| `m32-bridge setup` | Guided local setup and `/info` probe | 0 |
| `m32-bridge get-info` | Read-only `/info` probe | 0 |
| `m32-bridge config show` | Show non-secret resolved/saved config | 0 |
| `m32-bridge config set --host <host> --port <port>` | Validate and save endpoint config | 0 |
| `m32-bridge config validate` | Validate config sources | 0 |
| `m32-bridge doctor-runtime` | Runtime diagnostics | 0 |
| `m32-bridge detect-device` | Device identity and hardware classification | 0 |
| `m32-bridge mcp-server` | Start local stdio MCP server | 0 during startup |

Commands that support automation must accept JSON output. Human output may be friendly, but JSON output is the acceptance-test contract.

## No-Subcommand Behavior

When `m32-bridge` runs with no subcommand:

- If `stdin` is a TTY, start the optional interactive shell.
- If `stdin` is not a TTY, do not start the shell and do not block for input.
- Non-interactive no-subcommand launch returns a structured response with an error such as `NON_INTERACTIVE_SHELL_REQUIRED` and suggestions including `m32-bridge setup`, `m32-bridge health`, and `m32-bridge mcp-server`.

## Interactive Slash Commands

Slash commands are valid only inside the `m32-bridge` interactive shell. They must not be documented as standalone operating-system terminal commands.

| Shell Command | Normal CLI Equivalent | OSC Writes |
| --- | --- | --- |
| `/help` | `m32-bridge help` | 0 |
| `/runsetup` | `m32-bridge setup` | 0 |
| `/getinfo` | `m32-bridge get-info` | 0 |
| `/config` | `m32-bridge config show` | 0 |
| `/config set host <host>` | `m32-bridge config set --host <host>` | 0 |
| `/config set port <port>` | `m32-bridge config set --port <port>` | 0 |
| `/test` | `m32-bridge get-info` or local health test | 0 |
| `/doctor` | `m32-bridge doctor-runtime` | 0 |
| `/detect` | `m32-bridge detect-device` | 0 |
| `/mcp` | `m32-bridge mcp-server --help` or MCP guidance command | 0 |
| `/claude` | Manual-copy Claude MCP guidance command | 0 |
| `/mode` | Runtime mode status command | 0 |
| `/lock` | Local write-lock command | 0 |
| `/unlock` | Local write-unlock command with governance checks | 0 |
| `/exit` | Exit shell | 0 |

No slash command may expose raw OSC, arbitrary path execution, shell execution, firmware operations, shutdown operations, phantom power enablement, sample-rate changes, clock changes, or approval-token bypasses.

## Configuration Sources

Supported sources:

1. CLI arguments.
2. Environment variables.
3. User-local config file.
4. Project-local config for development/testing only.

Precedence:

```text
CLI > environment > user config > project-local dev/test config
```

If no host is found, commands that need an endpoint return `NO_CONSOLE_HOST`. They must not scan or infer a host.

`M32_CONSOLE_HOST` may appear only as a clearly labelled example or advanced/manual override. `M32_CONSOLE_PORT` defaults to `10023` when host exists and remains editable.

## Common JSON Envelope

All JSON-capable commands should use a common envelope:

```json
{
  "ok": false,
  "status": "NO_CONSOLE_HOST",
  "error_code": "NO_CONSOLE_HOST",
  "message": "No console host is configured. Run m32-bridge setup.",
  "configured_host": null,
  "configured_port": null,
  "attempted_path": "/info",
  "latency_ms": null,
  "exception_type": null,
  "osc_writes_sent": 0,
  "hardware_verified": false,
  "production_live_ready": false,
  "data": {},
  "recommendations": [
    "Run m32-bridge setup",
    "Run m32-bridge config show",
    "Use m32-bridge mcp-server from a local MCP host after setup"
  ]
}
```

Required common fields where applicable:

- `configured_host`
- `configured_port`
- `attempted_path`
- `latency_ms`
- `exception_type` on failure
- `osc_writes_sent`
- `hardware_verified`
- `production_live_ready`

## Error Codes

Expected structured codes include:

- `NO_CONSOLE_HOST`
- `NOT_CONFIGURED`
- `INVALID_CONFIG`
- `INVALID_HOST`
- `INVALID_PORT`
- `CONNECT_TIMEOUT`
- `NOT_CONNECTED`
- `UNEXPECTED_RESPONSE_ADDRESS`
- `PARTIAL_CAPABILITY`
- `CAPABILITY_LIMITATION`
- `NON_INTERACTIVE_SHELL_REQUIRED`
- `UNLOCK_DENIED_DISCONNECTED`
- `UNLOCK_DENIED_STALE`
- `UNLOCK_DENIED_UNRECONCILED`
- `UNLOCK_DENIED_EMERGENCY`
- `UNLOCK_DENIED_POLICY`

## Device Classification Contract

`m32-bridge detect-device --json` must classify as one of:

- `NOT_CONFIGURED`
- `EMULATOR_CONNECTED`
- `CONNECTED_UNVERIFIED`
- `HARDWARE_CANDIDATE`
- `HARDWARE_VERIFIED`

`hardware_verified` defaults to `false`. Emulator or Fake M32 evidence never sets `hardware_verified=true`. `production_live_ready` defaults to `false`.

## MCP Stdio Contract

Default MCP mode:

```json
{
  "command": "m32-bridge",
  "args": ["mcp-server"]
}
```

Normal Claude and AI MCP snippets should not embed host or port. The bridge reads saved user config. Environment overrides are allowed only in clearly labelled advanced/manual examples.

Stdio requirements:

- MCP messages use stdin/stdout.
- Logs go to stderr.
- No local MCP network port is opened by default.
- Snippets are manual-copy only and must not automatically modify Claude Desktop or other host config files.

## Unlock Governance Contract

`/unlock` and any CLI equivalent:

- affect only local write-lock state;
- send zero OSC writes;
- must not change executor, rollback, proposals, policy, EMERGENCY, or runtime-mode behavior;
- must reject unlock when disconnected, stale, unreconciled, in EMERGENCY, or blocked by write governance;
- must return a clear denial reason and `osc_writes_sent=0`.
