# Tasks: M32 MCP Bridge MVP

**Input**: `PLAN.md`, `.specify/memory/constitution.md`, `specs/001-m32-mcp-bridge/spec.md`, `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts/`.

**Scope Guard**: Implement the local Python 3.12 modular monolith only. Do not add WebUI, AI backend, database, microservices, raw OSC tools, arbitrary-path tools, M32-Edit control, hardware-verification claims from emulator results, or production/live instructions before Hardware Acceptance.

**Conflict Note**: The EMERGENCY clarification in `spec.md` and `plan.md` is controlling: EMERGENCY locks all AI writes, stops automation, cancels pending proposals, allows no AI mute, rollback, or console write, exits to OBSERVE, and requires reconciliation before any write can be enabled.

**Operational Note**: `.specify/feature.json` is absent in this workspace, so some SpecKit helper scripts may not resolve feature paths automatically. Do not repair this from implementation tasks unless explicitly approved; continue using `specs/001-m32-mcp-bridge/` as the feature directory.

**Testing Order Gate**: Unit/Codec -> Fake M32 -> External Emulator -> MCP Inspector and Claude Desktop -> Windows/macOS -> Hardware Acceptance.

## Phase 1: Setup

**Purpose**: Establish the Python project skeleton, dependency controls, and local modular monolith without implementing product behavior.

- [x] T001 Create Python 3.12 project metadata with runtime and test dependency groups in `pyproject.toml` (Req: FR-040, FR-045, SG-002; Depends: none)
- [x] T002 Create package skeleton directories under `src/m32_bridge/` for `mcp`, `core`, `osc`, `state`, `diagnostics`, `audit`, `config`, and `fake_m32` (Req: FR-040, SG-002; Depends: T001)
- [x] T003 Create test skeleton directories under `tests/unit/`, `tests/property/`, `tests/integration_fake_m32/`, `tests/integration_external_emulator/`, `tests/e2e_mcp/`, `tests/cross_platform/`, and `tests/hardware_acceptance/` (Req: SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011, SC-012, SC-013, SC-014; Depends: T001)
- [x] T004 Create non-secret example configuration stub matching `contracts/config.schema.json` in `config.example.yaml` (Req: FR-041, FR-051, SG-009; Depends: T001)
- [x] T005 Create developer README implementation notes stating no WebUI, no AI backend, no database, no raw OSC, no production/live use before Hardware Acceptance, and no EMERGENCY mute/rollback/write through AI in `README.md` (Req: FR-054, SG-002, SG-007, SG-008, SG-012; Depends: T001)
- [x] T006 Configure test markers for `unit`, `property`, `fake_m32`, `external_emulator`, `mcp`, `cross_platform`, and `hardware_acceptance` in `pyproject.toml` (Req: SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011, SC-012, SC-013, SC-014; Depends: T001, T003)
- [x] T007 Pin the official MCP Python SDK stable 1.x with an upper bound below v2 and create the dependency lock file in `uv.lock` (Req: FR-040, FR-045; Depends: T001)
- [x] T008 Create dependency and license register covering MCP SDK and community references without adding runtime community dependencies in `docs/dependency-license-register.md` (Req: FR-045, FR-051, SG-007; Depends: T007)
- [x] T009 Configure stdout/stderr logging policy for future stdio MCP work in `src/m32_bridge/config/logging.py` (Req: FR-040, FR-044, SG-003; Depends: T002)

**Checkpoint**: Project skeleton and dependency governance exist, but no console behavior is implemented.

---

## Phase 2: Foundational Unit/Codec Gate

**Purpose**: Build the shared domain, schema, OSC codec, property tests, rate limits, and fail-closed policy foundation required before any user story.

- [x] T010 Add JSON Schema loading tests for all contract files in `tests/unit/test_contract_schemas.py` (Req: FR-030, FR-050, FR-052; Depends: T003)
- [x] T011 Implement contract schema loader and Draft 2020-12 validation helpers in `src/m32_bridge/config/schemas.py` (Req: FR-030, FR-050, FR-052; Depends: T010)
- [x] T012 Add domain model tests for ConsoleIdentity, StateValue, Snapshot, Proposal, Operation, AuditRecord, ConnectionLifecycle, and VerificationState in `tests/unit/test_domain_models.py` (Req: FR-002, FR-010, FR-012, FR-030, FR-050; Depends: T003)
- [x] T013 Implement domain models in `src/m32_bridge/core/models.py` from `data-model.md` without adding persistence beyond JSON/JSONL (Req: FR-002, FR-010, FR-012, FR-030, FR-050, SG-007; Depends: T012)
- [x] T014 Add OSC golden packet, alignment, type, blob, malformed packet, and value-grid tests in `tests/unit/test_osc_codec.py` (Req: FR-012, FR-014, FR-015, SC-002; Depends: T003)
- [x] T015 Add property tests for OSC codec packing/alignment and malformed packet rejection in `tests/property/test_osc_codec_properties.py` (Req: FR-012, FR-015, SC-002; Depends: T014)
- [x] T016 Add property tests for value grids, display values, fader dB bounds, and headamp grid comparisons in `tests/property/test_value_grid_properties.py` (Req: FR-012, FR-014, FR-032, SC-002; Depends: T014)
- [x] T017 Implement strict OSC codec and value conversion in `src/m32_bridge/osc/codec.py` (Req: FR-012, FR-014, FR-015, SC-002; Depends: T014, T015, T016)
- [x] T018 Add policy matrix tests for modes, R1, R2, R3, R4, Main protection, prohibited operations, and EMERGENCY no-write behavior in `tests/unit/test_policy_matrix.py` (Req: FR-032, FR-036, FR-037, FR-054, SG-005, SG-011, SG-012, SC-007; Depends: T003)
- [x] T019 Implement runtime mode, risk, path allowlist, bounds, Main protection, R3 SOUNDCHECK-only, R4 blocked, and EMERGENCY policy in `src/m32_bridge/core/policy.py` (Req: FR-032, FR-036, FR-037, FR-054, SG-005, SG-011, SG-012; Depends: T018)
- [x] T020 Add rate-limit tests for per-resource serialization, mode-specific limits, fader delta limits, and repeated write attempts in `tests/unit/test_rate_limits.py` (Req: FR-032, FR-033; Depends: T018)
- [x] T021 Implement rate-limit policy helpers in `src/m32_bridge/core/rate_limits.py` (Req: FR-032, FR-033; Depends: T020)
- [x] T022 Add proposal digest, expiry, one-time-use, conflict baseline, rollback value, and server-computed risk tests in `tests/unit/test_proposals.py` (Req: FR-030, FR-031, FR-038, SC-010; Depends: T012)
- [x] T023 Add property tests for proposal digest stability, operation ordering sensitivity, and tamper detection in `tests/property/test_proposal_digest_properties.py` (Req: FR-030, FR-031; Depends: T022)
- [x] T024 Implement proposal store and digest lifecycle in `src/m32_bridge/core/proposals.py` (Req: FR-030, FR-031, FR-038, SC-010; Depends: T013, T019, T021, T022, T023)
- [x] T025 Add append-only JSONL audit serialization, redaction, per-operation detail, approval.source, approval.reference, latency_ms, and rejected-operation tests in `tests/unit/test_audit_writer.py` (Req: FR-050, FR-051, SC-004; Depends: T010)
- [x] T026 Implement append-only audit writer including approval.source, approval.reference, and per-operation latency_ms in `src/m32_bridge/audit/writer.py` (Req: FR-050, FR-051, SC-004; Depends: T025)
- [x] T027 Add snapshot checksum, completeness, stale/partial labeling, and environment label tests in `tests/unit/test_snapshots.py` (Req: FR-010, FR-052, SG-007, SC-003, SC-011; Depends: T010)
- [x] T028 Implement JSON snapshot capture model and checksum helpers in `src/m32_bridge/state/snapshot.py` (Req: FR-010, FR-052, SG-007, SC-003, SC-011; Depends: T013, T027)
- [x] T029 Add state cache revision, freshness, duplicate/out-of-order update, and manual-change detection tests in `tests/unit/test_state_cache.py` (Req: FR-011, FR-012, FR-013, FR-038, SC-001; Depends: T012)
- [x] T030 Add property tests for monotonic StateRevision and stale/partial state transitions in `tests/property/test_state_revision_properties.py` (Req: FR-011, FR-012, FR-013; Depends: T029)
- [x] T031 Implement in-memory state cache, StateRevision handling, freshness, and manual-change source labels in `src/m32_bridge/state/cache.py` (Req: FR-011, FR-012, FR-013, FR-038, SC-001; Depends: T013, T029, T030)
- [x] T032 Add unit gate command documentation for codec, schema, property, policy, rate-limit, audit, and snapshot tests in `README.md` (Req: SC-002, SC-004, SC-007; Depends: T011, T017, T019, T021, T026, T028, T031)

**Checkpoint**: Unit/Codec gate can run before any UDP, Fake M32, emulator, or MCP host work.

---

## Phase 3: User Story 1 - Connect and Prove Live State (Priority: P1)

**Goal**: Connect to Fake M32 or an OSC target, prove source identity, and observe an external gain change from +10.0 dB to +6.0 dB.

**Independent Test**: Connect to Fake M32, read Channel 1 headamp gain as +10.0 dB, inject an external change to +6.0 dB, and verify the bridge returns +6.0 dB with newer revision, non-stale timestamp, and source label.

### Tests for User Story 1

- [x] T033 [US1] Add Fake M32 identity, `/xremote`, Channel 1 gain, and external manual change tests in `tests/integration_fake_m32/test_connect_live_state.py` (Req: FR-001, FR-002, FR-003, FR-004, FR-013, SG-001, SC-001, SC-011; Depends: T032)
- [x] T034 [US1] Add UDP transport timeout, source endpoint check, malformed reply, and unknown firmware fail-closed tests in `tests/integration_fake_m32/test_connection_fail_closed.py` (Req: FR-003, FR-005, SG-010, SC-008; Depends: T032)

### Implementation for User Story 1

- [x] T035 [US1] Implement deterministic Fake M32 UDP server identity, leaf reads, leaf writes, `/xremote`, and manual change injection in `src/m32_bridge/fake_m32/server.py` (Req: FR-001, FR-003, FR-004, FR-013, SC-001; Depends: T033)
- [x] T036 [US1] Implement Fake M32 `/node` seeded container support for snapshots, routing, channels, buses, and supported container reads in `src/m32_bridge/fake_m32/node.py` (Req: FR-010, FR-013, SC-003; Depends: T035)
- [x] T037 [US1] Implement Fake M32 meter fixtures and scheduled meter updates in `src/m32_bridge/fake_m32/meters.py` (Req: FR-015, FR-023, SC-002; Depends: T035)
- [x] T038 [US1] Implement Fake M32 RTA source and RTA band fixtures in `src/m32_bridge/fake_m32/rta.py` (Req: FR-016, FR-023, SC-002; Depends: T035)
- [x] T039 [US1] Implement Fake M32 clock, AES50 A/B, and expansion-card sync seeded state in `src/m32_bridge/fake_m32/sync_state.py` (Req: FR-017, SG-006; Depends: T035)
- [x] T040 [US1] Implement Fake M32 failure injection for lost, delayed, duplicate, malformed, out-of-order packets, disconnect, and restart in `src/m32_bridge/fake_m32/failures.py` (Req: FR-005, FR-011, SG-010, SC-008; Depends: T035)
- [x] T041 [US1] Implement OSC UDP transport, source endpoint validation, timeout handling, and write-lock-on-failure behavior in `src/m32_bridge/osc/transport.py` (Req: FR-001, FR-005, SG-009, SG-010, SC-008; Depends: T034)
- [x] T042 [US1] Implement connection lifecycle and identity/capability discovery in `src/m32_bridge/osc/discovery.py` (Req: FR-002, FR-003, SG-010, SC-011; Depends: T035, T041)
- [x] T043 [US1] Implement `/xremote` renewal before expiry with default 8s and write-lock fail-safe in `src/m32_bridge/osc/subscriptions.py` (Req: FR-004, FR-005, SC-008; Depends: T041, T042)
- [x] T044 [US1] Implement read synchronization and reconciliation from OSC replies into state cache in `src/m32_bridge/state/sync.py` (Req: FR-011, FR-012, FR-013, SG-001, SC-001; Depends: T031, T042, T043)
- [x] T045 [US1] Implement console status service with environment labels and hardware verification separation in `src/m32_bridge/core/status.py` (Req: FR-002, FR-003, SG-007, SG-008, SC-011; Depends: T042, T044)
- [x] T046 [US1] Document Fake M32 validation command and +10 dB to +6 dB proof in `README.md` (Req: SC-001, SC-011; Depends: T035, T044, T045)

**Checkpoint**: US1 is independently testable through Fake M32 without MCP.

---

## Phase 4: User Story 2 - Query Console State Through Claude/ChatGPT (Priority: P1)

**Goal**: Expose read-only semantic MCP tools for console status, channels, buses, routing, clock, meters, RTA, snapshots, changes, comparisons, and signal trace.

**Independent Test**: Use MCP calls against Fake M32 to verify structured read-only results with no state-changing OSC packets in OBSERVE.

### Tests for User Story 2

- [x] T047 [US2] Add read-tool contract tests for `m32_console_status`, `m32_get_overview`, `m32_list_channels`, and `m32_get_channel` in `tests/e2e_mcp/test_read_tools_channels.py` (Req: FR-040, FR-043, FR-044, SC-012; Depends: T046)
- [x] T048 [US2] Add read-tool contract tests for bus, routing, clock, meters, RTA, snapshots, compare, changes, and trace in `tests/e2e_mcp/test_read_tools_consolewide.py` (Req: FR-015, FR-016, FR-017, FR-023, FR-040, FR-043, FR-044, SC-012; Depends: T036, T037, T038, T039, T046)
- [x] T049 [US2] Add OBSERVE-mode no-state-changing-OSC packet test in `tests/e2e_mcp/test_observe_read_only.py` (Req: FR-043, SG-003, SC-006; Depends: T046)

### Implementation for User Story 2

- [x] T050 [US2] Implement MCP stdio server bootstrap with stdout protocol isolation and stderr logging in `src/m32_bridge/mcp/server.py` (Req: FR-040, FR-044; Depends: T009, T045)
- [x] T051 [US2] Implement read-only status and channel MCP tools in `src/m32_bridge/mcp/read_tools.py` (Req: FR-012, FR-014, FR-040, FR-043, FR-044; Depends: T047, T050)
- [x] T052 [US2] Implement bus, routing, clock/sync, meter, RTA, snapshot, compare, changes, and trace MCP tools in `src/m32_bridge/mcp/read_tools.py` (Req: FR-015, FR-016, FR-017, FR-023, FR-040, FR-043, FR-044; Depends: T048, T050)
- [x] T053 [US2] Implement meter bank decoding and signal position mapping in `src/m32_bridge/osc/meters.py` (Req: FR-015, FR-023, SC-002; Depends: T017, T037, T052)
- [x] T054 [US2] Implement routing, bus, clock, RTA, and `/node` read adapters in `src/m32_bridge/osc/client.py` (Req: FR-010, FR-016, FR-017, FR-023; Depends: T036, T038, T039, T041, T052, T053)
- [x] T055 [US2] Enforce read-only MCP declarations and deny writes in OBSERVE in `src/m32_bridge/mcp/server.py` (Req: FR-043, SG-003, SC-006; Depends: T049, T050, T051, T052)

**Checkpoint**: US2 is independently testable through MCP stdio against Fake M32 read-only state.

---

## Phase 5: User Story 3 - Event Preflight and Evidence-Based Setup Advice (Priority: P1)

**Goal**: Produce deterministic blockers, warnings, advisories, and recommendations from console evidence without executing operations.

**Independent Test**: Seed Fake M32 with clock, sync, routing, gain, mute, processing, and protected-path issues; preflight returns findings with evidence and keeps recommendations non-executable.

### Tests for User Story 3

- [x] T056 [US3] Add event preflight blocker tests for identity, firmware, clock, AES50, expansion-card sync, routing, gain, meters, RTA source, and protected paths in `tests/integration_fake_m32/test_event_preflight.py` (Req: FR-017, FR-020, FR-021, SG-006, SC-003; Depends: T039, T052, T054, T055)
- [x] T057 [US3] Add recommendation separation tests proving findings and recommendations do not create writes or executable proposals in `tests/unit/test_recommendation_separation.py` (Req: FR-020, FR-021, FR-022, SG-003; Depends: T032)

### Implementation for User Story 3

- [x] T058 [US3] Implement DiagnosticFinding models and evidence-path formatting in `src/m32_bridge/diagnostics/findings.py` (Req: FR-020, FR-021; Depends: T013, T056)
- [x] T059 [US3] Implement clock, AES50, and expansion-card readiness checks in `src/m32_bridge/diagnostics/clock.py` (Req: FR-017, FR-020, SG-006; Depends: T054, T058)
- [x] T060 [US3] Implement routing, gain staging, processing, meter, and Main-protection diagnostics in `src/m32_bridge/diagnostics/preflight.py` (Req: FR-020, FR-021, SG-011; Depends: T054, T058, T059)
- [x] T061 [US3] Implement analysis MCP tools `m32_event_preflight`, `m32_analyze_gain_staging`, `m32_analyze_routing`, `m32_analyze_processing`, and `m32_recommend_event_setup` in `src/m32_bridge/mcp/analysis_tools.py` (Req: FR-020, FR-021, FR-022, FR-044; Depends: T057, T060)

**Checkpoint**: US3 provides evidence-based setup advice with no execution path.

---

## Phase 6: User Story 4 - Create a Safe Proposal Separate From Execution (Priority: P1)

**Goal**: Create stored, expiring, digest-protected proposals with operations, risks, bounds, affected paths, rate limits, and rollback values, without sending writes.

**Independent Test**: Ask for a safe fader proposal and confirm an expiring proposal exists with required fields and zero OSC writes.

### Tests for User Story 4

- [x] T062 [US4] Add proposal contract tests against `proposal.schema.json` for ID, digest, base snapshot, revisions, operations, bounds, rollback values, risk summary, and server-computed flag in `tests/unit/test_proposal_contract.py` (Req: FR-030, FR-032; Depends: T024)
- [x] T063 [US4] Add proposal rejection tests for raw OSC, arbitrary paths, R4 operations, Main implicit side effects, and R3 outside SOUNDCHECK in `tests/unit/test_proposal_rejections.py` (Req: FR-032, FR-036, FR-037, SG-002, SG-005, SG-011; Depends: T019, T024)
- [x] T064 [US4] Add proposal rate-limit and per-resource limit tests in `tests/unit/test_rate_limits.py` (Req: FR-032, FR-033; Depends: T021, T024)
- [x] T065 [US4] Add MCP proposal tool test proving `m32_propose_changes` sends no state-changing OSC packets in `tests/e2e_mcp/test_propose_changes.py` (Req: FR-022, FR-030, FR-043, SC-006; Depends: T055)

### Implementation for User Story 4

- [x] T066 [US4] Implement operation allowlist, bounds calculation, fader LIVE max +/-3 dB, rate-limit checks, and rollback value capture in `src/m32_bridge/core/operations.py` (Req: FR-030, FR-032, FR-033, FR-036, SG-011; Depends: T062, T063, T064)
- [x] T067 [US4] Implement proposal creation service with snapshot revision, expiry, digest, server-computed risk, and no write side effects in `src/m32_bridge/core/proposals.py` (Req: FR-030, FR-031, FR-038; Depends: T024, T066)
- [x] T068 [US4] Implement `m32_propose_changes` MCP tool with semantic inputs only and no raw OSC surface in `src/m32_bridge/mcp/write_tools.py` (Req: FR-030, FR-040, FR-043, SG-002; Depends: T065, T067)

**Checkpoint**: US4 creates proposals only; execution remains unavailable.

---

## Phase 7: User Story 5 - Execute Only After Human Approval, Readback, Audit, and Rollback (Priority: P1)

**Goal**: Execute approved proposals only after MCP host confirmation, re-check policy and state, read back every write, audit every attempt, and support targeted rollback outside EMERGENCY.

**Independent Test**: Create a fresh fader proposal, approve through host confirmation, execute, verify readback/audit, roll back, and verify original value.

### Tests for User Story 5

- [x] T069 [US5] Add execution denial tests for missing MCP host confirmation, Always Allow configuration, expired proposals, used proposals, stale state, unsupported capability, and policy denial in `tests/unit/test_execute_denials.py` (Req: FR-031, FR-032, FR-043, SG-003, SC-004; Depends: T068)
- [x] T070 [US5] Add MCP host confirmation harness tests proving write tools are sensitive/destructive and no approval_token is accepted in `tests/e2e_mcp/test_host_confirmation.py` (Req: FR-043, SG-003; Depends: T068)
- [x] T071 [US5] Add safe write readback, display-grid matching, retry, timeout, and readback mismatch tests in `tests/integration_fake_m32/test_safe_write_readback.py` (Req: FR-034, FR-035, SC-005; Depends: T068)
- [x] T072 [US5] Add targeted rollback tests proving only proposal-touched parameters are restored and rollback is denied in EMERGENCY in `tests/integration_fake_m32/test_targeted_rollback.py` (Req: FR-035, FR-054, SG-012, SC-005; Depends: T068)
- [x] T073 [US5] Add audit coverage tests for approved, rejected, failed, readback mismatch, rollback transactions, approval.source, approval.reference, and latency_ms per operation in `tests/integration_fake_m32/test_write_audit.py` (Req: FR-050, FR-051, SC-004; Depends: T026, T068)

### Implementation for User Story 5

- [x] T074 [US5] Implement serialized transaction executor with MCP host-confirmation boundary, no approval_token acceptance, rate-limit enforcement, and one-time proposal use in `src/m32_bridge/core/executor.py` (Req: FR-031, FR-032, FR-033, FR-043, SG-003; Depends: T069, T070)
- [x] T075 [US5] Implement allowlisted OSC write adapter for semantic operations only in `src/m32_bridge/osc/client.py` (Req: FR-032, SG-002, SG-005; Depends: T074)
- [x] T076 [US5] Implement readback verification with retry, timeout, display-grid comparison, and failure status in `src/m32_bridge/core/readback.py` (Req: FR-034, FR-035, SC-005; Depends: T071, T075)
- [x] T077 [US5] Implement targeted rollback service using stored rollback candidates and policy checks in `src/m32_bridge/core/rollback.py` (Req: FR-035, FR-054, SG-012; Depends: T072, T076)
- [x] T078 [US5] Wire execution, verification, rollback, and audit records into `m32_execute_proposal`, `m32_verify_proposal`, and `m32_rollback_proposal` in `src/m32_bridge/mcp/write_tools.py` (Req: FR-034, FR-035, FR-043, FR-050; Depends: T073, T074, T076, T077)

**Checkpoint**: US5 safe writes work on Fake M32 and remain bounded by policy.

---

## Phase 8: User Story 6 - Reject Manual Change Conflicts (Priority: P1)

**Goal**: Reject execution when manual or external state changes conflict with a proposal baseline, and send zero writes.

**Independent Test**: Create a proposal at revision N, externally change the same target, approve execution, and confirm `PROPOSAL_CONFLICT` with zero OSC writes.

### Tests for User Story 6

- [x] T079 [US6] Add manual change conflict tests for fader, mute, gain, send, routing, and processing paths in `tests/integration_fake_m32/test_manual_conflicts.py` (Req: FR-038, SG-004, SC-010; Depends: T078)
- [x] T080 [US6] Add zero-write assertion tests for conflicted, expired, modified, missing, used, and stale proposals in `tests/integration_fake_m32/test_zero_write_conflicts.py` (Req: FR-031, FR-038, SC-010; Depends: T078)

### Implementation for User Story 6

- [x] T081 [US6] Implement affected-path reconciliation before execution in `src/m32_bridge/state/sync.py` (Req: FR-031, FR-038, SG-004; Depends: T079)
- [x] T082 [US6] Implement proposal conflict reporter with path, previous value, current value, revision, and source in `src/m32_bridge/core/conflicts.py` (Req: FR-031, FR-038, SC-010; Depends: T079, T081)
- [x] T083 [US6] Integrate conflict reporter into executor and MCP errors in `src/m32_bridge/core/executor.py` (Req: FR-031, FR-038, SG-004, SC-010; Depends: T080, T082)

**Checkpoint**: US6 proves manual control wins.

---

## Phase 9: External Emulator Release Gate

**Purpose**: Validate OSC behavior against Patrick-Gilles Maillot X32 Emulator after Fake M32 read/write/conflict behavior is complete and before MCP readiness claims.

- [x] T084 Add external emulator setup guard, license notice, and no-redistribution checks in `tests/integration_external_emulator/test_emulator_setup.py` (Req: SG-007, SG-008, SC-013; Depends: T083)
- [x] T085 Add external emulator identity, leaf read, external write, `/xremote`, `/node`, meter, and reconnect tests in `tests/integration_external_emulator/test_emulator_read_sync.py` (Req: FR-001, FR-004, FR-010, FR-015, SC-001, SC-003, SC-013; Depends: T083)
- [x] T086 Add external emulator safe proposal, execute, readback, conflict, and targeted rollback tests in `tests/integration_external_emulator/test_emulator_safe_write.py` (Req: FR-030, FR-031, FR-032, FR-033, FR-034, FR-035, FR-036, FR-037, FR-038, SC-004, SC-005, SC-010, SC-013; Depends: T083)
- [x] T087 Implement external emulator pytest marker and target configuration loader in `src/m32_bridge/config/emulator.py` (Req: SC-013, SG-007; Depends: T084)
- [x] T088 Document external emulator gate, limitations, and hardware-unverified status in `README.md` (Req: SG-007, SG-008, SC-013; Depends: T084, T085, T086, T087)

**Checkpoint**: External Emulator gate passes but still does not grant hardware verification.

---

## Phase 10: User Story 7 - Measurement Microphone Awareness (Priority: P2)

**Goal**: Use an explicit event profile measurement microphone role and phantom policy without guessing from channel names or enabling phantom automatically.

**Independent Test**: Configure a measurement microphone channel, run preflight and recommendations, and verify Main protection, RTA eligibility, and no phantom enable.

### Tests for User Story 7

- [x] T089 [US7] Add event-profile schema validation tests for channel, bus, output dictionaries, measurement microphone, protected paths, mode permissions, and known-good reference in `tests/unit/test_event_profile_contract.py` (Req: FR-025, SG-011; Depends: T011)
- [x] T090 [US7] Add measurement microphone preflight tests for explicit role, Main exclusion, protected sends, RTA eligibility, and no phantom enable in `tests/integration_fake_m32/test_measurement_microphone.py` (Req: FR-025, FR-037, SG-006, SG-011; Depends: T061)

### Implementation for User Story 7

- [x] T091 [US7] Implement event profile loader and validator in `src/m32_bridge/config/event_profile.py` (Req: FR-025, FR-052; Depends: T089)
- [x] T092 [US7] Implement measurement microphone role handling and phantom policy enforcement in `src/m32_bridge/diagnostics/preflight.py` (Req: FR-025, FR-037, SG-006; Depends: T090, T091)
- [x] T093 [US7] Add measurement microphone protection to recommendation generation in `src/m32_bridge/diagnostics/preflight.py` (Req: FR-022, FR-025, SG-011; Depends: T092)

**Checkpoint**: US7 supports measurement microphone awareness without unsafe phantom behavior.

---

## Phase 11: User Story 8 - RTA-Assisted Soundcheck (Priority: P2)

**Goal**: Interpret current RTA source safely and optionally scan configured sources in SOUNDCHECK with save/restore behavior.

**Independent Test**: Read current RTA data with source identity, reject scan outside SOUNDCHECK, and restore original source after scan success, failure, or cancellation.

### Tests for User Story 8

- [x] T094 [US8] Add RTA source identity, unknown-source, no per-channel spectra, and acquisition settings tests in `tests/integration_fake_m32/test_rta_analysis.py` (Req: FR-016, FR-023, SC-002; Depends: T061)
- [x] T095 [US8] Add sequential RTA scan mode, save/restore, failure, and cancellation tests in `tests/integration_fake_m32/test_rta_scan.py` (Req: FR-024, SG-006; Depends: T061)

### Implementation for User Story 8

- [x] T096 [US8] Implement RTA read and analysis service with source identity and limited conclusions in `src/m32_bridge/diagnostics/rta.py` (Req: FR-016, FR-023; Depends: T094)
- [x] T097 [US8] Implement SOUNDCHECK-only sequential RTA scan with original source save/restore in `src/m32_bridge/diagnostics/rta.py` (Req: FR-024, SG-006; Depends: T095, T096)
- [x] T098 [US8] Expose `m32_analyze_rta` behavior through MCP analysis tools in `src/m32_bridge/mcp/analysis_tools.py` (Req: FR-016, FR-023, FR-024, FR-044; Depends: T096, T097)

**Checkpoint**: US8 provides RTA assistance without false spectra claims.

---

## Phase 12: User Story 9 - Recover Safely From Connection Failure and Emergency Lock (Priority: P2)

**Goal**: Disable writes during disconnect/stale state, reconcile before unlock, and enforce EMERGENCY as no AI write/mute/rollback/console-write mode.

**Independent Test**: Stop Fake M32, confirm writes lock within one second, restart and reconcile before unlock; enter EMERGENCY, verify proposal cancellation and denial of mute/rollback/write; exit to OBSERVE and require reconciliation.

### Tests for User Story 9

- [x] T099 [US9] Add heartbeat loss, stale state, disconnect, restart, bounded backoff, and reconciliation-before-unlock tests in `tests/integration_fake_m32/test_reconnect_reconciliation.py` (Req: FR-005, FR-006, SG-010, SC-008, SC-009; Depends: T083)
- [x] T100 [US9] Add malformed, delayed, duplicated, dropped, and out-of-order packet failure-injection tests in `tests/integration_fake_m32/test_failure_injection.py` (Req: FR-005, FR-011, SG-010, SC-008; Depends: T040, T083)
- [x] T101 [US9] Add EMERGENCY tests for proposal cancellation, no AI mute, no AI rollback, no console write, OBSERVE exit, and reconciliation-before-write in `tests/integration_fake_m32/test_emergency_lock.py` (Req: FR-054, SG-012, SC-008, SC-009; Depends: T083)

### Implementation for User Story 9

- [x] T102 [US9] Implement bounded reconnect and reconciliation controller in `src/m32_bridge/core/connection.py` (Req: FR-005, FR-006, SG-010; Depends: T099)
- [x] T103 [US9] Wire Fake M32 failure injection into transport-facing tests in `src/m32_bridge/fake_m32/failures.py` (Req: FR-005, FR-011, SC-008; Depends: T100)
- [x] T104 [US9] Implement write lock, OBSERVE-only unlock after reconciliation, emergency enter, and emergency exit state machine in `src/m32_bridge/core/emergency.py` (Req: FR-054, SG-012; Depends: T101, T102)
- [x] T105 [US9] Wire `m32_lock_writes`, `m32_unlock_writes`, `m32_enter_emergency`, and `m32_exit_emergency_to_observe` into `src/m32_bridge/mcp/write_tools.py` with no OSC writes from emergency tools in `src/m32_bridge/mcp/write_tools.py` (Req: FR-054, SG-012; Depends: T104)

**Checkpoint**: US9 proves fail-closed recovery and EMERGENCY behavior.

---

## Phase 13: Optional ChatGPT Secondary Transport Guard

**Purpose**: Cover FR-042 without implementing production ChatGPT deployment. The secondary transport remains disabled by default and may use only Secure MCP Tunnel or another approved outbound secure tunnel when enabled.

- [x] T106 Add disabled-by-default Streamable HTTP and Secure MCP Tunnel configuration tests in `tests/unit/test_secondary_transport_config.py` (Req: FR-041, FR-042, SG-009; Depends: T011)
- [x] T107 Add secondary transport guard tests proving OSC is never public and bind host is loopback/private only in `tests/e2e_mcp/test_secondary_transport_guard.py` (Req: FR-041, FR-042, SG-009; Depends: T106)
- [x] T108 Implement optional secondary transport guard with disabled-by-default behavior in `src/m32_bridge/mcp/transport_http.py` (Req: FR-041, FR-042, SG-009; Depends: T106, T107)
- [x] T109 Document optional ChatGPT transport as Secure MCP Tunnel only, with no production enablement and no public OSC exposure in `README.md` (Req: FR-042, SG-009; Depends: T108)

**Checkpoint**: FR-042 is covered without expanding MVP runtime or exposing OSC.

---

## Phase 14: Operator Controls Gate

**Purpose**: Cover FR-053 for operator controls: health/doctor, snapshot, verify-connection, and audit-tail.

- [x] T110 Add operator control tests for health/doctor, snapshot, verify-connection, and audit-tail in `tests/e2e_mcp/test_operator_controls.py` (Req: FR-053, FR-050, FR-052, SC-004; Depends: T061, T078, T105)
- [x] T111 Implement operator controls for health/doctor, snapshot, verify-connection, and audit-tail in `src/m32_bridge/cli.py` (Req: FR-053, FR-050, FR-052; Depends: T110)
- [x] T112 Wire operator controls to status, snapshot store, connection verification, and audit reader in `src/m32_bridge/cli.py` (Req: FR-053, SG-003; Depends: T111)
- [x] T113 Document operator controls without adding WebUI, mixer UI, or production/live instructions in `README.md` (Req: FR-053, SG-002; Depends: T112)

**Checkpoint**: FR-053 has explicit test and implementation coverage.

---

## Phase 15: MCP Inspector and Claude Desktop Gate

**Purpose**: Validate semantic MCP surface, host confirmation, clean stdio, structured outputs, every MVP tool, and scripted Claude Desktop workflows after Fake M32, external emulator, FR-042 guard, FR-053 controls, and EMERGENCY behavior.

- [x] T114 Add MCP Inspector inventory test that parses `specs/001-m32-mcp-bridge/contracts/mcp-tools.md` and proves every declared MVP tool is exposed and no prohibited tool exists in `tests/e2e_mcp/test_tool_inventory.py` (Req: FR-043, FR-044, SG-002, SG-005, SC-007, SC-012; Depends: T088, T105, T109, T113)
- [x] T115 Add MCP schema and structured output tests for status, read, snapshot, compare, verify, preflight, propose, execute, rollback, emergency, lock, unlock, RTA, audit-tail, and operator controls in `tests/e2e_mcp/test_tool_schemas_outputs.py` (Req: FR-040, FR-043, FR-044, FR-053, FR-054, SC-012; Depends: T088, T105, T109, T113)
- [x] T116 Add MCP cancellation, timeout, malformed model input, concurrent read, and stdout/stderr protocol tests in `tests/e2e_mcp/test_mcp_protocol_resilience.py` (Req: FR-040, FR-044, SC-012; Depends: T088, T105, T109, T113)
- [x] T117 Add Claude Desktop scripted read-only validation conversation test in `tests/e2e_mcp/test_claude_read_only_conversation.py` (Req: FR-040, FR-044, SC-001, SC-012; Depends: T114, T115, T116)
- [x] T118 Add Claude Desktop proposal, host confirmation, execute, readback, conflict, rollback, audit-tail, operator controls, unlock OBSERVE-only, and EMERGENCY denial conversation test in `tests/e2e_mcp/test_claude_safe_write_conversation.py` (Req: FR-030, FR-031, FR-032, FR-033, FR-034, FR-035, FR-036, FR-037, FR-038, FR-043, FR-050, FR-053, FR-054, SG-003, SG-012, SC-004, SC-005, SC-010, SC-012; Depends: T117)
- [x] T119 Document MCP Inspector and Claude Desktop local validation steps in `README.md` without adding production/live instructions in `README.md` (Req: FR-040, FR-043, FR-053, SC-012; Depends: T117, T118)

**Checkpoint**: MCP gate passes only after External Emulator, secondary transport guard, operator controls, and EMERGENCY behavior are covered.

---

## Phase 16: Windows/macOS Cross-Platform Gate

**Purpose**: Prove unit, Fake M32, MCP smoke, packaging, and startup tests pass on Windows and macOS before MVP release.

- [x] T120 Add Windows smoke test entry for unit, property, Fake M32, MCP smoke, package build, and startup in `tests/cross_platform/test_windows_smoke.py` (Req: SG-009, SC-012; Depends: T119)
- [x] T121 Add macOS smoke test entry for unit, property, Fake M32, MCP smoke, package build, and startup in `tests/cross_platform/test_macos_smoke.py` (Req: SG-009, SC-012; Depends: T119)
- [x] T122 Add packaging/startup verification for Python 3.12 local process without WebUI, database, or microservices in `src/m32_bridge/__main__.py` (Req: FR-040, FR-045, SG-002; Depends: T120, T121)
- [x] T123 Document cross-platform release gate and required evidence in `README.md` (Req: SG-008, SC-012; Depends: T122)

**Checkpoint**: Cross-platform gate passes before any MVP release claim.

---

## Phase 17: Hardware Acceptance Gate

**Purpose**: Define and run the real M32 acceptance suite before any `hardware-verified`, production, or Live readiness claim. Do not assume deferred hardware data.

- [x] T124 Add hardware acceptance checklist tests for identity, firmware, expansion card, clock, AES50, card sync, routing, and network isolation in `tests/hardware_acceptance/test_hardware_readiness.py` (Req: FR-017, SG-006, SG-008, SG-009, SC-014; Depends: T123)
- [x] T125 Add physical manual gain/fader challenge tests proving live manual change detection before hardware verification in `tests/hardware_acceptance/test_physical_manual_change.py` (Req: FR-001, FR-013, SG-001, SC-001, SC-014; Depends: T123)
- [x] T126 Add isolated safe write, readback, manual conflict, disconnect/reconnect, and targeted rollback hardware tests in `tests/hardware_acceptance/test_hardware_safe_write.py` (Req: FR-030, FR-031, FR-032, FR-033, FR-034, FR-035, FR-036, FR-037, FR-038, FR-050, FR-054, SG-003, SG-004, SC-004, SC-005, SC-010, SC-014; Depends: T123)
- [x] T127 Implement hardware verification guard that sets `HARDWARE_VERIFIED` only after hardware acceptance evidence exists in `src/m32_bridge/core/status.py` (Req: FR-002, SG-007, SG-008, SC-011, SC-014; Depends: T124, T125, T126)
- [x] T128 Document Hardware Acceptance evidence requirements and emulator-not-hardware warning in `README.md` (Req: SG-007, SG-008, SC-014; Depends: T127)

**Checkpoint**: Hardware gate is mandatory and cannot be satisfied by Fake M32 or external emulator.

---

## Final Phase: Safety, Governance, and Release Review

**Purpose**: Confirm all SpecKit quality gates and constitutional requirements before moving beyond implementation. Final safety tests must run before the full quality-gate evidence task.

- [x] T129 Audit final MCP tool surface for absence of raw OSC, arbitrary path, shell, firmware, shutdown, SD format, phantom enable, sample-rate, and clock write tools in `tests/e2e_mcp/test_tool_inventory.py` (Req: SG-002, SG-005, SC-007; Depends: T119)
- [x] T130 Verify final implementation contains no WebUI, AI backend, database service, microservice split, or M32-Edit control in `tests/unit/test_scope_guard.py` (Req: FR-045, SG-002; Depends: T123)
- [x] T131 Verify all audit records redact secrets and every write attempt has append-only JSONL audit coverage with approval.source, approval.reference, and latency_ms in `tests/integration_fake_m32/test_write_audit.py` (Req: FR-050, FR-051, SC-004; Depends: T123)
- [x] T132 Verify EMERGENCY remains no AI mute, no rollback, no console write, cancel pending proposals, exit to OBSERVE, and require reconciliation in `tests/integration_fake_m32/test_emergency_lock.py` (Req: FR-054, SG-012; Depends: T123)
- [x] T133 Run full quality-gate sequence and record results in `README.md`: Unit/Codec, Fake M32, External Emulator, MCP Inspector, Claude Desktop, Windows/macOS, and Hardware Acceptance when available (Req: SC-001, SC-002, SC-003, SC-004, SC-005, SC-006, SC-007, SC-008, SC-009, SC-010, SC-011, SC-012, SC-013, SC-014; Depends: T128, T129, T130, T131, T132)

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 Setup: no dependencies.
- Phase 2 Foundational Unit/Codec Gate: depends on Phase 1.
- US1 Fake M32 connection: depends on Phase 2.
- US2 Read-only MCP: depends on US1 and the Fake M32 `/node`, meters, RTA, and sync fixtures.
- US3 Event preflight: depends on US2 and Fake M32 clock/AES50/card sync fixtures.
- US4 Proposal creation: depends on Phase 2 and US2.
- US5 Safe write: depends on US4 and rate-limit foundation.
- US6 Manual conflict protection: depends on US5.
- External Emulator Gate: depends on US6 and must pass before MCP readiness claims.
- US7 Measurement microphone: depends on US3.
- US8 RTA soundcheck: depends on US3.
- US9 Recovery and EMERGENCY: depends on US6 and Fake M32 failure injection.
- Optional ChatGPT Secondary Transport Guard: depends on foundational schemas and remains disabled by default.
- Operator Controls Gate: depends on analysis, safe-write, and EMERGENCY behavior.
- MCP Inspector and Claude Desktop Gate: depends on External Emulator Gate, US9, FR-042 guard, and FR-053 controls.
- Windows/macOS Gate: depends on MCP Inspector and Claude Desktop Gate.
- Hardware Acceptance Gate: depends on Windows/macOS Gate and physical hardware availability.
- Final Safety Review: final safety tests T129-T132 must pass before full quality-gate evidence T133.

### User Story Dependencies

- US1 -> US2 -> US3 establishes Read-only MVP.
- US4 -> US5 -> US6 establishes Safe Write MVP.
- US7 and US8 depend on US3 and can run after Read-only diagnostics are stable.
- US9 depends on Safe Write and conflict behavior because it must deny writes, rollback, and pending proposals under failure and EMERGENCY.

### Required Gate Order

1. Unit/Codec: T010-T032.
2. Fake M32: T033-T083 and T089-T105 where applicable.
3. External Emulator: T084-T088.
4. MCP Inspector and Claude Desktop: T114-T119.
5. Windows/macOS: T120-T123.
6. Hardware Acceptance: T124-T128.
7. Final Safety and Full Quality Gate: T129-T133.

---

## Parallel Execution Examples

No `[P]` markers are used because every task declares a dependency and the current instruction forbids marking dependent tasks as parallel. Parallelization is still possible manually when dependency sets are satisfied and target files do not overlap.

```text
After T032, T033 and T034 can be prepared by different implementers if they coordinate Fake M32 fixtures.
After T061, T062, T063, T064, and T065 can be prepared in separate test files before converging on T066.
After T083, T084, T085, and T086 can be prepared in separate external emulator test files before T087.
After T123, T124, T125, and T126 can be prepared separately when real hardware is available.
```

---

## Implementation Strategy

### MVP First: Read-only MVP

1. Complete Phase 1 and Phase 2.
2. Complete US1, US2, and US3.
3. Validate Unit/Codec and Fake M32 read-only behavior.
4. Do not add Safe Write until read-only state, freshness, identity, and preflight evidence are stable.

### Safe Write Increment

1. Complete US4, US5, and US6 after Read-only MVP.
2. Validate proposal separation, MCP host confirmation, policy, rate limits, readback, audit, rollback, and manual conflict rejection on Fake M32.
3. Run External Emulator Gate before MCP readiness claims.

### Host and Release Gates

1. Run MCP Inspector and Claude Desktop gate only after Fake M32, External Emulator, FR-042 guard, FR-053 controls, and EMERGENCY behavior are covered.
2. Run Windows/macOS smoke and packaging/startup gates.
3. Run Hardware Acceptance only with the real M32 and required deferred inputs.
4. Run final safety tests before recording the full quality-gate result.
5. Do not claim production/live readiness or `hardware-verified` before Hardware Acceptance passes.

---

## Notes

- Every task lists target file path, linked requirements, and dependencies.
- Tests are mandatory because the constitution and success criteria require them.
- Emulator success is never hardware verification.
- R3 remains SOUNDCHECK-only. R4 remains blocked.
- EMERGENCY remains a full AI-write lock with no mute, rollback, or console write.
- MCP host confirmation remains the only approval boundary for MCP writes; do not add `approval_token`.
- Deferred hardware details must be collected during Hardware Acceptance and must not be invented during implementation.
