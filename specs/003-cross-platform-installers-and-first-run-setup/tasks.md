# Tasks: Cross-Platform Installers and First-Run Setup

**Input**: Design documents from `specs/003-cross-platform-installers-and-first-run-setup/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/installer-contract.md`, `contracts/installer-output.schema.json`, `contracts/mcp-guidance-contract.md`, `quickstart.md`

**Tests**: Required by the user request, plan test strategy, contracts, and constitution quality gates. Tests must be written before implementation within each slice.

**Organization**: Tasks are grouped by setup/foundational work, then user stories in priority order, then final safety and documentation gates.

**Scope Guard**: Do not modify `src/m32_bridge/core/executor.py`, `src/m32_bridge/core/rollback.py`, `src/m32_bridge/core/proposals.py`, or `src/m32_bridge/core/policy.py`. No task may add binary installers, signed releases, WebUI, database, backend service, microservices, remote/cloud MCP, ChatGPT tunnel, automatic Claude config editing, real hardware writes, production/live readiness claims, emulator-based hardware verification, admin-by-default behavior, or MCP shell execution surfaces.

---

## Phase 1: Setup and Contract Baseline

**Purpose**: Establish contract validation and scope guards before installer work.

- [X] T001 Add installer output schema validation tests for valid minimal output, optional metadata fields, rejected extra properties, and safety constants in `tests/unit/test_installer_output_schema.py`; Req: FR-004, FR-006, FR-017, FR-028, FR-029, FR-035, SC-002, SC-003, SC-006, SC-007, SC-008; Depends: None.
- [X] T002 [P] Add installer contract drift tests for user-local paths, no-admin defaults, runtime manager guidance, idempotency states, first-run setup, and safer install UX in `tests/unit/test_installer_contract_docs.py`; Req: FR-001, FR-002, FR-003, FR-004, FR-007, FR-010, FR-011, FR-013, FR-033, SC-001, SC-002, SC-008, SC-012; Depends: None.
- [X] T003 [P] Add MCP guidance contract drift tests for manual-copy snippets, `m32-bridge mcp-server`, no embedded host/port, advanced override labelling, and no Claude auto-write in `tests/unit/test_installer_mcp_guidance_contract.py`; Req: FR-023, FR-024, FR-025, FR-026, FR-027, SC-010; Depends: None.
- [X] T004 [P] Add installer feature scope guard tests proving no binary installer artifacts, WebUI, DB, backend service, microservice, remote MCP, ChatGPT tunnel, admin-by-default, raw OSC, arbitrary path, shell execution, or Claude config auto-write surfaces are introduced in `tests/unit/test_installer_feature_scope_guard.py`; Req: FR-017, FR-023, FR-027, FR-028, FR-029, FR-034, SC-006, SC-007, SC-013; Depends: None.
- [X] T005 Add test helper fixtures for isolated user-local install homes, Windows local-app-data paths, POSIX home paths, and dry-run capture in `tests/unit/installer_test_helpers.py`; Req: FR-004, FR-010, FR-011, FR-035, SC-002, SC-008; Depends: T001.
- [X] T006 Add design-only placeholder package boundary tests proving future installer helpers can be imported without executing installers or sending OSC writes in `tests/unit/test_installer_module_boundaries.py`; Req: FR-017, FR-028, FR-029, SC-006, SC-007; Depends: T004, T005.

**Checkpoint**: Contract baseline ready; source implementation can start only after these tests exist.

---

## Phase 2: Foundational Installer Models and Shared Helpers

**Purpose**: Shared implementation primitives required by POSIX, Windows, first-run setup, lifecycle, and guidance slices.

- [X] T007 Implement installer output envelope builder with `osc_writes_sent=0`, `hardware_verified=false`, `production_live_ready=false`, optional metadata fields, and schema-compatible status values in `src/m32_bridge/installer/output.py`; Req: FR-017, FR-028, FR-029, FR-035, SC-006, SC-007, SC-008; Depends: T001.
- [X] T008 Implement installation target model for macOS, Linux, WSL, Windows PowerShell, Windows CMD launcher usage, Raspberry Pi OS, architecture, shell, and interactivity evidence in `src/m32_bridge/installer/platforms.py`; Req: FR-005, FR-030, FR-031, FR-032, SC-008, SC-009; Depends: T005.
- [X] T009 Implement user-local install path calculation for POSIX and Windows app/launcher locations without admin defaults in `src/m32_bridge/installer/paths.py`; Req: FR-004, FR-010, FR-011, FR-012, SC-002, SC-012; Depends: T005.
- [X] T010 Implement runtime manager status model for `uv` present, user-local installed, blocked, and manual-action-required states without global `py` assumptions in `src/m32_bridge/installer/runtime_manager.py`; Req: FR-006, FR-007, FR-030, FR-035, SC-003, SC-008; Depends: T007.
- [X] T011 Implement install state model for `fresh_install`, `existing_install`, `repair`, `update`, `already_current`, `partial_failure`, and `failed` without deleting saved config by default in `src/m32_bridge/installer/state.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T007, T009.
- [X] T012 Implement dry-run planner that reports intended app, launcher, runtime, PATH, setup, and lifecycle actions without writing files or contacting consoles in `src/m32_bridge/installer/planner.py`; Req: FR-004, FR-006, FR-007, FR-017, FR-035, SC-002, SC-003, SC-006, SC-008; Depends: T008, T009, T010, T011.
- [X] T013 Add CLI-accessible installer status/dry-run service boundary without creating binary installers or changing existing write tools in `src/m32_bridge/installer/service.py`; Req: FR-001, FR-002, FR-008, FR-017, FR-028, FR-029, SC-006, SC-007; Depends: T012.

**Checkpoint**: Shared installer primitives ready; user story work may proceed in priority order.

---

## Phase 3: User Story 1 - Install with a User-Local Script (Priority: P1) MVP

**Goal**: A user can perform a user-local script install on supported OS families and get a stable `m32-bridge` launcher without admin privileges or global `py`.

**Independent Test**: From isolated user-local paths, run POSIX and PowerShell dry-run/contract tests and verify app paths, launcher paths, runtime manager guidance, idempotency status, and `m32-bridge health` launcher expectations.

### Tests for User Story 1

- [X] T014 [P] [US1] Add POSIX installer dry-run contract tests for macOS, Linux, WSL, and Raspberry Pi OS in `tests/cross_platform/test_posix_installer_dry_run.py`; Req: FR-001, FR-004, FR-005, FR-010, FR-012, FR-031, FR-032, SC-001, SC-002, SC-009; Depends: T005, T008, T009.
- [X] T015 [P] [US1] Add POSIX installer no-admin and no-global-py tests in `tests/unit/test_posix_installer_runtime_manager.py`; Req: FR-004, FR-006, FR-007, FR-030, FR-035, SC-002, SC-003, SC-008; Depends: T005, T010.
- [X] T016 [P] [US1] Add POSIX installer idempotency tests for fresh install, existing install, repair, update, already current, partial failure, and failed states in `tests/unit/test_posix_installer_idempotency.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T005, T011.
- [X] T017 [P] [US1] Add POSIX launcher availability tests proving `~/.local/bin/m32-bridge` can dispatch `m32-bridge health` without global `py` in `tests/cross_platform/test_posix_launcher_contract.py`; Req: FR-008, FR-009, FR-010, FR-022, SC-001, SC-003; Depends: T005, T009.
- [X] T018 [P] [US1] Add Windows PowerShell installer static and dry-run contract tests in `tests/cross_platform/test_windows_installer_dry_run.py`; Req: FR-002, FR-004, FR-005, FR-011, FR-030, SC-001, SC-002, SC-008; Depends: T005, T008, T009.
- [X] T019 [P] [US1] Add Windows CMD launcher creation tests for `%LOCALAPPDATA%\\M32Bridge\\bin\\m32-bridge.cmd` in `tests/cross_platform/test_windows_cmd_launcher_contract.py`; Req: FR-008, FR-009, FR-011, FR-022, SC-001, SC-003; Depends: T005, T009.
- [X] T020 [P] [US1] Add Windows runtime manager and PowerShell execution-policy guidance tests in `tests/unit/test_windows_installer_runtime_manager.py`; Req: FR-004, FR-006, FR-007, FR-030, FR-035, SC-002, SC-003, SC-008; Depends: T005, T010.
- [X] T021 [P] [US1] Add Windows installer idempotency tests for fresh install, existing install, repair, update, already current, partial failure, and failed states in `tests/unit/test_windows_installer_idempotency.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T005, T011.

### Implementation for User Story 1

- [X] T022 [US1] Create future POSIX installer script surface with dry-run, user-local path planning, OS detection, runtime manager guidance, and no-admin defaults in `scripts/install.sh`; Req: FR-001, FR-004, FR-005, FR-006, FR-007, FR-010, FR-012, FR-030, FR-031, FR-032, FR-035, SC-001, SC-002, SC-003, SC-008, SC-009; Depends: T014, T015, T016, T017.
- [X] T023 [US1] Wire POSIX installer script to shared installer planner and output envelope without console contact or OSC writes in `scripts/install.sh`; Req: FR-017, FR-028, FR-029, FR-035, SC-006, SC-007, SC-008; Depends: T022, T012, T013.
- [X] T024 [US1] Create future Windows PowerShell installer script surface with dry-run, user-local path planning, runtime manager guidance, execution-policy guidance, and no-admin defaults in `scripts/install.ps1`; Req: FR-002, FR-004, FR-005, FR-006, FR-007, FR-011, FR-030, FR-035, SC-001, SC-002, SC-003, SC-008; Depends: T018, T020, T021.
- [X] T025 [US1] Implement CMD-compatible launcher generation planning for `%LOCALAPPDATA%\\M32Bridge\\bin\\m32-bridge.cmd` without global `py` in `scripts/install.ps1`; Req: FR-008, FR-009, FR-011, FR-022, SC-001, SC-003; Depends: T019, T024.
- [X] T026 [US1] Wire Windows installer script to shared installer planner and output envelope without console contact or OSC writes in `scripts/install.ps1`; Req: FR-017, FR-028, FR-029, FR-035, SC-006, SC-007, SC-008; Depends: T024, T025, T012, T013.
- [X] T027 [US1] Implement idempotency state detection and recovery messaging for POSIX and Windows installer surfaces in `src/m32_bridge/installer/state.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T016, T021, T011, T023, T026.
- [X] T028 [US1] Implement PATH visibility and new-terminal guidance for POSIX shell profiles and Windows user PATH without requiring admin privileges in `src/m32_bridge/installer/paths.py`; Req: FR-004, FR-010, FR-011, FR-030, FR-033, SC-002, SC-008, SC-012; Depends: T017, T019, T009.
- [X] T029 [US1] Run focused US1 validation commands for installer contract, POSIX dry-run, Windows dry-run, launcher, runtime manager, and idempotency tests, recording failures without running binary packaging or hardware tests in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-001, FR-002, FR-004, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-030, FR-031, FR-032, FR-033, FR-035, SC-001, SC-002, SC-003, SC-008, SC-009, SC-012; Depends: T022, T023, T024, T025, T026, T027, T028.

**Checkpoint**: US1 provides script-first installation MVP without admin-by-default, global `py`, binary packages, or hardware claims.

---

## Phase 4: User Story 2 - Complete First-Run Setup During Installation (Priority: P1)

**Goal**: After install, interactive users can complete safe first-run setup and non-interactive environments get structured no-hang guidance.

**Independent Test**: Run installer setup tests in TTY and non-TTY modes and verify host/port/label/target prompts, `/info` only, no `/set`, classification display, save confirmation, `osc_writes_sent=0`, and emulator `hardware_verified=false`.

### Tests for User Story 2

- [X] T030 [P] [US2] Add first-run TTY prompt contract tests for detected OS, recommended mode, host, port default `10023`, label/environment, and intended target type in `tests/unit/test_installer_first_run_tty.py`; Req: FR-013, FR-014, FR-015, SC-004; Depends: T013.
- [X] T031 [P] [US2] Add non-TTY no-hang structured output tests for installer-triggered setup in `tests/unit/test_installer_first_run_non_tty.py`; Req: FR-020, FR-021, FR-035, SC-005, SC-008; Depends: T013.
- [X] T032 [P] [US2] Add first-run setup no-write tests proving `/info` only, no `/set`, and `osc_writes_sent=0` in `tests/integration_fake_m32/test_installer_first_run_no_write.py`; Req: FR-016, FR-017, SC-006; Depends: T005.
- [X] T033 [P] [US2] Add first-run classification and emulator honesty tests proving emulator output keeps `hardware_verified=false` and `production_live_ready=false` in `tests/unit/test_installer_first_run_classification.py`; Req: FR-018, FR-028, FR-029, SC-007; Depends: T007.
- [X] T034 [P] [US2] Add setup save confirmation tests proving config is saved only after explicit confirmation and existing config is not overwritten silently in `tests/unit/test_installer_first_run_save_confirmation.py`; Req: FR-019, FR-033, SC-011, SC-012; Depends: T005.

### Implementation for User Story 2

- [X] T035 [US2] Implement first-run setup orchestration service that offers setup only in interactive terminals and delegates to existing safe setup behavior in `src/m32_bridge/installer/first_run.py`; Req: FR-013, FR-014, FR-015, FR-016, FR-017, SC-004, SC-006; Depends: T030, T032.
- [X] T036 [US2] Implement non-TTY no-hang setup output and automation guidance in `src/m32_bridge/installer/first_run.py`; Req: FR-020, FR-021, FR-035, SC-005, SC-008; Depends: T031, T035.
- [X] T037 [US2] Implement classification display mapping for setup results without hardware verification or production readiness claims in `src/m32_bridge/installer/first_run.py`; Req: FR-018, FR-028, FR-029, SC-007; Depends: T033, T035.
- [X] T038 [US2] Implement save-after-confirmation integration with existing user-local config behavior in `src/m32_bridge/installer/first_run.py`; Req: FR-019, FR-033, SC-011, SC-012; Depends: T034, T035.
- [X] T039 [US2] Wire POSIX and Windows installer surfaces to offer first-run setup after successful install while preserving dry-run and non-TTY behavior in `scripts/install.sh` and `scripts/install.ps1`; Req: FR-013, FR-020, FR-021, FR-035, SC-004, SC-005, SC-008; Depends: T035, T036, T037, T038.
- [X] T040 [US2] Run focused US2 validation for first-run TTY, non-TTY, no-write, classification, and save-confirmation tests without external safe-write or real hardware tests in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-028, FR-029, FR-035, SC-004, SC-005, SC-006, SC-007, SC-008, SC-011; Depends: T035, T036, T037, T038, T039.

**Checkpoint**: US2 completes safe first-run setup integration without `/set`, scanning, hardware claims, or non-TTY hangs.

---

## Phase 5: User Story 3 - Verify the Installed Runtime (Priority: P2)

**Goal**: A user can run post-install verification commands and get clear no-write results.

**Independent Test**: Run post-install command guidance and command smoke tests for `health`, `setup`, `get-info`, `detect-device`, and `doctor-runtime`, including missing-host and emulator-safe behavior.

### Tests for User Story 3

- [X] T041 [P] [US3] Add post-install verification guidance tests for `m32-bridge health`, `m32-bridge setup`, `m32-bridge get-info`, `m32-bridge detect-device`, and `m32-bridge doctor-runtime` in `tests/unit/test_installer_verification_guidance.py`; Req: FR-022, SC-001, SC-011; Depends: T013.
- [X] T042 [P] [US3] Add installed launcher verification tests proving `m32-bridge health` works through planned POSIX and Windows launchers without console connectivity in `tests/e2e_mcp/test_installed_launcher_health.py`; Req: FR-008, FR-009, FR-022, SC-001, SC-003; Depends: T017, T019.
- [X] T043 [P] [US3] Add post-install no-write tests for `setup`, `get-info`, `detect-device`, and `doctor-runtime` in `tests/integration_fake_m32/test_installer_verification_no_write.py`; Req: FR-016, FR-017, FR-022, SC-006; Depends: T005.
- [X] T044 [P] [US3] Add missing-host post-install verification tests proving setup guidance is returned without guessing or scanning in `tests/unit/test_installer_verification_missing_host.py`; Req: FR-020, FR-021, FR-022, FR-035, SC-005, SC-008; Depends: T007.
- [X] T045 [P] [US3] Add emulator honesty verification tests proving `detect-device` and setup-linked outputs never set `hardware_verified=true` or `production_live_ready=true` in `tests/unit/test_installer_verification_emulator_honesty.py`; Req: FR-018, FR-028, FR-029, SC-007; Depends: T007.

### Implementation for User Story 3

- [X] T046 [US3] Implement post-install verification guidance renderer with the five required commands in `src/m32_bridge/installer/verification.py`; Req: FR-022, SC-001, SC-011; Depends: T041.
- [X] T047 [US3] Integrate verification guidance into POSIX and Windows installer success outputs in `scripts/install.sh` and `scripts/install.ps1`; Req: FR-022, FR-035, SC-001, SC-008; Depends: T046, T023, T026.
- [X] T048 [US3] Implement installed launcher verification metadata for POSIX and Windows launchers without global `py` assumptions in `src/m32_bridge/installer/verification.py`; Req: FR-008, FR-009, FR-022, SC-001, SC-003; Depends: T042, T046.
- [X] T049 [US3] Ensure post-install verification outputs preserve zero-write and conservative hardware readiness flags in `src/m32_bridge/installer/verification.py`; Req: FR-017, FR-028, FR-029, SC-006, SC-007; Depends: T043, T045, T046.
- [X] T050 [US3] Run focused US3 validation for verification guidance, launcher health, no-write checks, missing-host behavior, and emulator honesty in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-008, FR-009, FR-016, FR-017, FR-018, FR-020, FR-021, FR-022, FR-028, FR-029, FR-035, SC-001, SC-003, SC-005, SC-006, SC-007, SC-008, SC-011; Depends: T047, T048, T049.

**Checkpoint**: US3 gives a complete no-write post-install runtime verification path.

---

## Phase 6: User Story 4 - Configure Claude or Other Local MCP Hosts Manually (Priority: P2)

**Goal**: A user can copy safe local stdio MCP snippets using `m32-bridge mcp-server` without automatic host config edits.

**Independent Test**: Inspect MCP guidance output and verify manual-copy wording, default no host/port embedding, advanced override labels, and no forbidden MCP surfaces.

### Tests for User Story 4

- [X] T051 [P] [US4] Add installer MCP guidance snippet tests for `m32-bridge mcp-server`, manual-copy wording, and no default host/port embedding in `tests/unit/test_installer_mcp_guidance.py`; Req: FR-023, FR-024, FR-025, SC-010; Depends: T003.
- [X] T052 [P] [US4] Add advanced environment override labelling tests for host/port examples in installer MCP guidance in `tests/unit/test_installer_mcp_advanced_overrides.py`; Req: FR-026, SC-010; Depends: T003.
- [X] T053 [P] [US4] Add no Claude config auto-write regression tests for installer MCP guidance in `tests/unit/test_installer_mcp_no_auto_config_write.py`; Req: FR-023, FR-027, SC-010; Depends: T004.
- [X] T054 [P] [US4] Add MCP forbidden-surface regression tests proving no raw OSC, arbitrary path, shell execution, firmware, shutdown, phantom, sample-rate, clock, remote MCP, or ChatGPT tunnel is added in `tests/unit/test_installer_mcp_forbidden_surfaces.py`; Req: FR-027, FR-034, SC-006, SC-013; Depends: T004.

### Implementation for User Story 4

- [X] T055 [US4] Implement installer MCP guidance renderer using `m32-bridge mcp-server` and manual-copy-only wording in `src/m32_bridge/installer/mcp_guidance.py`; Req: FR-023, FR-024, FR-025, SC-010; Depends: T051.
- [X] T056 [US4] Implement advanced/manual host and port override examples with clear labels in `src/m32_bridge/installer/mcp_guidance.py`; Req: FR-026, SC-010; Depends: T052, T055.
- [X] T057 [US4] Integrate MCP guidance into installer success and post-install guidance without writing Claude config in `scripts/install.sh` and `scripts/install.ps1`; Req: FR-023, FR-024, FR-025, FR-026, FR-027, SC-010; Depends: T053, T055, T056.
- [X] T058 [US4] Run focused US4 validation for MCP guidance snippets, advanced override labelling, no auto config write, and forbidden MCP surfaces in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-023, FR-024, FR-025, FR-026, FR-027, FR-034, SC-010, SC-013; Depends: T054, T057.

**Checkpoint**: US4 delivers safe manual-copy MCP guidance only.

---

## Phase 7: User Story 5 - Maintain or Remove the User-Local Install (Priority: P3)

**Goal**: A user can update, repair, or uninstall the user-local installation with clear config retention/removal and PATH guidance.

**Independent Test**: Run lifecycle guidance and dry-run tests for update, repair, uninstall, partial failure recovery, config retention/removal choices, and future-only packaging documentation.

### Tests for User Story 5

- [X] T059 [P] [US5] Add lifecycle guidance tests for update, repair, uninstall, app path, launcher path, config retention/removal choices, and PATH/new-terminal guidance in `tests/unit/test_installer_lifecycle_guidance.py`; Req: FR-033, SC-012; Depends: T011.
- [X] T060 [P] [US5] Add partial failure recovery tests proving failed installs do not claim success and provide actionable recovery in `tests/unit/test_installer_partial_failure_recovery.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T011.
- [X] T061 [P] [US5] Add future-only packaging docs tests for `.exe`, `.msi`, `.app`, `.pkg`, `.dmg`, `.deb`, `.rpm`, AppImage, Raspberry Pi service/image, Claude `.mcpb`, Claude `.dxt`, USB portable kit, signing, checksums, and GitHub Releases in `tests/unit/test_installer_future_packaging_docs.py`; Req: FR-012, FR-034, SC-013; Depends: T002.
- [X] T062 [P] [US5] Add install command UX docs tests proving download-inspect-run is recommended and `curl | sh` or `irm | iex` are convenience-only in `tests/unit/test_installer_command_ux_docs.py`; Req: FR-003, SC-008; Depends: T002.

### Implementation for User Story 5

- [X] T063 [US5] Implement lifecycle guidance renderer for update, repair, uninstall, app path, launcher path, config retention/removal choices, and PATH/new-terminal guidance in `src/m32_bridge/installer/lifecycle.py`; Req: FR-033, SC-012; Depends: T059.
- [X] T064 [US5] Implement partial failure recovery messaging in lifecycle and installer output flows without silent success in `src/m32_bridge/installer/lifecycle.py`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T060, T063.
- [X] T065 [US5] Update `quickstart.md` future-only packaging validation notes without adding binary installer implementation in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-034, SC-013; Depends: T061.
- [X] T066 [US5] Update installer command UX validation notes to keep download-inspect-run recommended and one-liners convenience-only in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-003, SC-008; Depends: T062.
- [X] T067 [US5] Integrate lifecycle guidance into POSIX and Windows installer dry-run/success/failure outputs in `scripts/install.sh` and `scripts/install.ps1`; Req: FR-033, FR-035, SC-008, SC-012; Depends: T063, T064.
- [X] T068 [US5] Run focused US5 validation for lifecycle guidance, partial failure recovery, install command UX, and future-only packaging docs in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-003, FR-012, FR-033, FR-034, FR-035, SC-008, SC-012, SC-013; Depends: T065, T066, T067.

**Checkpoint**: US5 provides lifecycle clarity while keeping binary packaging future-only.

---

## Final Phase: Safety, Cross-Platform Gates, and Release Readiness Boundaries

**Purpose**: Validate the entire feature against contracts, safety boundaries, no-write guarantees, and future-only packaging scope.

- [X] T069 Add whole-feature installer output schema regression covering representative POSIX, Windows, setup-required, failed, and partial-failure outputs in `tests/unit/test_installer_output_schema.py`; Req: FR-004, FR-006, FR-017, FR-028, FR-029, FR-030, FR-035, SC-002, SC-003, SC-006, SC-007, SC-008; Depends: T029, T040, T050, T058, T068.
- [X] T070 [P] Add whole-feature safety inventory regression proving no OSC writes during install/setup/detect/verification, no production readiness claim, no emulator hardware verification, no admin default, no MCP shell execution, and no remote/cloud MCP in `tests/unit/test_installer_feature_scope_guard.py`; Req: FR-017, FR-027, FR-028, FR-029, FR-034, SC-006, SC-007, SC-013; Depends: T029, T040, T050, T058, T068.
- [X] T071 [P] Add cross-platform final gate tests for macOS, Linux, WSL, Windows PowerShell, Windows CMD launcher, and Raspberry Pi OS installer behavior in `tests/cross_platform/test_installer_cross_platform_gate.py`; Req: FR-001, FR-002, FR-004, FR-005, FR-010, FR-011, FR-012, FR-030, FR-031, FR-032, SC-001, SC-002, SC-008, SC-009; Depends: T029, T050, T068.
- [X] T072 [P] Add documentation drift tests proving `spec.md`, `plan.md`, `research.md`, `data-model.md`, contracts, and `quickstart.md` remain aligned on idempotency, safer install UX, no-admin defaults, no global `py`, no writes, and future-only packaging in `tests/unit/test_installer_docs_drift.py`; Req: FR-003, FR-004, FR-006, FR-017, FR-033, FR-034, SC-002, SC-003, SC-006, SC-012, SC-013; Depends: T068.
- [X] T073 Run focused unit, cross-platform, e2e MCP, and fake integration validation commands for this feature only, excluding binary installer generation, external safe-write tests, and real hardware write tests, and record results in `specs/003-cross-platform-installers-and-first-run-setup/quickstart.md`; Req: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-022, FR-023, FR-024, FR-025, FR-026, FR-027, FR-028, FR-029, FR-030, FR-031, FR-032, FR-033, FR-034, FR-035, SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011, SC-012, SC-013; Depends: T069, T070, T071, T072.
- [X] T074 Re-run final safety and future-only packaging gates proving no binary installers, signed releases, WebUI, database, backend service, microservice, remote MCP, ChatGPT tunnel, Claude auto-config edit, real hardware write, production/live readiness, or emulator hardware verification was added in `tests/unit/test_installer_feature_scope_guard.py`; Req: FR-017, FR-023, FR-027, FR-028, FR-029, FR-034, SC-006, SC-007, SC-010, SC-013; Depends: T073.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 has no dependencies and establishes contract tests.
- Phase 2 depends on Phase 1 and blocks all user stories.
- US1 depends on Phase 2 and is the MVP slice.
- US2 depends on US1 installer surfaces and Phase 2 first-run boundaries.
- US3 depends on US1 and US2 for installed launcher and setup outputs.
- US4 depends on Phase 2 and can proceed after US1, but final installer integration depends on installer surfaces.
- US5 depends on US1 idempotency and lifecycle state work.
- Final Phase depends on US1, US2, US3, US4, and US5.

### User Story Dependencies

- US1: Depends on Phase 2 only.
- US2: Depends on US1 installer surfaces and Phase 2 setup boundaries.
- US3: Depends on US1 launcher behavior and US2 setup behavior.
- US4: Depends on Phase 2 and integrates after US1 installer outputs exist.
- US5: Depends on US1 idempotency and shared lifecycle state.

### Important Gates

- No implementation task may run before its related tests are added.
- Installer scripts must be idempotent before final validation.
- `scripts/install.sh` and `scripts/install.ps1` must remain script installers only, not binary installers.
- No test or task may treat emulator, Fake M32, install success, or `/info` connectivity as hardware verification.
- No task may require admin privileges by default.
- No task may run real hardware write tests or external safe-write tests.

---

## Parallel Opportunities

- T002, T003, T004 can run in parallel after T001 is planned because they touch different test files.
- T014, T015, T016, T017, T018, T019, T020, T021 can run in parallel after foundational helpers exist.
- T030, T031, T032, T033, T034 can run in parallel for US2 tests.
- T041, T042, T043, T044, T045 can run in parallel for US3 tests.
- T051, T052, T053, T054 can run in parallel for US4 tests.
- T059, T060, T061, T062 can run in parallel for US5 tests.
- T070, T071, T072 can run in parallel after all user story checkpoints complete.

---

## Parallel Example: User Story 1

```text
Task: "T014 Add POSIX installer dry-run contract tests in tests/cross_platform/test_posix_installer_dry_run.py"
Task: "T018 Add Windows PowerShell installer static and dry-run contract tests in tests/cross_platform/test_windows_installer_dry_run.py"
Task: "T016 Add POSIX installer idempotency tests in tests/unit/test_posix_installer_idempotency.py"
Task: "T021 Add Windows installer idempotency tests in tests/unit/test_windows_installer_idempotency.py"
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete US1 only: POSIX and Windows script installer dry-run/user-local launcher behavior.
3. Validate US1 independently.
4. Stop before first-run setup, MCP guidance, lifecycle polish, or final packaging docs unless explicitly requested.

### Incremental Delivery

1. US1: install scripts and launchers.
2. US2: first-run safe setup.
3. US3: post-install verification commands.
4. US4: manual-copy MCP guidance.
5. US5: lifecycle and future-only packaging documentation.
6. Final Phase: safety and cross-platform gates.

### Safety Notes

- Every no-write path must prove or report `osc_writes_sent=0`.
- `hardware_verified` remains `false` for emulator, Fake M32, and install-time evidence.
- `production_live_ready` remains `false`.
- Default installation remains user-local and no-admin.
- Claude configuration remains manual-copy only.
