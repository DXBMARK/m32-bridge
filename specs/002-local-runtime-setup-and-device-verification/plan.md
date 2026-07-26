# Implementation Plan: Local Runtime Setup and Device Verification

**Branch**: `002-local-runtime-setup-and-device-verification` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-local-runtime-setup-and-device-verification/spec.md`

## Summary

Add a safe local runtime setup and device-verification layer around the existing M32 bridge. The feature defines a stable `m32-bridge` launcher, read-only setup/config/doctor/detect/get-info flows, optional interactive slash shell, local stdio MCP guidance, user-local configuration, OS-aware recommendations, and honest device classification that separates connectivity from hardware verification.

The implementation approach remains a local Python modular monolith. It must reuse the existing CLI/MCP/OSC/config/diagnostics boundaries, preserve current write governance, and avoid any WebUI, database, backend service, microservice split, installer implementation, remote MCP implementation, ChatGPT tunnel implementation, automatic Claude config editing, or production use of Fake M32/emulator evidence.

## Technical Context

**Language/Version**: Python 3.12, using the existing `src/m32_bridge` package layout.

**Primary Dependencies**: Existing stdlib and current project dependencies for CLI, config parsing, OSC UDP reads, pytest, and MCP stdio. No new database, service framework, WebUI framework, installer framework, or remote transport dependency is planned for this feature.

**Storage**: File-based non-secret runtime configuration. Default storage is an application-owned user-local config file. Project-local configuration is allowed only for explicitly marked development and test contexts.

**Testing**: Existing pytest suites under `tests/unit`, `tests/property`, `tests/e2e_mcp`, `tests/integration_fake_m32`, `tests/integration_external_emulator`, `tests/cross_platform`, and `tests/hardware_acceptance`, with this feature adding focused tests in the appropriate existing directories.

**Target Platform**: Local operator machines on macOS, Windows, Linux, and Raspberry Pi OS. MCP host integration is local stdio by default.

**Project Type**: Local CLI plus stdio MCP bridge, implemented as a modular monolith.

**Performance Goals**: Setup, config validation, doctor, get-info, and detect-device commands must return bounded structured output and must not hang. `/info` probes and optional detection reads must expose `latency_ms` and timeout classifications. Non-interactive `m32-bridge` launch with no subcommand must return immediately with a structured error/help response instead of waiting for input.

**Constraints**: `setup`, `config`, `doctor-runtime`, `detect-device`, `get-info`, `/runsetup`, `/getinfo`, `/config`, `/test`, `/doctor`, `/detect`, `/lock`, and `/unlock` must send zero OSC writes. No raw OSC, arbitrary path execution, shell execution, firmware operations, shutdown operations, phantom power enablement, sample-rate changes, clock changes, safety-policy relaxation, executor change, rollback change, proposal change, or EMERGENCY behavior change is in scope. `M32_CONSOLE_HOST` must not be hardcoded except in clearly labelled examples. `M32_CONSOLE_PORT` defaults to `10023` only when a host is configured and remains editable through every supported configuration source.

**Scale/Scope**: One local bridge process for one configured console endpoint per operator environment. No multi-tenant, cloud, database, or service orchestration scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Console State Authority**: PASS. The plan uses live `/info` and explicit optional capability probes as evidence; emulator, stale, unknown, unsupported, and hardware-unverified states remain visible.
- **Safe MCP Surface and Policy Enforcement**: PASS. The plan does not add raw OSC, arbitrary paths, shell execution, firmware, shutdown, phantom, sample-rate, or clock controls. MCP remains typed and local stdio by default.
- **Human-Approved Proposal Execution**: PASS. This feature is read-only for setup/config/doctor/detect/get-info and does not change executor, rollback, proposals, policy, R3/R4 permissions, or host confirmation behavior.
- **Verification, Audit, and Fail-Closed Recovery**: PASS. Unlock governance must reject disconnected, stale, unreconciled, or EMERGENCY states with `osc_writes_sent=0`; no write readiness is claimed before required evidence.
- **Emulator Honesty and Minimal MVP Architecture**: PASS. Emulator and Fake M32 evidence never produce `HARDWARE_VERIFIED` or production readiness. No WebUI, database, microservice, installer implementation, remote MCP implementation, or ChatGPT tunnel implementation is added.
- **Operational Constraints**: PASS. Default runtime remains `OBSERVE`; stdio MCP logs go to stderr and stdout stays protocol-clean.
- **Quality Gates**: PASS. The plan includes focused tests for no-write behavior, config precedence, missing-host fail-closed behavior, emulator classification, stdio cleanliness, OS recommendations, USB best-effort detection, and unlock denial governance.

## Project Structure

### Documentation (this feature)

```text
specs/002-local-runtime-setup-and-device-verification/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli-contract.md
│   └── runtime-output.schema.json
├── checklists/
│   └── requirements.md
└── spec.md
```

### Source Code (repository root)

The future implementation should stay within the existing package structure and avoid introducing new service or UI layers:

```text
src/m32_bridge/
├── cli.py                         # Stable m32-bridge subcommands and interactive shell entry
├── __main__.py                    # Development module entry remains secondary to launcher guidance
├── config/
│   ├── schemas.py                 # Runtime config validation and non-secret schema additions
│   └── emulator.py                # Existing emulator helpers remain test/development oriented
├── diagnostics/
│   └── runtime.py                 # Runtime diagnostics and /info probe reporting
├── mcp/
│   ├── server.py                  # Local stdio server entry and tool registration
│   └── read_tools.py              # Read-only MCP diagnostics/config/device guidance tools if needed
├── osc/
│   ├── client.py
│   ├── discovery.py               # Must not become default scanning for missing host
│   └── transport.py
└── core/
    ├── emergency.py               # Existing EMERGENCY state remains authoritative
    ├── status.py                  # Existing runtime status/reconciliation evidence
    ├── executor.py                # Out of scope for this feature
    ├── rollback.py                # Out of scope for this feature
    ├── proposals.py               # Out of scope for this feature
    └── policy.py                  # Out of scope for this feature

tests/
├── unit/                          # Config validation, precedence, JSON envelopes, shell parser
├── property/                      # Existing properties plus config boundary properties if useful
├── e2e_mcp/                       # stdio cleanliness and MCP read-only diagnostics
├── integration_fake_m32/          # Development-only fake no-write regression coverage
├── integration_external_emulator/ # External emulator read-only detection and /info coverage
├── cross_platform/                # OS recommendation and path behavior checks
└── hardware_acceptance/           # Hardware evidence gate only; no real hardware writes in this feature
```

**Structure Decision**: Keep the modular monolith. Add planning contracts for CLI/runtime JSON behavior and later implement inside existing CLI, config, diagnostics, MCP read-tool, and OS-detection boundaries. Do not create `tasks.md` in this planning phase.

## Phase 0: Research

Research decisions are documented in [research.md](./research.md). The key decisions are:

- Resolve config in the order CLI arguments, environment variables, user config, then project-local development/test config.
- Return `NO_CONSOLE_HOST` when no host is configured; do not scan or guess.
- Use `m32-bridge` as the stable end-user and MCP launcher; do not assume global `py`.
- Keep local stdio MCP as the default and publish manual-copy host snippets only.
- Treat `/unlock` as local write-lock governance that cannot bypass reconciliation, runtime mode, EMERGENCY, stale-state, disconnected-state, or existing write-governance rules.
- Classify emulator, connected-unverified, hardware-candidate, and hardware-verified states separately.
- Keep future packaging strategy as documentation only.

## Phase 1: Design

Design artifacts are:

- [data-model.md](./data-model.md): Runtime configuration, probe result, device identity, USB evidence, shell session, unlock decision, OS recommendation, and MCP launch guidance models.
- [contracts/cli-contract.md](./contracts/cli-contract.md): CLI, shell, MCP guidance, JSON envelope, and error-code contract.
- [contracts/runtime-output.schema.json](./contracts/runtime-output.schema.json): Common structured runtime output schema.
- [quickstart.md](./quickstart.md): Manual validation scenarios for later implementation without starting installer or hardware-write work.

## Test Strategy

Future implementation must add focused tests before changing behavior:

- **Setup no-write**: setup with valid, invalid, missing, and timed-out endpoints reports `osc_writes_sent=0`.
- **Detect-device no-write**: detection collects `/info` and optional evidence without write packets.
- **Get-info no-write**: `get-info` and `/getinfo` probe only `/info`.
- **Config validation**: host/port validation, malformed config handling, user-local path reporting, and source precedence.
- **Missing host**: all connect-capable diagnostics return `NO_CONSOLE_HOST` without guessing, scanning, or defaulting a host.
- **Emulator classification**: emulator endpoint returns `EMULATOR_CONNECTED`, `connected=true`, `hardware_verified=false`, and `production_live_ready=false`.
- **Hardware default**: detection keeps `hardware_verified=false` unless later hardware acceptance evidence exists.
- **Non-interactive shell guard**: `m32-bridge` with no subcommand and non-TTY stdin does not hang and returns `NON_INTERACTIVE_SHELL_REQUIRED` or equivalent structured help.
- **Slash commands shell-only**: help/docs do not present slash commands as standalone OS terminal commands.
- **Unlock governance**: `/unlock` and CLI equivalent are denied while disconnected, stale, unreconciled, or in EMERGENCY, with `osc_writes_sent=0`.
- **Stdio cleanliness**: MCP stdout contains protocol messages only and logs go to stderr.
- **OS recommendations**: macOS, Windows, Linux, and Raspberry Pi OS outputs describe user-local defaults, optional admin cases, and future packaging separately.
- **USB best-effort**: absent, blocked, or unavailable USB inspection is non-blocking and reports limitations.

## Phase 2 Boundary

This plan intentionally stops before task generation and implementation. `tasks.md` must be produced only by the SpecKit tasks phase, after review of this plan and its design artifacts.

## Complexity Tracking

No constitution violations are introduced by this plan. No extra project, service layer, database, WebUI, packaging implementation, remote MCP implementation, or safety-governance change is justified or planned.
