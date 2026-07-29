# Implementation Plan: Cross-Platform Installers and First-Run Setup

**Branch**: `003-cross-platform-installers-and-first-run-setup` | **Date**: 2026-07-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-cross-platform-installers-and-first-run-setup/spec.md`

## Summary

Define the cross-platform installer and first-run setup plan for M32 Bridge. The feature prioritizes user-local install scripts for POSIX shells and Windows PowerShell, creates a stable `m32-bridge` launcher on supported operating systems, verifies or guides installation of the user-managed runtime, integrates the existing read-only setup wizard after install, and provides post-install verification and manual-copy MCP guidance.

The implementation approach is intentionally script-first and user-local. It must not add binary installers, admin-by-default behavior, WebUI, database, backend service, microservices, remote MCP, ChatGPT tunnel, automatic Claude configuration edits, real hardware writes, production/live readiness claims, or emulator-based hardware verification.

## Technical Context

**Language/Version**: Existing project runtime is Python 3.12; installer planning targets POSIX shell behavior and Windows PowerShell behavior as user-facing script surfaces.

**Primary Dependencies**: Existing `m32-bridge` CLI and current project dependency set. The installer runtime manager strategy centers on `uv` availability or clear user guidance when `uv` cannot be installed in user space.

**Storage**: User-local application and launcher files plus existing user-local runtime configuration. No database, backend service, system-wide registry dependency, or secret storage is added.

**Testing**: Future validation should use pytest for POSIX/contract/path/OS detection/idempotency/no-write checks, plus static or contract checks for PowerShell behavior. Cross-platform checks should remain runnable without real hardware writes.

**Target Platform**: macOS, Linux, WSL, Windows PowerShell, Windows CMD launcher usage, and Raspberry Pi OS.

**Project Type**: Local CLI plus stdio MCP bridge with user-facing install scripts. The architecture remains a modular monolith.

**Performance Goals**: Install and setup commands must produce clear success or failure states without silent partial success. Non-interactive install/setup paths must return within 10 seconds when waiting for input would otherwise occur.

**Constraints**: User-local install by default; no administrator privileges by default; no global `py` assumption; no `/set` or state-changing OSC writes during install/setup/detect/verification; no automatic Claude config modification; no MCP shell execution surface; no hardware verification from emulator or install-time evidence; `production_live_ready` remains false.

**Scale/Scope**: One user-local installation per user account, one stable launcher per supported shell environment, and one saved runtime configuration consumed by the existing `m32-bridge` runtime.

## Installer Decisions

### Idempotency Decision

Installer scripts must be idempotent. Re-running `install.sh` or `install.ps1` must not break an existing user-local installation, overwrite saved runtime configuration without confirmation, or report silent partial success.

The planned installer state model is:

- `fresh_install`: no existing app/launcher is present; create user-local app and launcher paths.
- `existing_install`: an installation is present; inspect version/state before taking action.
- `repair`: required files are missing, corrupted, or inconsistent; restore the user-local app/launcher without deleting saved config by default.
- `update`: an older installation is present and a newer install source is available; update app files while preserving user config unless explicitly changed by the user.
- `already_current`: app and launcher already match the install source; report success and offer verification commands.
- `partial_failure`: a previous install did not complete; report recovery steps and either repair safely or stop with clear manual instructions.
- `failed`: required steps cannot complete; return actionable failure details and do not claim installation success.

### Install Command UX Decision

The recommended install path is download, inspect, then run:

1. Download `install.sh` or `install.ps1`.
2. Inspect the script before execution.
3. Run the script locally from the user's shell.

Convenience one-liners such as `curl -LsSf <url>/install.sh | sh` and `powershell -ExecutionPolicy Bypass -c "irm <url>/install.ps1 | iex"` may be documented, but only as convenience examples. They must not be the only documented path and must not be presented as safer than the download-inspect-run workflow.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Console State Authority**: PASS. The plan uses `/info` as setup evidence and keeps missing, unreachable, emulator, and unverified states visible. It does not use model memory or installer assumptions as live console authority.
- **Safe MCP Surface and Policy Enforcement**: PASS. MCP guidance remains manual-copy stdio and does not add raw OSC, arbitrary path execution, shell execution, firmware, shutdown, phantom, sample-rate, clock, or approval-token surfaces.
- **Human-Approved Proposal Execution**: PASS. This installer feature is no-write. It does not alter executor, rollback, proposals, policy, host confirmation, R3/R4 permissions, or approval flow.
- **Verification, Audit, and Fail-Closed Recovery**: PASS. Install/setup/detect must report zero writes and fail clearly when runtime, config, or endpoint checks cannot complete.
- **Emulator Honesty and Minimal MVP Architecture**: PASS. Emulator/Fake M32 evidence never sets `hardware_verified=true` and never produces production/live readiness. No WebUI, database, microservice split, or remote tunnel is planned.
- **Operational Constraints**: PASS. Local stdio MCP remains the default; OSC remains on the configured private console endpoint; install scripts do not create network bridges or public exposure.
- **Quality Gates**: PASS. Planned tests cover installer contracts, OS detection, path calculation, idempotency, no-admin defaults, first-run no-write setup, non-TTY no-hang behavior, launcher availability, MCP snippets, and lifecycle guidance.

## Project Structure

### Documentation (this feature)

```text
specs/003-cross-platform-installers-and-first-run-setup/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── installer-contract.md
│   ├── installer-output.schema.json
│   └── mcp-guidance-contract.md
├── checklists/
│   └── requirements.md
└── spec.md
```

### Source Code (repository root)

This planning phase does not modify source files. Future implementation should stay within existing boundaries and add installer script surfaces without adding services or binary packages:

```text
scripts/
├── install.sh                    # POSIX installer surface, future implementation
└── install.ps1                   # PowerShell installer surface, future implementation

src/m32_bridge/
├── cli.py                        # Existing m32-bridge commands reused by installer flows
├── config/                       # Existing user-local config resolution
├── diagnostics/                  # Existing setup, doctor, OS, and device diagnostics
└── mcp/                          # Existing local stdio MCP server

tests/
├── unit/                         # installer contracts, path/idempotency, guidance checks
├── cross_platform/               # OS detection and path behavior
├── integration_fake_m32/         # first-run/setup/detect no-write checks
└── e2e_mcp/                      # launcher and MCP stdio guidance/startup checks
```

**Structure Decision**: Keep the existing local modular monolith. Installer scripts are user-facing launch/bootstrap surfaces around existing CLI behavior, not a new app, service, packaging system, or MCP transport.

## Phase 0: Research

Research decisions are documented in [research.md](./research.md). Key decisions:

- Prioritize script installers over binary packages for this feature.
- Use user-local default install paths and no admin privileges by default.
- Use `uv` as the managed runtime strategy; do not rely on global Python or `py`.
- Make download-inspect-run the recommended install UX; treat `curl | sh` and `irm | iex` as convenience examples only.
- Require idempotent installer behavior for fresh install, existing install, repair, update, already current, partial failure recovery, and failed states.
- Treat WSL and Raspberry Pi OS as distinct OS targets with tailored recommendations.
- Preserve setup as `/info` only and save config only after confirmation.
- Keep MCP guidance manual-copy only with `m32-bridge mcp-server` and no embedded host/port by default.
- Keep all binary packaging, signing, release automation, service/image work, `.mcpb`/`.dxt`, and USB portable kit as future-only phases.

## Phase 1: Design

Design artifacts are:

- [data-model.md](./data-model.md): Installation target, install state, runtime manager state, launcher, first-run setup session, verification command, MCP guidance, lifecycle action, and packaging roadmap entities.
- [contracts/installer-contract.md](./contracts/installer-contract.md): Script behavior, install locations, idempotency states, first-run setup, verification commands, and no-write requirements.
- [contracts/installer-output.schema.json](./contracts/installer-output.schema.json): Structured installer/setup status output for automation and tests.
- [contracts/mcp-guidance-contract.md](./contracts/mcp-guidance-contract.md): Manual-copy MCP snippet contract and forbidden automatic configuration behavior.
- [quickstart.md](./quickstart.md): Validation guide for future implementation without running real hardware writes or binary packaging work.

## Test Strategy

Future tasks should add tests before implementation for:

- POSIX installer dry-run and contract behavior on macOS, Linux, WSL, and Raspberry Pi OS.
- PowerShell installer static/contract behavior and CMD launcher creation.
- Path calculation for POSIX and Windows user-local app and launcher locations.
- OS detection, including WSL distinct from native Linux and Raspberry Pi OS distinct from generic Linux.
- No-admin default behavior and clear messages when user-local paths are not writable.
- Runtime manager handling for present, installable, blocked, and manual-guidance cases.
- Idempotency states: fresh install, existing install, repair, update, already current, and partial failure recovery.
- First-run setup TTY flow, non-TTY no-hang flow, and `/info`-only no-write behavior.
- Post-install command guidance for `health`, `setup`, `get-info`, `detect-device`, and `doctor-runtime`.
- MCP snippet guidance: manual-copy only, `m32-bridge mcp-server`, no embedded host/port by default, no Claude config auto-write.
- Lifecycle guidance for update, repair, uninstall, and future-only packaging scope.
- Safety inventory regression proving no forbidden MCP or installer surfaces were added.

## Phase 2 Boundary

This plan intentionally stops before task generation and implementation. `tasks.md` must be produced only by the SpecKit tasks phase after this plan is reviewed.

## Complexity Tracking

No constitution violations are introduced. No database, WebUI, backend service, microservice, binary installer generation, remote MCP implementation, ChatGPT tunnel, automatic Claude config editing, real hardware write validation, or production/live readiness claim is planned.
