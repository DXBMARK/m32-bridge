# M32 MCP Bridge

Local Python 3.12 modular monolith for a safety-first MCP bridge to a Midas
M32/X32-family console over OSC/UDP.

## MVP Boundaries

- Claude Desktop over MCP stdio is the primary host path.
- Optional ChatGPT transport stays disabled by default. The only documented
  ChatGPT path for this MVP is Secure MCP Tunnel.
- No custom WebUI, no AI backend integration, no database, no microservices, no
  M32-Edit control, no raw OSC tools, and no arbitrary-path tools are part of
  the MVP.
- Emulator results are never hardware verification.
- Production, Live readiness, and `hardware_verified` claims require the final
  real-M32 Hardware Acceptance suite.

## Safety Rules

The console or emulator endpoint is the source of truth for operational state.
Manual console changes take priority over automation.

Every state-changing operation must follow:

```text
Read -> Proposal -> MCP Host Human Confirmation -> Policy Check -> Write -> Readback -> Audit
```

Write tools must not be configured as Always Allow. Do not add model-supplied
approval tokens.

`EMERGENCY` is AI write-lock only: it stops automation, cancels pending
proposals, blocks all AI console writes, blocks AI mute, blocks AI rollback, and
returns to `OBSERVE` only after reconciliation. No AI-controlled mute, rollback,
or console write is allowed in `EMERGENCY`.

R3 operations remain `SOUNDCHECK`-only. R4 operations remain blocked.

## Development Gates

Run gates in this order:

```text
Unit/Codec -> Fake M32 -> External Emulator -> MCP Inspector and Claude Desktop -> Windows/macOS -> Hardware Acceptance
```

Current Unit/Codec gate command:

```sh
uv run --extra test python -m pytest tests/unit tests/property
```

Fake M32 connection proof:

```sh
uv run --extra test python -m pytest tests/integration_fake_m32/test_connect_live_state.py tests/integration_fake_m32/test_connection_fail_closed.py
```

This proof connects to the project-owned Fake M32, renews `/xremote`, reads
Channel 1 headamp gain at `+10.0 dB`, injects a manual change to `+6.0 dB`, and
verifies the bridge observes the newer revision with an emulator source label.

The external emulator gate is required before MCP readiness claims, but it still
does not grant hardware verification.

Do not redistribute emulator binary artifacts from this project. Configure an
external local emulator only when its license and local usage are understood.

## Optional ChatGPT Transport

Claude Desktop over MCP stdio is the primary MVP path. ChatGPT connectivity is
optional and disabled by default.

The optional secondary MCP transport is guarded for Secure MCP Tunnel use only.
It must not expose the OSC endpoint, must not provide raw OSC or arbitrary-path
tools, and must bind only to loopback or private interfaces if explicitly
enabled by configuration.

There is no production ChatGPT enablement in the current MVP. Do not run a
production tunnel, public bind, or Internet-exposed OSC endpoint from this
project.

## Operator Controls

The local operator controls are command-line tools. They are not a WebUI and do
not add raw OSC, arbitrary-path, or approval-token surfaces.

```sh
py -m m32_bridge health
py -m m32_bridge doctor
py -m m32_bridge snapshot
py -m m32_bridge verify-connection
py -m m32_bridge audit-tail
```

Each command writes structured JSON to stdout. Diagnostics and process errors go
to stderr, and non-zero exit codes indicate failure, denial, or configuration
errors.

These controls are local MVP operator utilities only. They do not imply
production readiness, Live readiness, or hardware verification.

## Local MCP Validation

The local MCP server entry point is the Python module:

```sh
py -m m32_bridge
```

For Claude Desktop local validation, configure a local stdio MCP server command
that runs `py -m m32_bridge`. Use a local config profile equivalent to
`config.example.yaml`: target `127.0.0.1`, stdio enabled, secondary HTTP
transport disabled, write lock enabled on startup, and no raw OSC or
arbitrary-path tools.

Use MCP Inspector locally against the same stdio command to verify tool
inventory, metadata, structured outputs, denials, and stdout/stderr protocol
cleanliness. Inspector validation is local developer validation only.

Claude Desktop validation is also local validation only. It does not mean
production readiness, Live readiness, or hardware verification.

The External X32 Emulator remains optional for the separate external emulator
gate only. Real hardware acceptance is still required later before any real
console or live-use claim.

## Cross-Platform Release Gate

Windows and macOS evidence is required before an MVP release claim. These are
local development gates, not production or Live instructions.

Windows commands:

```sh
py -m compileall src tests
py -m pytest tests/unit tests/property -q -p no:cacheprovider
py -m pytest tests/integration_fake_m32 -q -p no:cacheprovider
py -m pytest tests/e2e_mcp -q -p no:cacheprovider
py -m m32_bridge health
```

macOS commands:

```sh
py -m compileall src tests
py -m pytest tests/unit tests/property -q -p no:cacheprovider
py -m pytest tests/integration_fake_m32 -q -p no:cacheprovider
py -m pytest tests/e2e_mcp -q -p no:cacheprovider
py -m m32_bridge health
py -m m32_bridge doctor
```

Evidence for each platform must include the platform name, Python 3.12 version,
the exact `py -m` commands, exit codes, and JSON output from `py -m m32_bridge
health`.

Windows smoke does not count as passed unless it is run on a real Windows
runtime. macOS smoke does not count as passed unless it is run on a real macOS
runtime.

This gate does not run Hardware Acceptance and does not replace the later real
M32 hardware gate.

## Hardware Acceptance Evidence

Hardware Acceptance is manual and gated. It requires real M32 evidence artifacts
before any `hardware_verified` claim can be considered. Fake M32 and external
emulator results are never hardware evidence.

Required readiness evidence:

- identity
- firmware
- expansion card
- clock
- AES50
- card sync
- routing
- network isolation

Required manual-change evidence:

- initial read of the real console value
- manual gain or fader change on the physical console
- second read of the changed value
- changed revision, timestamp, and source metadata

Required gated safe-write evidence before real console writes:

- isolated safe write case
- readback
- manual conflict
- disconnect/reconnect
- targeted rollback

Hardware tests remain `pending` or `not_available` when real hardware evidence is
absent. Do not substitute Fake M32 or the External X32 Emulator for a real M32.

## External Emulator Gate

The external emulator gate uses Patrick-Gilles Maillot X32 Emulator as the
approved emulator for this MVP gate:

- Primary reference: https://sites.google.com/site/patrickmaillot/x32
- Supporting source/tools repository: https://github.com/pmaillot/X32-Behringer

Run the emulator outside this repository. Do not copy or redistribute emulator
binaries in this project. Configure the bridge test target with environment
variables:

```sh
export M32_EXTERNAL_EMULATOR_HOST=127.0.0.1
export M32_EXTERNAL_EMULATOR_PORT=10023
```

UDP `10023` is the usual X32/M32 OSC control port, but the actual port shown by
the running emulator should be used.

The gate validates OSC behavior only:

- read-only `/info` identity
- leaf reads such as channel fader and channel name
- safe write, readback, and targeted rollback through the bridge proposal,
  MCP-host-confirmed executor, validated operation boundary, and readback path

Known Patrick X32 Emulator limitations observed in this gate:

- It is OSC-only and does not emulate Audio, MIDI, or USB behavior.
- `/node` may return `unsupported_or_timeout`.
- Direct `/meters` requests may return `unsupported_or_timeout`.
- Some leaf reads may not include revision metadata.

External emulator success never grants `hardware_verified`, does not authorize
production or Live use, and does not replace Hardware Acceptance with a real
M32.

## MVP Quality Gate Evidence

Evidence captured on 2026-07-26 from a local macOS (`Darwin`) development
process. `py` was provided by a temporary `/tmp/py` shim because it was not
available in `PATH`. Patrick-Gilles Maillot X32 Emulator was running and reported
`Listening to port: 10023, X32 IP = 192.168.8.88`.

All gates below preserve `hardware_verified=False` unless real hardware
acceptance evidence is explicitly present. This evidence does not claim
production readiness or Live readiness.

| Gate | Command | Status | Tests | Evidence notes |
| --- | --- | --- | ---: | --- |
| Compile | `py -m compileall src tests` | passed | n/a | Source and tests compiled. |
| Unit and property | `py -m pytest tests/unit tests/property -q -p no:cacheprovider` | passed | 84 | Re-run with local UDP permission because two unit tests start Fake M32 on loopback. |
| Fake M32 integration | `py -m pytest tests/integration_fake_m32 -q -p no:cacheprovider` | passed | 46 | Re-run with local UDP permission for Fake M32 loopback bind. Fake M32 is not hardware evidence. |
| External emulator | `py -m pytest tests/integration_external_emulator -q -p no:cacheprovider` | passed | 8 | Patrick X32 Emulator target: `M32_EXTERNAL_EMULATOR_HOST=192.168.8.88`, `M32_EXTERNAL_EMULATOR_PORT=10023`. External emulator remains `hardware_verified=False`. |
| MCP e2e | `py -m pytest tests/e2e_mcp -q -p no:cacheprovider` | passed | 43 | Re-run with local UDP permission because scripted MCP tests start Fake M32. Claude Desktop app was not launched. |
| Cross-platform | `py -m pytest tests/cross_platform -q -p no:cacheprovider` | passed | 5 | macOS smoke ran on `Darwin`; Windows smoke reported `not_run_on_this_platform` and does not count as a real Windows pass. |
| Hardware acceptance | `py -m pytest tests/hardware_acceptance -q -p no:cacheprovider` | pending/not_available | 13 | Tests passed by verifying structured `pending`/`not_available` behavior without real M32 evidence. No real hardware was used. |
| Final safety review | `py -m pytest tests/e2e_mcp/test_tool_inventory.py tests/unit/test_scope_guard.py tests/integration_fake_m32/test_write_audit.py tests/integration_fake_m32/test_emergency_lock.py -q -p no:cacheprovider` | passed | 17 | Re-run with local UDP permission for Fake M32 loopback bind. Confirms no prohibited MCP tools, scope guard, audit coverage, and EMERGENCY lock behavior. |

Hardware Acceptance remains unresolved for real M32 operation. The current
hardware gate result is `pending`/`not_available` until a physical M32 evidence
artifact covers readiness, manual change challenge, and gated safe-write checks.
