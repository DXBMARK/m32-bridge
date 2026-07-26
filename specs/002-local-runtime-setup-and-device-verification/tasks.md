# Tasks: Local Runtime Setup and Device Verification

**Input**: Design documents from `specs/002-local-runtime-setup-and-device-verification/`

**Prerequisites**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli-contract.md](./contracts/cli-contract.md), [contracts/runtime-output.schema.json](./contracts/runtime-output.schema.json), [quickstart.md](./quickstart.md)

**Tests**: Required by the feature specification, plan, contracts, and constitution gates. Write tests before implementation inside each user-story slice.

**Scope Guard**: These tasks must not modify `src/m32_bridge/core/executor.py`, `src/m32_bridge/core/rollback.py`, `src/m32_bridge/core/proposals.py`, or `src/m32_bridge/core/policy.py`. No task may add WebUI, database, backend service, microservices, actual packaging/installers, remote MCP, ChatGPT tunnel implementation, automatic Claude config editing, real hardware writes, production/live readiness claims, raw OSC, arbitrary OSC paths, shell execution, firmware, shutdown, phantom power, sample-rate, clock, or approval-token bypass behavior.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish shared feature scaffolding without changing runtime behavior.

- [X] T001 Review the CLI/config/diagnostics/MCP boundaries for this feature in `src/m32_bridge/cli.py`, `src/m32_bridge/config/schemas.py`, `src/m32_bridge/diagnostics/runtime.py`, `src/m32_bridge/mcp/server.py`, and `src/m32_bridge/mcp/read_tools.py`; Req: FR-014, FR-020, FR-021, FR-043, SC-001, SC-004; Depends: None.
- [X] T002 [P] Add the runtime output schema validation test scaffold in `tests/unit/test_runtime_output_schema.py` for `specs/002-local-runtime-setup-and-device-verification/contracts/runtime-output.schema.json`; Req: FR-013, SC-004; Depends: None.
- [X] T003 [P] Add the no-write assertion helper plan in `tests/unit/test_runtime_no_write_helpers.py` to verify commands report or prove `osc_writes_sent=0` without depending on real hardware; Req: FR-003, FR-043, FR-058, FR-059, SC-001, SC-018, SC-019; Depends: None.
- [X] T004 [P] Add CLI subprocess helper coverage in `tests/unit/test_cli_runtime_helpers.py` for invoking future `m32-bridge` command paths through the managed environment command such as `uv run m32-bridge health` or the project console script equivalent, without assuming global `py`; Req: FR-015, FR-016, SC-006; Depends: None.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared config, output, launcher, and safety primitives required before any user story implementation.

**Critical**: Complete this phase before starting user story implementation.

- [X] T005 Add failing unit tests for `RuntimeConfig` validation and source metadata in `tests/unit/test_runtime_config.py`; Req: FR-002, FR-005, FR-006, FR-007, FR-010, SC-003, SC-011; Depends: T002.
- [X] T006 Add failing unit tests for config precedence `CLI > environment > user config > project-local dev/test` in `tests/unit/test_runtime_config_precedence.py`; Req: FR-007, FR-008, SC-011; Depends: T002.
- [X] T007 Add failing unit tests for missing host returning `NO_CONSOLE_HOST` without scan or guess in `tests/unit/test_runtime_config_missing_host.py`; Req: FR-011, FR-012, SC-003, SC-009; Depends: T002.
- [X] T008 Add failing unit tests for common JSON envelope validation against `runtime-output.schema.json` in `tests/unit/test_runtime_output_schema.py`; Req: FR-013, SC-004; Depends: T002.
- [X] T009 Implement `RuntimeConfig`, `ConfigResolution`, and validation helpers in `src/m32_bridge/config/runtime.py`; Req: FR-002, FR-005, FR-006, FR-007, FR-008, FR-010, FR-011, FR-012, SC-003, SC-009, SC-011; Depends: T005, T006, T007.
- [X] T010 Implement user-local and project-local development/test config path resolution in `src/m32_bridge/config/runtime.py`; Req: FR-005, FR-006, FR-007, FR-008, SC-005, SC-011; Depends: T009.
- [X] T011 Implement the common runtime JSON envelope builder and schema-compatible unsupported path objects in `src/m32_bridge/diagnostics/runtime_output.py`; Req: FR-013, FR-020, FR-032, SC-004; Depends: T008.
- [X] T012 Wire `NO_CONSOLE_HOST`, invalid config, timeout, and unexpected response address status mapping through `src/m32_bridge/diagnostics/runtime.py`; Req: FR-004, FR-011, FR-012, FR-020, SC-003, SC-004, SC-009; Depends: T009, T011.
- [X] T013 Add the stable `m32-bridge` console entry declaration without relying on global `py` in `pyproject.toml`; Req: FR-001, FR-014, FR-015, FR-016, SC-006; Depends: T004.
- [X] T014 Confirm the stable launcher dispatch uses existing package entrypoints in `src/m32_bridge/cli.py` and `src/m32_bridge/__main__.py` without changing write tools; Req: FR-001, FR-014, FR-015, FR-016; Depends: T013.
- [X] T015 Add a safety inventory regression test in `tests/unit/test_runtime_feature_scope_guard.py` proving no raw OSC, arbitrary path, shell, firmware, shutdown, phantom, sample-rate, clock, approval-token, WebUI, database, service, remote MCP, or tunnel surface was added; Req: FR-044, FR-048, FR-049, FR-052, FR-053, FR-060, FR-063, SC-020; Depends: T002.

**Checkpoint**: Foundation ready. User stories can now proceed in priority order or in parallel where marked.

---

## Phase 3: User Story 1 - Configure a Local Runtime Safely (Priority: P1) MVP

**Goal**: `m32-bridge setup` safely configures a local endpoint, probes `/info` only, reports structured diagnostics, and saves non-secret user-local config only after confirmation.

**Independent Test**: Run setup with valid, invalid, missing, and timed-out endpoints and verify structured JSON, config path, `/info` only, and `osc_writes_sent=0`.

### Tests for User Story 1

- [X] T016 [P] [US1] Add setup JSON contract tests for valid endpoint, invalid host, invalid port, timeout, and unexpected response address in `tests/unit/test_cli_setup.py`; Req: FR-001, FR-002, FR-003, FR-004, FR-013, SC-001, SC-003, SC-004; Depends: T011, T012.
- [X] T017 [P] [US1] Add setup config persistence tests for user-local default and project-local dev/test override in `tests/unit/test_cli_setup_config_paths.py`; Req: FR-005, FR-006, SC-005, SC-011; Depends: T009, T010.
- [X] T018 [P] [US1] Add setup no-write tests proving only `/info` is attempted and no `/set` or state-changing OSC packet is sent in `tests/integration_fake_m32/test_setup_no_write.py`; Req: FR-003, FR-043, SC-001; Depends: T003.
- [X] T019 [P] [US1] Add missing-host setup diagnostics tests returning `NO_CONSOLE_HOST` in `tests/unit/test_cli_setup_missing_host.py`; Req: FR-011, FR-012, SC-003, SC-009; Depends: T007.

### Implementation for User Story 1

- [X] T020 [US1] Implement `m32-bridge setup` argument parsing and JSON output in `src/m32_bridge/cli.py`; Req: FR-001, FR-002, FR-013, FR-014, SC-004; Depends: T016, T017, T018, T019.
- [X] T021 [US1] Implement read-only setup `/info` probe flow using existing OSC read client in `src/m32_bridge/diagnostics/runtime.py`; Req: FR-003, FR-004, FR-043, SC-001, SC-003; Depends: T020.
- [X] T022 [US1] Implement save-confirmation and non-secret config persistence for setup in `src/m32_bridge/config/runtime.py`; Req: FR-005, FR-006, FR-007, FR-008, SC-005, SC-011; Depends: T020, T021.
- [X] T023 [US1] Integrate setup result classification and recommendations into `src/m32_bridge/cli.py`; Req: FR-012, FR-013, FR-040, FR-041, FR-042, SC-004, SC-005, SC-015; Depends: T021, T022.

**Checkpoint**: US1 is independently testable as the MVP setup flow.

---

## Phase 4: User Story 2 - Detect Target Type Without Overclaiming Hardware (Priority: P1)

**Goal**: `m32-bridge detect-device` classifies configured targets honestly, reports optional capability limits, and never treats emulator or connectivity alone as hardware verification.

**Independent Test**: Provide no config, wrong endpoint, emulator endpoint, partial endpoint, and fixture-based later hardware evidence; verify classification, safety flags, USB evidence, and zero writes.

### Tests for User Story 2

- [X] T024 [P] [US2] Add device classification tests for `NOT_CONFIGURED`, `EMULATOR_CONNECTED`, `CONNECTED_UNVERIFIED`, and `HARDWARE_CANDIDATE` in `tests/unit/test_device_detector.py`; Req: FR-030, FR-033, FR-034, FR-036, FR-041, FR-042, SC-002, SC-015; Depends: T011, T012.
- [X] T025 [P] [US2] Add fixture-only hardware evidence tests proving `HARDWARE_VERIFIED` requires later acceptance evidence and no real hardware write in `tests/hardware_acceptance/test_device_identity_classification.py`; Req: FR-037, FR-038, SC-015; Depends: T011.
- [X] T026 [P] [US2] Add optional capability limitation tests using object-shaped `unsupported_or_timeout_paths` in `tests/unit/test_device_detector_capabilities.py`; Req: FR-031, FR-032, SC-004; Depends: T008.
- [X] T027 [P] [US2] Add USB best-effort and non-blocking tests in `tests/cross_platform/test_usb_detection.py`; Req: FR-035, FR-039, SC-014; Depends: T011.
- [X] T028 [P] [US2] Add detect-device no-write tests in `tests/integration_fake_m32/test_detect_device_no_write.py`; Req: FR-031, FR-043, SC-001; Depends: T003.
- [X] T029 [P] [US2] Add external emulator read-only classification tests in `tests/integration_external_emulator/test_detect_device_read_only.py` that do not fail the gate for unsupported optional paths; Req: FR-030, FR-032, FR-034, SC-002; Depends: T024, T026.

### Implementation for User Story 2

- [X] T030 [US2] Implement `DeviceIdentityReport` and classification logic in `src/m32_bridge/diagnostics/device_identity.py`; Req: FR-030, FR-033, FR-034, FR-036, FR-037, FR-041, FR-042, SC-002, SC-015; Depends: T024, T025.
- [X] T031 [US2] Implement optional read capability mapping with structured `unsupported_or_timeout_paths` objects in `src/m32_bridge/diagnostics/device_identity.py`; Req: FR-031, FR-032, SC-004; Depends: T026, T030.
- [X] T032 [US2] Implement best-effort USB evidence collection with `usb_control_supported=false` by default in `src/m32_bridge/diagnostics/usb.py`; Req: FR-035, FR-039, SC-014; Depends: T027.
- [X] T033 [US2] Implement `m32-bridge detect-device --json` in `src/m32_bridge/cli.py`; Req: FR-013, FR-014, FR-030, FR-031, FR-043, SC-001, SC-004; Depends: T028, T030, T031, T032.
- [X] T034 [US2] Integrate emulator-vs-hardware safety flags into detection output in `src/m32_bridge/diagnostics/device_identity.py`; Req: FR-033, FR-034, FR-037, FR-038, FR-041, FR-042, SC-002, SC-015; Depends: T029, T033.

**Checkpoint**: US2 is independently testable through `m32-bridge detect-device --json`.

---

## Phase 5: User Story 3 - Use Local MCP Hosts Through Stdio Reliably (Priority: P1)

**Goal**: Local MCP hosts launch `m32-bridge mcp-server` over stdio with clean stdout, stderr logging, no network MCP port, and manual-copy snippets that omit host/port by default.

**Independent Test**: Start the MCP server locally, verify stdout protocol cleanliness, stderr logging, no local network MCP port, read-only diagnostics, and manual-copy MCP guidance.

### Tests for User Story 3

- [X] T035 [P] [US3] Add MCP stdio launcher tests for `m32-bridge mcp-server` in `tests/e2e_mcp/test_m32_bridge_launcher_stdio.py`, including a managed-environment launch such as `uv run m32-bridge health` or the project console script equivalent to prove the stable launcher works without global `py`; Req: FR-015, FR-016, FR-021, FR-022, FR-047, SC-006, SC-012; Depends: T013, T014.
- [X] T036 [P] [US3] Add stdout/stderr cleanliness tests for local MCP startup in `tests/e2e_mcp/test_stdio_clean_output.py`; Req: FR-021, FR-024, SC-012; Depends: T011.
- [X] T037 [P] [US3] Add no-network-port MCP startup tests in `tests/e2e_mcp/test_mcp_stdio_no_network_port.py`; Req: FR-023, FR-047, FR-048; Depends: T035.
- [X] T038 [P] [US3] Add manual-copy Claude/AI MCP snippet tests in `tests/unit/test_mcp_launch_guidance.py`; Req: FR-017, FR-018, FR-019, SC-006, SC-007, SC-008, SC-010; Depends: T011.
- [X] T039 [P] [US3] Add runtime dependency and launcher diagnostic tests for MCP startup failures in `tests/e2e_mcp/test_mcp_runtime_startup_diagnostics.py`; Req: FR-020, FR-021, SC-003, SC-004; Depends: T011, T012.

### Implementation for User Story 3

- [X] T040 [US3] Implement `m32-bridge mcp-server` CLI dispatch to the existing stdio MCP server in `src/m32_bridge/cli.py`; Req: FR-014, FR-021, FR-022, FR-047; Depends: T035.
- [X] T041 [US3] Ensure MCP stdio startup sends logs to stderr and protocol messages only to stdout in `src/m32_bridge/mcp/server.py`; Req: FR-024, SC-012; Depends: T036, T040.
- [X] T042 [US3] Ensure local stdio MCP mode opens no MCP network port by default in `src/m32_bridge/mcp/server.py`; Req: FR-023, FR-047, FR-048; Depends: T037, T041.
- [X] T043 [US3] Implement manual-copy MCP and Claude guidance output without embedded host/port by default in `src/m32_bridge/diagnostics/mcp_guidance.py`; Req: FR-017, FR-018, FR-019, SC-006, SC-007, SC-008, SC-010; Depends: T038.
- [X] T044 [US3] Integrate MCP runtime/dependency diagnostics into `src/m32_bridge/diagnostics/runtime.py`; Req: FR-020, SC-003, SC-004; Depends: T039, T043.

**Checkpoint**: US3 is independently testable through local stdio MCP startup and guidance output.

---

## Phase 6: User Story 4 - Inspect and Validate Local Configuration (Priority: P2)

**Goal**: Operators can inspect, validate, and edit non-secret config safely without changing console state or MCP host configuration files.

**Independent Test**: Show and validate valid, invalid, missing, and malformed config files and verify no secrets, no Claude config modification, and zero writes.

### Tests for User Story 4

- [X] T045 [P] [US4] Add `config show` tests for saved, missing, and malformed config in `tests/unit/test_cli_config_show.py`; Req: FR-013, FR-014, SC-003, SC-004, SC-005; Depends: T009, T011.
- [X] T046 [P] [US4] Add `config validate` tests for invalid host, invalid port, missing host, and source precedence in `tests/unit/test_cli_config_validate.py`; Req: FR-007, FR-008, FR-010, FR-011, FR-012, FR-013, FR-014, SC-003, SC-009, SC-011; Depends: T006, T007.
- [X] T047 [P] [US4] Add `config set` tests for user-editable host/port and no hardcoded production host in `tests/unit/test_cli_config_set.py`; Req: FR-007, FR-009, FR-010, FR-014, SC-010, SC-011; Depends: T009, T010.
- [X] T048 [P] [US4] Add config command no-write tests in `tests/integration_fake_m32/test_config_commands_no_write.py`; Req: FR-043, SC-001; Depends: T003.

### Implementation for User Story 4

- [X] T049 [US4] Implement `m32-bridge config show --json` in `src/m32_bridge/cli.py`; Req: FR-013, FR-014, SC-004, SC-005; Depends: T045.
- [X] T050 [US4] Implement `m32-bridge config validate --json` in `src/m32_bridge/cli.py`; Req: FR-007, FR-008, FR-010, FR-011, FR-012, FR-013, FR-014, SC-003, SC-009, SC-011; Depends: T046.
- [X] T051 [US4] Implement `m32-bridge config set --host <host> --port <port> --json` in `src/m32_bridge/cli.py`; Req: FR-007, FR-009, FR-010, FR-014, SC-010, SC-011; Depends: T047, T048.

**Checkpoint**: US4 is independently testable through config commands.

---

## Phase 7: User Story 5 - Receive OS-Aware Installation Guidance (Priority: P2)

**Goal**: Operators receive platform-aware setup recommendations without global Python assumptions, admin defaults, actual packaging, or USB autorun dependency.

**Independent Test**: Check macOS, Windows, Linux, and Raspberry Pi OS recommendation outputs for user-local defaults, optional admin cases, best-effort USB, and future-only packaging notes.

### Tests for User Story 5

- [X] T052 [P] [US5] Add OS recommendation tests for macOS, Windows, Linux, and Raspberry Pi OS in `tests/cross_platform/test_os_recommendations.py`; Req: FR-025, FR-026, FR-027, FR-028, FR-029, FR-050, FR-051, FR-052, SC-013; Depends: T011.
- [X] T053 [P] [US5] Add future packaging documentation boundary tests in `tests/unit/test_installation_strategy_scope.py`; Req: FR-045, FR-046, FR-048, FR-049, FR-063, SC-020; Depends: T011.
- [X] T054 [P] [US5] Add USB inspection failure recommendation tests in `tests/cross_platform/test_usb_recommendation_non_blocking.py`; Req: FR-039, FR-046, SC-014; Depends: T027.

### Implementation for User Story 5

- [X] T055 [US5] Implement OS recommendation model and renderer in `src/m32_bridge/diagnostics/os_recommendations.py`; Req: FR-025, FR-026, FR-027, FR-028, FR-029, FR-050, FR-051, FR-052, SC-013; Depends: T052.
- [X] T056 [US5] Implement future-only installation strategy guidance in `src/m32_bridge/diagnostics/os_recommendations.py`; Req: FR-045, FR-046, FR-048, FR-049, FR-063, SC-020; Depends: T053, T055.
- [X] T057 [US5] Integrate OS recommendations into setup, doctor-runtime, and detect-device outputs in `src/m32_bridge/cli.py`; Req: FR-013, FR-025, FR-039, SC-004, SC-013, SC-014; Depends: T054, T056.

**Checkpoint**: US5 is independently testable through recommendation output.

---

## Phase 8: User Story 6 - Use an Optional Interactive Shell (Priority: P2)

**Goal**: Running `m32-bridge` with no subcommand opens an optional slash-command shell only on TTY, while non-TTY launch returns structured help/error without hanging.

**Independent Test**: Launch the command with TTY and non-TTY stdin, run every slash command, verify CLI equivalents, zero writes, local-only lock/unlock, and unlock denial governance.

### Tests for User Story 6

- [X] T058 [P] [US6] Add non-interactive no-subcommand guard tests in `tests/unit/test_interactive_shell_non_tty.py`; Req: FR-054, FR-061, SC-004; Depends: T011.
- [X] T059 [P] [US6] Add interactive shell slash command parser tests in `tests/unit/test_interactive_shell_commands.py`; Req: FR-055, FR-056, FR-057, FR-060, SC-016, SC-017; Depends: T011.
- [X] T060 [P] [US6] Add slash read-only no-write tests for `/runsetup`, `/getinfo`, `/config`, `/test`, `/doctor`, and `/detect` in `tests/integration_fake_m32/test_shell_read_only_no_write.py`; Req: FR-058, SC-018; Depends: T003.
- [X] T061 [P] [US6] Add `/lock` and `/unlock` local-only no-write tests in `tests/unit/test_shell_lock_state.py`; Req: FR-059, SC-019; Depends: T003.
- [X] T062 [P] [US6] Add unlock governance denial tests for disconnected, stale, unreconciled, EMERGENCY, and policy-blocked states in `tests/unit/test_unlock_governance.py`; Req: FR-040, FR-044, FR-059, FR-062, SC-019; Depends: T011.
- [X] T063 [P] [US6] Add shell help tests proving slash commands are documented as shell-only in `tests/unit/test_shell_help_text.py`; Req: FR-056, FR-057, SC-016, SC-017; Depends: T059.

### Implementation for User Story 6

- [X] T064 [US6] Implement no-subcommand TTY detection and non-TTY structured response in `src/m32_bridge/cli.py`; Req: FR-054, FR-061, SC-004; Depends: T058.
- [X] T065 [US6] Implement interactive shell command loop and slash command dispatch in `src/m32_bridge/interactive_shell.py`; Req: FR-054, FR-055, FR-056, FR-057, FR-060, SC-016, SC-017; Depends: T059, T064.
- [X] T066 [US6] Map read-only slash commands to existing CLI service functions without OSC writes in `src/m32_bridge/interactive_shell.py`; Req: FR-058, SC-018; Depends: T060, T065.
- [X] T067 [US6] Implement local write-lock state display and `/lock` handling in `src/m32_bridge/interactive_shell.py`; Req: FR-059, SC-019; Depends: T061, T065.
- [X] T068 [US6] Implement `/unlock` governance checks in `src/m32_bridge/interactive_shell.py` using existing status, reconciliation, runtime mode, EMERGENCY, and governance signals without changing policy files; Req: FR-040, FR-044, FR-059, FR-062, SC-019; Depends: T062, T067.
- [X] T069 [US6] Implement `/mcp` and `/claude` shell guidance as manual-copy output only in `src/m32_bridge/interactive_shell.py`; Req: FR-017, FR-018, FR-019, FR-055, SC-006, SC-007, SC-008, SC-010; Depends: T043, T065.
- [X] T070 [US6] Implement shell-only help text and `/exit` behavior in `src/m32_bridge/interactive_shell.py`; Req: FR-055, FR-056, FR-057, SC-016, SC-017; Depends: T063, T065.

**Checkpoint**: US6 is independently testable through interactive shell and non-TTY launches.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Validate the whole feature against contracts, documentation, and safety boundaries.

- [X] T071 [P] Validate all runtime JSON outputs against `specs/002-local-runtime-setup-and-device-verification/contracts/runtime-output.schema.json` in `tests/unit/test_runtime_output_schema.py`; Req: FR-013, SC-004; Depends: T020, T033, T049, T050, T051, T057, T064.
- [X] T072 [P] Add quickstart drift checks for slash-command shell-only wording and future-only packaging notes in `tests/unit/test_quickstart_runtime_setup_docs.py`; Req: FR-045, FR-046, FR-056, FR-063, SC-016, SC-020; Depends: T056, T070.
- [X] T073 Update `specs/002-local-runtime-setup-and-device-verification/quickstart.md` only if implementation changes command wording or validation steps while preserving future-only packaging scope; Req: FR-045, FR-056, FR-063, SC-016, SC-020; Depends: T071, T072.
- [X] T074 Run focused unit/property/e2e/fake/cross-platform/hardware-acceptance non-write validation commands plus the external emulator read-only subset only, excluding external safe-write tests and any `/set` or state-changing OSC writes, and record failures in `specs/002-local-runtime-setup-and-device-verification/quickstart.md` if documentation updates are needed; Req: SC-001, SC-002, SC-003, SC-004, SC-012, SC-013, SC-014, SC-015, SC-020; Depends: T071, T072, T073.
- [X] T075 Re-run the safety inventory regression in `tests/unit/test_runtime_feature_scope_guard.py` and confirm no source file exposes raw OSC, arbitrary path, shell, firmware, shutdown, phantom, sample-rate, clock, approval-token, WebUI, database, service, remote MCP, or ChatGPT tunnel behavior; Req: FR-044, FR-048, FR-049, FR-052, FR-053, FR-060, FR-063, SC-020; Depends: T015, T074.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1.
- **US1 Configure Runtime**: Depends on Phase 2.
- **US2 Detect Device**: Depends on Phase 2 and can run alongside US1 after shared config/output foundations are ready.
- **US3 MCP Stdio**: Depends on Phase 2 and stable launcher tasks; can run alongside US1/US2 after T013 and T014.
- **US4 Config Inspection**: Depends on Phase 2 and can run after config foundations are complete.
- **US5 OS Guidance**: Depends on Phase 2 and USB model tests; can run alongside US4.
- **US6 Interactive Shell**: Depends on Phase 2 and integrates outputs from US1, US3, US4, and US5 for shell mappings.
- **Final Phase**: Depends on selected user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Foundation only; suggested MVP.
- **US2 (P1)**: Foundation only for core classification; external emulator test depends on capability test scaffolding.
- **US3 (P1)**: Foundation plus stable launcher.
- **US4 (P2)**: Foundation config model.
- **US5 (P2)**: Foundation output model and USB evidence model.
- **US6 (P2)**: Foundation plus CLI command service mappings; `/mcp` and `/claude` depend on US3 guidance.

### Gates

- **No-write gate**: T003, T018, T028, T048, T060, T061, and T075 must prove or preserve zero OSC writes.
- **Schema gate**: T008 and T071 must validate JSON outputs against `runtime-output.schema.json`.
- **Missing-host gate**: T007 and T019 must prove `NO_CONSOLE_HOST` without guessing or scanning.
- **MCP stdio gate**: T035, T036, T037, T040, T041, and T042 must prove stdout cleanliness, stderr logging, and no network MCP port.
- **Unlock governance gate**: T062, T068, and T075 must prove unlock denial for disconnected, stale, unreconciled, EMERGENCY, and policy-blocked states.
- **Hardware honesty gate**: T024, T025, T030, T034, and T075 must prevent emulator/Fake/OSC/USB evidence from claiming production readiness or hardware verification.

---

## Parallel Opportunities

- **Setup**: T002, T003, and T004 can run in parallel after T001 is understood.
- **Foundational tests**: T005, T006, T007, T008, and T015 can run in parallel.
- **US1 tests**: T016, T017, T018, and T019 can run in parallel.
- **US2 tests**: T024, T025, T026, T027, T028, and T029 can run in parallel where their listed dependencies are satisfied.
- **US3 tests**: T035, T036, T037, T038, and T039 can run in parallel where their listed dependencies are satisfied.
- **US4 tests**: T045, T046, T047, and T048 can run in parallel.
- **US5 tests**: T052, T053, and T054 can run in parallel.
- **US6 tests**: T058, T059, T060, T061, T062, and T063 can run in parallel.
- **Polish checks**: T071 and T072 can run in parallel before documentation reconciliation.

## Parallel Example: User Story 2

```text
Task: T024 Add device classification tests in tests/unit/test_device_detector.py
Task: T026 Add optional capability limitation tests in tests/unit/test_device_detector_capabilities.py
Task: T027 Add USB best-effort tests in tests/cross_platform/test_usb_detection.py
Task: T028 Add detect-device no-write tests in tests/integration_fake_m32/test_detect_device_no_write.py
```

## Parallel Example: User Story 6

```text
Task: T058 Add non-interactive no-subcommand guard tests in tests/unit/test_interactive_shell_non_tty.py
Task: T059 Add shell command parser tests in tests/unit/test_interactive_shell_commands.py
Task: T060 Add shell read-only no-write tests in tests/integration_fake_m32/test_shell_read_only_no_write.py
Task: T062 Add unlock governance denial tests in tests/unit/test_unlock_governance.py
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 only.
3. Stop and validate setup no-write behavior, config save path, `/info` only, `NO_CONSOLE_HOST`, JSON output, and `m32-bridge` launcher.

### Incremental Delivery

1. US1: safe local setup and `/info`.
2. US2: honest device classification and USB evidence.
3. US3: local stdio MCP launcher and manual-copy guidance.
4. US4: config inspection and validation.
5. US5: OS-aware recommendations and future packaging documentation.
6. US6: optional interactive shell and unlock governance.

### Safety Rule

Any implementation task that appears to require changes to executor, rollback, proposals, policy, write tools, EMERGENCY behavior, real hardware write tests, WebUI, database, backend service, microservice architecture, actual installer/package implementation, remote MCP, ChatGPT tunnel implementation, or automatic Claude config editing is out of scope and must stop for review before code changes.
