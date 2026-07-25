# Local MVP Runbook

This runbook is for local developer validation only. It does not add production,
Live, or hardware acceptance behavior.

## Safety Warnings

- Do not write to a real console before Hardware Acceptance is complete.
- The Patrick-Gilles Maillot X32 Emulator is not hardware.
- Fake M32 and external emulator evidence must keep `hardware_verified=False`.
- A real M32 still remains `hardware_verified=False` until real-M32 evidence
  exists and the Hardware Acceptance suite passes.
- Do not use this MVP for Live or production operation.
- Do not start a production tunnel, public bind, Internet-exposed OSC endpoint,
  or non-stdio MCP exposure from this runbook.
- Keep OSC local/LAN-only and isolated from Internet-facing interfaces.

## Prerequisites

- Python 3.12.
- Project dependencies installed in the local development environment.
- Terminal access on macOS Terminal, Windows PowerShell, or Windows Terminal.
- Optional: Patrick-Gilles Maillot X32 Emulator for the external emulator gate.
- Optional: MCP Inspector or Claude Desktop for local stdio validation.

Run all commands from the repository root:

```sh
cd "/Users/sunmarke/Downloads/M32 AI MCP Bridge"
```

On another machine, replace the path with your local checkout path.

## Python Launcher

The project commands use the `py` launcher form:

```sh
py -m m32_bridge health
```

### macOS

If `py` already exists:

```sh
py --version
```

If `py` is missing but `python3.12` exists, create a local shim outside the
repository:

```sh
mkdir -p /tmp/m32-local-bin
printf '#!/bin/sh\nexec python3.12 "$@"\n' > /tmp/m32-local-bin/py
chmod +x /tmp/m32-local-bin/py
export PATH="/tmp/m32-local-bin:$PATH"
py --version
```

If your Python command is `python3`, change the shim to `exec python3 "$@"` only
after confirming it is Python 3.12:

```sh
python3 --version
```

### Windows

Windows normally provides `py.exe` through the Python launcher:

```powershell
py -3.12 --version
py -m m32_bridge health
```

If `py` is missing but `python` points to Python 3.12, create a small shim in a
local tools directory and put it first in `PATH` for the current PowerShell
session:

```powershell
python --version
New-Item -ItemType Directory -Force .local\bin | Out-Null
Set-Content .local\bin\py.cmd '@echo off'
Add-Content .local\bin\py.cmd 'python %*'
$env:PATH = "$(Resolve-Path .local\bin);$env:PATH"
py --version
```

This shim is a local developer convenience only. It does not change project
runtime behavior.

## Install Dependencies

Use the dependency workflow already approved for the checkout. If the local
environment already has dependencies installed, skip this step.

With `uv`:

```sh
uv sync --extra test
```

Then verify import and packaging startup:

```sh
py -m m32_bridge health
py -m m32_bridge doctor
```

Both commands must print JSON. `hardware_verified` must remain `false`.

## Patrick X32 Emulator

Use Patrick-Gilles Maillot X32 Emulator only as an external local developer
tool. Do not copy emulator binaries into this repository and do not redistribute
them from this project.

### Start From Terminal

Download or install the emulator outside this repository, then start it from a
terminal according to the package you have.

macOS example:

```sh
cd "/path/to/X32-Emulator"
./X32-Emulator
```

Windows PowerShell example:

```powershell
cd "C:\path\to\X32-Emulator"
.\X32-Emulator.exe
```

Use the actual executable name from your emulator package. Leave the emulator
running while you validate the bridge.

### Read IP And Port

When the emulator starts, read its terminal output or status window. Look for
values equivalent to:

```text
Listening to port: 10023
X32 IP = 192.168.x.x
```

Use the exact IP and port printed by your emulator. UDP `10023` is the usual
X32/M32 OSC control port, but the running emulator output is authoritative for
this local test.

### Configure Environment

macOS:

```sh
export M32_EXTERNAL_EMULATOR_HOST=192.168.x.x
export M32_EXTERNAL_EMULATOR_PORT=10023
```

Windows PowerShell:

```powershell
$env:M32_EXTERNAL_EMULATOR_HOST = "192.168.x.x"
$env:M32_EXTERNAL_EMULATOR_PORT = "10023"
```

Replace `192.168.x.x` and `10023` with the emulator values. Emulator success is
still `hardware_verified=False`.

## Operator Controls

These commands are local operator controls. They are not a WebUI, do not expose
raw OSC, and do not authorize real-console writes.

Read local health:

```sh
py -m m32_bridge health
```

Check config and startup posture:

```sh
py -m m32_bridge doctor
```

Verify read-only connection checks against a target:

```sh
py -m m32_bridge verify-connection --host "$M32_EXTERNAL_EMULATOR_HOST" --port "$M32_EXTERNAL_EMULATOR_PORT"
```

Windows PowerShell:

```powershell
py -m m32_bridge verify-connection --host $env:M32_EXTERNAL_EMULATOR_HOST --port $env:M32_EXTERNAL_EMULATOR_PORT
```

Capture a read-only snapshot:

```sh
py -m m32_bridge snapshot --host "$M32_EXTERNAL_EMULATOR_HOST" --port "$M32_EXTERNAL_EMULATOR_PORT"
```

Tail local audit records:

```sh
py -m m32_bridge audit-tail
```

Use `--audit-path` when validating a specific audit file:

```sh
py -m m32_bridge audit-tail --audit-path .local/audit/m32-bridge.audit.jsonl --limit 20
```

## Local MCP Stdio

For this MVP, use local MCP stdio only. Do not start Streamable HTTP, Secure MCP
Tunnel, production tunnels, public binds, or Internet-exposed OSC endpoints for
this runbook.

The host process launches the local stdio command. You do not need to expose a
network server for Claude Desktop or MCP Inspector stdio validation.

Use a stdio command shape equivalent to:

```sh
py -m m32_bridge
```

Keep logs on stderr and protocol data on stdout. Operator commands such as
`py -m m32_bridge health` are JSON diagnostics; they are separate from an MCP
host session.

### MCP Inspector

Use MCP Inspector in local stdio mode and set the command to:

```text
py
```

Set arguments to:

```text
-m
m32_bridge
```

Set the working directory to the repository root. Do not use an HTTP transport
or tunnel for this local MVP runbook.

### Claude Desktop

Add only a local stdio server entry. Do not configure HTTP, tunnel URLs, or
production endpoints.

Safe stdio-only example:

```json
{
  "mcpServers": {
    "m32-bridge-local": {
      "command": "py",
      "args": ["-m", "m32_bridge"],
      "cwd": "/Users/sunmarke/Downloads/M32 AI MCP Bridge",
      "env": {
        "M32_EXTERNAL_EMULATOR_HOST": "192.168.x.x",
        "M32_EXTERNAL_EMULATOR_PORT": "10023"
      }
    }
  }
}
```

On Windows, use a Windows path for `cwd`, for example:

```json
{
  "mcpServers": {
    "m32-bridge-local": {
      "command": "py",
      "args": ["-m", "m32_bridge"],
      "cwd": "C:\\Users\\you\\path\\to\\M32 AI MCP Bridge",
      "env": {
        "M32_EXTERNAL_EMULATOR_HOST": "192.168.x.x",
        "M32_EXTERNAL_EMULATOR_PORT": "10023"
      }
    }
  }
}
```

The emulator host and port must point to the local emulator only. This config is
not a Live or production setup.

## Manual Validation Conversation

Use this first scripted conversation with MCP Inspector or Claude Desktop
against Fake M32 or the Patrick X32 Emulator only. Do not aim it at a real
console.

1. Status

   ```text
   Show the current M32 bridge status. Include source, runtime mode,
   connection lifecycle, and hardware_verified.
   ```

   Expected: the response is structured, identifies emulator or not-connected
   state, and keeps `hardware_verified=false`.

2. Read channel

   ```text
   Read channel 1. Include the current headamp or fader value, revision/source
   metadata when available, and do not create a proposal.
   ```

   Expected: read-only result, no proposal, no OSC writes.

3. Preflight

   ```text
   Run event preflight for the current emulator state. Return findings and
   recommendations separately. Do not change console state.
   ```

   Expected: findings/recommendations only, no proposal, no writes.

4. RTA analysis

   ```text
   Analyze the current RTA source. Report the source identity, confidence,
   band count, and whether per-channel spectra are available. Do not scan
   sources unless I explicitly ask.
   ```

   Expected: current-mode RTA analysis is read-only and keeps
   `proposal_created=false`. If source scan is requested later, run it only in
   `SOUNDCHECK` and only against explicit configured sources because scan mode
   may write and restore `/rta/source` on the emulator.

5. Propose change

   ```text
   Propose a safe emulator-only change to channel 1 fader from the currently
   read value to a small nearby value. Return proposal_id, proposal_digest,
   risk summary, operations, and rollback candidates. Do not execute yet.
   ```

   Expected: proposal is created, `osc_writes_sent=0`, and no write occurs.

6. Host confirmation

   ```text
   I confirm this exact proposal for emulator-only execution:
   proposal_id=<paste proposal_id>
   proposal_digest=<paste proposal_digest>
   expected_operation_count=<paste count>
   ```

   Expected: the host confirmation is explicit. Do not use Always Allow and do
   not use model-supplied approval tokens.

7. Execute on emulator only

   ```text
   Execute the confirmed proposal on the emulator only, then read back the
   changed value and report audit status. Keep hardware_verified=false.
   ```

   Expected: execution is allowed only for emulator/SOUNDCHECK validation,
   readback verifies the change, audit is written, and `hardware_verified=false`.

8. Rollback

   ```text
   Roll back the executed emulator proposal, read back the rollback value, and
   report audit status. This is emulator-only.
   ```

   Expected: targeted rollback runs on emulator only, readback verifies the
   rollback, audit is written, and `hardware_verified=false`.

9. Audit tail

   ```text
   Show the latest audit records for the proposal execution and rollback.
   Summarize operation path, requested value, readback, result, and audit_id.
   ```

   Expected: audit records show execution and rollback. No production or Live
   readiness claim is made.

Stop validation if any response claims hardware verification from emulator
evidence, suggests real-console writes, asks for Always Allow, requests an
approval token, exposes raw OSC/arbitrary-path tools, or proposes a production
tunnel.

## Required Local Checks

Run the requested local gates:

```sh
py -m compileall src tests
py -m pytest tests/unit/test_safety_regression.py tests/e2e_mcp -q -p no:cacheprovider
```

If a local UDP test fails with a sandbox or permission error, rerun only in an
environment where local loopback UDP is allowed. Do not count a sandbox failure
as a product failure or as successful validation.
