# X32-Bridge MCP

Powered by DXBMARK LLC

## What It Is

X32-Bridge MCP is a local safety-first MCP bridge for Midas M32 and X32-family digital consoles using OSC.

It runs under local operator control and exposes read, analysis, and recommendation workflows to supported MCP hosts. Installer and setup flows are conservative: they do not scan the network, do not send `/set`, do not send OSC writes, and do not imply hardware verification or production readiness.

## Current Version

- Product version: `0.1.0`
- Package: `m32-mcp-bridge`
- CLI: `m32-bridge`
- Python range: `>=3.11,<3.14`
- Approved managed runtime: CPython `3.13.x`
- Primary MCP transport: local `stdio`
- Runtime configuration: `~/.m32-bridge/runtime.yaml`

## Installation

Use the installer scripts from this project. They install user-local application files and a stable `m32-bridge` launcher without administrator access or system Python modification.

### macOS / Linux

```sh
sh scripts/install.sh
```

Dry run:

```sh
sh scripts/install.sh --dry-run
```

### Windows

```powershell
.\scripts\install.ps1
```

Dry run:

```powershell
.\scripts\install.ps1 -DryRun
```

## First Run

Open the installer TTY and run:

```text
/setup
```

Setup asks for:

- Console IP: the known address configured on the console itself.
- Port: default `10023`.
- Label: optional local name such as `Main Console`.
- Intended target: physical console, emulator/test endpoint, or unknown.

`SAVE` stores the configuration first, then runs one read-only `/info` verification. If the endpoint is offline, the configuration remains saved and can be verified later with `/get-info` or `/verify-device`.

## Runtime Configuration

Default file:

```text
~/.m32-bridge/runtime.yaml
```

Precedence:

1. explicit CLI values
2. environment overrides
3. user runtime config
4. project-local config where explicitly allowed for development/testing
5. none

The installer does not guess this computer's local IP address and does not scan subnets.

## Running the MCP Server

For normal installed use, MCP clients should launch the installed user-local launcher:

```sh
m32-bridge mcp-server
```

Do not configure normal user clients to run development checkout launchers. Use development launch forms only for development-only testing.

## MCP Client Setup

Generate current local guidance:

```sh
m32-bridge mcp-config
```

Machine-readable output:

```sh
m32-bridge mcp-config --json
```

The generated profiles are manual-copy only. X32-Bridge MCP never edits Claude, Codex, Gemini, Antigravity, ChatGPT, or other MCP client configuration files automatically.

### Claude Desktop

Use the generated absolute launcher path from `m32-bridge mcp-config`. The shape is:

```json
{
  "mcpServers": {
    "x32-bridge-mcp": {
      "command": "/absolute/path/to/m32-bridge",
      "args": ["mcp-server"]
    }
  }
}
```

Steps:

1. Open Claude Desktop.
2. Open Settings > Developer.
3. Select Edit Config.
4. Merge the `x32-bridge-mcp` entry into the existing `mcpServers` object.
5. Do not replace unrelated existing servers.
6. Save.
7. Restart Claude Desktop.
8. Confirm the server shows Running.
9. Use View Logs if startup fails.

Do not paste a second top-level `mcpServers` object. Merge the entry into the existing object.

### Codex

This project does not define a canonical Codex config file path or schema. Use these values through the MCP configuration surface provided by your installed Codex version:

```text
Server name : x32-bridge-mcp
Transport   : stdio
Command     : absolute launcher path from m32-bridge mcp-config
Arguments   : mcp-server
Environment : none required
```

### Gemini CLI

Gemini CLI local stdio profile:

```json
{
  "mcpServers": {
    "x32-bridge-mcp": {
      "command": "/absolute/path/to/m32-bridge",
      "args": ["mcp-server"]
    }
  }
}
```

Configuration location hints:

- User configuration: `~/.gemini/settings.json`
- Project configuration: `.gemini/settings.json`

Merge the server into `mcpServers`, restart Gemini CLI or refresh MCP servers if supported, then run `/mcp list` and confirm `x32-bridge-mcp` is Ready. For this local stdio profile, use `command` and `args`, not `httpUrl`.

### Antigravity

Antigravity MCP support is client/version dependent. Use generic local stdio values and verify the schema in the installed version:

```text
Server name : x32-bridge-mcp
Transport   : stdio
Command     : absolute launcher path from m32-bridge mcp-config
Arguments   : mcp-server
Environment : none required
```

Field names and config locations may differ between Antigravity releases.

### ChatGPT

ChatGPT does not accept a direct local stdio command entry for this local installer.
Direct local stdio is not available in ChatGPT.

```text
Direct local stdio connection : not available
Required transport            : remote MCP
Private/local deployment      : Secure MCP Tunnel or another approved remote deployment method
```

The local command `m32-bridge mcp-server` cannot be pasted directly into ChatGPT as a local command entry. Current local installer readiness does not imply ChatGPT remote readiness. Do not create a localhost URL, public tunnel, OAuth flow, webhook, or port-forwarding setup from this local installer pass.

### Other / Generic MCP Clients

Generic local stdio values:

```text
Server name : x32-bridge-mcp
Transport   : stdio
Command     : absolute launcher path from m32-bridge mcp-config
Arguments   : ["mcp-server"]
Environment : {}
```

Use this only in MCP clients that support local command-based stdio servers.

## Why No Host/Port in Client Config

Normal MCP client profiles do not include `M32_CONSOLE_HOST`, `M32_CONSOLE_PORT`, or `M32_CONFIG`.

The saved runtime configuration is the source of truth:

```text
~/.m32-bridge/runtime.yaml
```

Duplicating host or port in client environment variables can make clients use stale endpoints. Environment overrides take precedence over saved runtime configuration and should be used only intentionally.

## Environment Variables

Normal installed use requires no environment variables.

Optional advanced overrides:

- `M32_CONSOLE_HOST`: overrides the saved runtime host.
- `M32_CONSOLE_PORT`: overrides the saved runtime port.
- `M32_CONFIG`: custom config path or mode where supported by the calling environment.

These overrides are advanced and can make client behavior differ from `/status` or `config show` expectations.

## Commands

```sh
m32-bridge health
m32-bridge setup
m32-bridge get-info
m32-bridge detect-device
m32-bridge doctor-runtime
m32-bridge config show
m32-bridge mcp-config
m32-bridge mcp-server
```

## TTY Commands

```text
/help
/contact
/mcp-config
/status
/health
/setup
/get-info
/verify-device
/doctor-runtime
/clear
/exit
```

## Safety Model

- Network scan: not used.
- OSC writes in installer/setup: `0`.
- `/set` in installer/setup: not sent.
- Administrator access: not required.
- System Python: unchanged.
- Managed Python: user-local through `uv`.
- Intended target: operator intent only, not hardware verification.
- Hardware verification: separate evidence gate.
- Production readiness: not implied by installer, setup, emulator, or `/info` response.

## Troubleshooting

Launcher missing:

- Run the installer again.
- Run `m32-bridge doctor-runtime`.
- Confirm `~/.local/bin` or the Windows user-local launcher directory is visible in PATH.

Server not Running:

- Confirm the client command is the installed launcher path.
- Confirm args are exactly `["mcp-server"]`.
- Use Claude Desktop View Logs or the equivalent client log surface.

Stale environment variables:

- Check `M32_CONSOLE_HOST`, `M32_CONSOLE_PORT`, and `M32_CONFIG`.
- Remove overrides from client config unless they are intentional.

Wrong console IP:

- Run `/setup` or `m32-bridge setup`.
- Store the known console endpoint.
- Run `/get-info` when the console is online.

Config source inspection:

- Run `/status`.
- Run `m32-bridge config show`.

Gemini CLI:

- Run `/mcp list`.
- Confirm `x32-bridge-mcp` is Ready.

ChatGPT:

- Direct local stdio is not available.
- Use a future remote MCP deployment plan such as Secure MCP Tunnel only when explicitly implemented and approved.

## Development-Only Setup

Development checkouts may run from a project environment during local development, but this is not the normal installed MCP client setup:

```sh
uv run --frozen --python 3.13 python -m m32_bridge mcp-server
```

Do not use this form for normal installed clients. User clients should use the installed `m32-bridge` launcher.

## Support

DXBMARK LLC

- Website: https://www.dxbmark.com
- Support: support@dxbmark.com
- Phone / WhatsApp: +971505121583
