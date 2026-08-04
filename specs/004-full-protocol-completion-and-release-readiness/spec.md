# Feature Specification: Full Protocol Completion and Release Readiness

**Feature Branch**: `main`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: Complete the audited protocol surface, read/write pipelines, verification, controlled maintenance boundary, emulator matrix, physical acceptance, and release readiness without a broad rewrite.

## Constitution Alignment

This feature must comply with the amended constitution and the updated root plan. The normal MVP surface remains typed, bounded, local, and proposal-driven. Controlled maintenance is a separate boundary, not a relaxation of the normal write path. Emulator evidence, Fake M32 evidence, and hardware evidence must remain distinct, and only exact physical acceptance evidence may establish hardware verification.

The feature also inherits the owner-approved default LIVE safety policy of limiting approved fader changes to +/-3 dB unless configured lower. That policy is an internal safety rule and does not change OSC protocol precision.

## Supersession Note

This feature supersedes historical clauses in older quickstarts and specs that treated controlled R4 maintenance as permanently prohibited, treated emulator success as hardware proof, or assumed the declared tool surface could remain partial at release. The updated constitution and root PLAN are the governing source for the normal MVP surface plus the separate maintenance boundary.

## Clarifications

### Session 2026-08-03

- Q: What is the exact local operator authorization UX for R4 permits? -> A: Interactive local CLI flow only. Operator must type `AUTHORIZE <ACTION_NAME> <LAST_8_DIGEST_CHARS>`, then re-enter a generated six-digit challenge; non-interactive approval, piping, environment-variable approval, wildcard/batch/permanent approval, and `--yes` are prohibited.
- Q: Which R4 actions are exposed through MCP versus local-only controls? -> A: MCP may prepare immutable `MaintenanceAction` requests and return read-only status only; authorization, permit creation, execution, readback, audit, and recovery are local CLI-only.
- Q: Is recall scope scene/cue/snippet or a subset? -> A: Scene, cue, and snippet recall are all in scope once each family passes independent capability-gated validation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persistent Server-Owned Session and Honest Host Approval (Priority: P1)

As an engineer, I want the bridge to keep a single authoritative runtime context during the MCP session, so host approval, runtime mode, and write authority cannot drift between tools.

**Why this priority**: Without a single server-owned session, every later read, write, and verification rule can become inconsistent.

**Independent Test**: Start the bridge, inspect session-backed state, invoke a read tool, and confirm the same server-owned context owns the approval boundary for a sensitive write invocation.

**Acceptance Scenarios**:

1. **Given** a running MCP session, **When** multiple tools are called, **Then** they all observe the same server-owned runtime state.
2. **Given** a sensitive write is requested, **When** the host confirms the tool invocation, **Then** approval is represented by the confirmed invocation and not by a model-supplied flag.

### User Story 2 - Fail-Closed Writes Bound to Real Runtime State (Priority: P1)

As an engineer, I want writes to be denied whenever the endpoint, firmware, identity, snapshot, or acceptance evidence is not valid, so the bridge never writes against an untrusted state.

**Why this priority**: This is the primary safety gate for all state-changing behavior.

**Independent Test**: Alter the endpoint identity, stale the snapshot, or remove the acceptance record and confirm every attempted write is denied with zero console writes.

**Acceptance Scenarios**:

1. **Given** a mismatched endpoint or identity, **When** a write is attempted, **Then** the bridge denies the write before transmission.
2. **Given** incomplete acceptance evidence or stale state, **When** a write is attempted, **Then** the bridge fails closed and records the denial.

### User Story 3 - Protocol-Faithful Registry and Codecs (Priority: P1)

As an engineer, I want the bridge to encode and decode console values according to the approved protocol reference, so reads and writes reflect the real console behavior.

**Why this priority**: Correct protocol behavior is the foundation for all later read, write, and verification features.

**Independent Test**: Read a value with a documented discrete table or pseudo-log mapping and verify the displayed value, raw value, and normalized comparison match the protocol registry.

**Acceptance Scenarios**:

1. **Given** a registered path with a documented value grid, **When** it is encoded or decoded, **Then** the result matches the registry and the console's display rules.
2. **Given** an unsupported or ambiguous writable entry, **When** it is validated, **Then** it is rejected rather than accepted as a placeholder.

### User Story 4 - Complete Read-Only Console Inspection (Priority: P1)

As an engineer, I want to inspect the full supported console state, so the bridge can explain the console without manual page-by-page inspection.

**Why this priority**: The read surface feeds every analysis, recommendation, snapshot, and verification flow.

**Independent Test**: Request the supported channel, bus, matrix, main, DCA, headamp, routing, clock, meter, and RTA views and confirm they return real structured data for the declared scope.

**Acceptance Scenarios**:

1. **Given** a supported console or emulator, **When** the read surface is queried, **Then** all declared domains return structured results.
2. **Given** a firmware or path gap, **When** a read is requested, **Then** the result explicitly marks completeness and missing evidence.

### User Story 5 - Trusted Stored Snapshots and Conflict Baselines (Priority: P1)

As an engineer, I want snapshots to be stored, validated, and bound to proposals, so conflicts are detected against real console history rather than model memory.

**Why this priority**: Snapshots are the baseline for safe writes, conflict detection, and rollback.

**Independent Test**: Capture a snapshot, modify the console manually, and confirm the stored baseline detects the conflict before execution proceeds.

**Acceptance Scenarios**:

1. **Given** a stored snapshot, **When** a proposal references it, **Then** the snapshot is validated before any action is allowed.
2. **Given** a manual console change after snapshot capture, **When** the proposal executes, **Then** the conflict is detected and the write is rejected.

### User Story 6 - Complete R1-R3 Proposal, Execute, Readback, and Rollback (Priority: P1)

As an engineer, I want bounded R1-R3 changes to move through proposal, confirmation, execution, verification, and rollback, so normal writes remain safe and recoverable.

**Why this priority**: This is the core normal write workflow for the product.

**Independent Test**: Propose a bounded fader or mute change, confirm it, verify the readback, and confirm rollback restores the previous state if verification fails.

**Acceptance Scenarios**:

1. **Given** a valid proposal and fresh snapshot, **When** the write is confirmed, **Then** the change is applied, read back, audited, and compared.
2. **Given** a failed verification or mismatch, **When** rollback is safe, **Then** only the affected parameters are restored.

### User Story 7 - Independent Proposal Verification (Priority: P2)

As an engineer, I want proposals to be re-read against the live console before they are accepted, so approval status alone does not imply correctness.

**Why this priority**: Verification must be separate from proposal creation and approval.

**Independent Test**: Create a proposal, change the console, and confirm verification reports mismatches with the expected, encoded, and normalized values.

**Acceptance Scenarios**:

1. **Given** a stored proposal, **When** verification runs, **Then** the affected paths are re-read from the bound endpoint.
2. **Given** a mismatch or stale path, **When** verification completes, **Then** the result includes the mismatch evidence and audit record.

### User Story 8 - Controlled R4 Maintenance Authorization (Priority: P2)

As an engineer, I want a separate, fail-closed maintenance path for destructive or break-glass actions, so the normal MCP surface stays safe while maintenance remains possible under explicit local control.

**Why this priority**: Maintenance is intentionally separate from normal writes and must not be implied by normal approval.

**Independent Test**: Attempt an R4 action without an exact permit and confirm it is denied; then provide the valid maintenance authorization path and confirm only the permitted action can proceed.

**Acceptance Scenarios**:

1. **Given** an R4 request without a valid permit, **When** it is submitted, **Then** it is denied with zero writes.
2. **Given** a valid local permit and matching digest, **When** the request executes, **Then** it follows the separate maintenance boundary and consumes the permit once.

### User Story 9 - Protocol-Faithful Fake M32 Validation (Priority: P2)

As an engineer, I want a faithful test double for the supported console surface, so automated validation can exercise realistic OSC behavior without pretending to be hardware.

**Why this priority**: The fake console is the main deterministic test harness for development and regression coverage.

**Independent Test**: Run the read and write suite against the Fake M32 and confirm it returns documented replies, detects malformed behavior, and preserves deterministic results.

**Acceptance Scenarios**:

1. **Given** a supported path, **When** the Fake M32 is queried, **Then** it returns protocol-faithful values and response shapes.
2. **Given** an unsupported path, **When** it is queried, **Then** the gap is explicit rather than silently accepted.

### User Story 10 - External Emulator Validation (Priority: P2)

As an engineer, I want emulator-backed validation to prove behavior against a separate external target, so the bridge can demonstrate interoperability beyond the fake server.

**Why this priority**: Emulator validation is an important intermediate evidence tier before physical hardware acceptance.

**Independent Test**: Connect to the emulator, execute the declared non-destructive read and write set, and confirm unsupported capabilities are reported explicitly.

**Acceptance Scenarios**:

1. **Given** a supported emulator target, **When** the bridge runs the emulator matrix, **Then** supported paths pass and unsupported paths are reported as unsupported.
2. **Given** a successful emulator run, **When** results are recorded, **Then** they never establish hardware verification.

### User Story 11 - Physical M32 Acceptance (Priority: P2)

As an engineer, I want a physical acceptance workflow with signed evidence, so hardware verification only becomes true from the exact real console profile.

**Why this priority**: Physical hardware remains the final truth source for release readiness and hardware verification.

**Independent Test**: Perform the read-only acceptance suite on the physical M32, then run the isolated safe write and recovery checks, and confirm the resulting acceptance record binds to the exact hardware profile.

**Acceptance Scenarios**:

1. **Given** the physical console and acceptance suite, **When** the read-only matrix passes, **Then** it records hardware evidence for the exact endpoint profile.
2. **Given** an emulator or Fake M32 result, **When** acceptance is evaluated, **Then** hardware verification remains false.

### User Story 12 - Native Clean-Host and Release-Asset Validation (Priority: P3)

As an engineer, I want clean-host and published-asset validation across supported desktop platforms, so release readiness is not inferred from repository checkout alone.

**Why this priority**: The release must work on real user machines, not only on the development tree.

**Independent Test**: Install, update, repair, and initialize on clean desktop hosts and verify the published release assets behave the same way as the checked-in source.

**Acceptance Scenarios**:

1. **Given** a clean supported desktop host, **When** the release assets are installed and started, **Then** the expected runtime, health, and stdio behaviors are present.
2. **Given** a published asset failure or version mismatch, **When** it is validated, **Then** the release gate fails.

### User Story 13 - Documentation, Legal, and Release Governance (Priority: P3)

As an engineer, I want the public documentation and release governance to reflect only validated behavior, so users and reviewers can trust the release process.

**Why this priority**: Documentation and governance must stay truthful to the implemented state.

**Independent Test**: Review the README, runbook, notices, versioning policy, and release guidance against the current validated feature set and confirm they do not overclaim.

**Acceptance Scenarios**:

1. **Given** the release documentation set, **When** it is reviewed, **Then** it matches the implemented behavior and current governance.
2. **Given** a historical quickstart or superseded clause, **When** it is retained, **Then** it is clearly marked historical.

## Edge Cases

- A snapshot exists but was captured against a different endpoint or firmware version.
- The console returns a supported path for some channels but not all declared channels.
- A proposal becomes stale because a manual change occurs before execution.
- An emulator supports a read path but not the corresponding write path.
- A maintenance permit expires after preparation but before execution.
- A recovery step succeeds for some affected paths but not all affected paths.
- A readback matches raw value but not the documented normalized display value.
- A supported action is requested in LIVE or EMERGENCY mode.
- A hardware acceptance record exists for a similar console profile but not the exact endpoint identity.
- A release asset works on a checked-in source tree but not on a clean host.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST maintain one server-owned runtime context for the lifetime of the MCP session.
- **FR-002**: The product MUST treat live console evidence as authoritative over model memory, chat history, or stale snapshots.
- **FR-003**: The product MUST keep normal read and write actions separate, with explicit approval boundaries for sensitive changes.
- **FR-004**: The product MUST ensure that approval is represented by the confirmed tool invocation, not by a model-supplied approval flag.
- **FR-005**: The product MUST expose only bounded, typed, purpose-specific tools on the normal MCP surface.
- **FR-006**: The product MUST reject placeholder or partially implemented tools from the release-ready tool list.
- **FR-007**: The product MUST use a machine-readable, versioned protocol registry as the source of truth for supported paths and values.
- **FR-008**: The product MUST record source reference, direction, value type, ranges, discrete tables, risk class, hardware sensitivity, readback strategy, rollback strategy, and evidence for every writable protocol entry.
- **FR-009**: The product MUST reject ambiguous, overlapping, or undocumented writable protocol templates.
- **FR-010**: The product MUST encode and decode console values using protocol-faithful representations for the supported surface.
- **FR-011**: The product MUST preserve the documented distinction between raw protocol values and user-facing display values.
- **FR-012**: The product MUST support complete read coverage for the declared channel, bus, matrix, main, DCA, headamp, routing, clock, meter, and RTA domains.
- **FR-013**: The product MUST label unsupported, incomplete, stale, or emulator-only results explicitly.
- **FR-014**: The product MUST persist snapshots with identity, endpoint, firmware, completeness, checksum, and provenance.
- **FR-015**: The product MUST reject snapshot references that are not backed by stored content.
- **FR-016**: The product MUST bind proposals to fresh snapshots and reject conflicts when the console changes before execution.
- **FR-017**: The product MUST execute normal R1-R3 changes only through the full proposal, confirmation, execution, readback, audit, and rollback flow.
- **FR-018**: The product MUST deny any write when the endpoint, identity, firmware, capability profile, snapshot, or environment-specific execution evidence is invalid; writes against physical hardware additionally require an exact valid Hardware `AcceptanceRecord` for that endpoint profile.
- **FR-018a**: Fake M32 and emulator test-write evidence MUST authorize only explicitly bounded test execution scoped to that environment and MUST NEVER set `hardware_verified=true`.
- **FR-019**: The product MUST keep write denials from sending any OSC write packets.
- **FR-020**: The product MUST append an audit record for every attempted write, including denials.
- **FR-021**: The product MUST expose a separate maintenance boundary for controlled R4 actions.
- **FR-022**: The product MUST require a single-use, short-lived local permit for each R4 execution attempt.
- **FR-023**: The product MUST keep R4 unavailable in LIVE and EMERGENCY modes.
- **FR-024**: The product MUST prevent the normal MCP host approval boundary from authorizing R4 by itself.
- **FR-025**: The product MUST record a signed or hashed acceptance record before any hardware verification claim is made.
- **FR-026**: The product MUST keep emulator and Fake M32 evidence separate from hardware verification evidence.
- **FR-027**: The product MUST validate clean-host installs, updates, repairs, health checks, and published release assets before release readiness is declared.
- **FR-028**: The product MUST preserve existing truthful documentation and clearly mark historical or superseded quickstarts and clauses.
- **FR-029**: R4 authorization MUST occur outside MCP through a local interactive TTY flow that displays action, endpoint, identity, model, firmware, OSC path and typed arguments, current value or explicit not-applicable state for actions with no scalar current value, requested value, risk, expected effect, recovery action, digest, and expiry.
- **FR-030**: The local operator MUST approve R4 with `AUTHORIZE <ACTION_NAME> <LAST_8_DIGEST_CHARS>`, then pass a local six-digit challenge re-entry.
- **FR-031**: Non-interactive approval, piped approval input, environment-variable approval, wildcard authorization, batch authorization, permanent authorization, and `--yes` approval MUST be rejected.
- **FR-032**: A `MaintenancePermit` MUST be single-use, locally stored, and expire in at most 60 seconds by default.
- **FR-033**: Every `MaintenancePermit` MUST bind endpoint, console identity, model, firmware, capability profile, action digest, source commit, maintenance session, and operator identity.
- **FR-034**: A `MaintenancePermit` MUST be consumed after exactly one execution attempt, whether successful or failed.
- **FR-035**: The MCP surface MUST permit R4 preparation and read-only status only, and MUST NOT expose R4 execution or permit-submission tools.
- **FR-036**: R4 preparation through MCP MUST send zero OSC writes, create no permit, and enter no maintenance mode.
- **FR-037**: Scene, cue, and snippet recall MUST each be implemented as independently capability-gated R3 semantic operations with exact registry entries, scope preview, safes handling, snapshot binding, typed encoding, execution, readback verification, conflict detection, audit, recovery classification, Fake M32 coverage, emulator coverage where supported, and physical acceptance where required.
- **FR-038**: No recall family may remain registered as a placeholder or be described as release-ready before its complete validation gate passes.

### Security Requirements

- **SR-001**: The normal MCP surface MUST not expose raw OSC, generic setters, shell execution, or arbitrary path tools.
- **SR-002**: The product MUST enforce all blocking rules on the server side, not only in prompts or documentation.
- **SR-003**: The product MUST deny any request that would broaden scope outside the approved normal MVP surface unless the separate maintenance boundary applies.
- **SR-004**: The product MUST never treat emulator success as hardware verification.
- **SR-005**: The product MUST never mark production readiness true without exact release evidence and acceptance gates.
- **SR-006**: The product MUST not log secrets, tunnel credentials, or private configuration values in audit records.
- **SR-007**: The product MUST require exact action digests and exact target binding for R4 requests.
- **SR-008**: The product MUST fail closed on malformed packets, stale state, unknown firmware, or capability mismatch.

### Key Entities

- **Proposal**: A bounded, reviewable request to change console state. Key attributes include proposal id, digest, source snapshot, affected paths, target values, risk class, expiration, rollback plan, and audit reference.
- **Snapshot**: A stored baseline of console state. Key attributes include snapshot id, endpoint, identity, model, firmware, completeness, checksum, capture time, and provenance.
- **RegistryEntry**: A protocol definition record for a supported path. Key attributes include path template, value type, ranges, direction, discrete tables, risk default, readback rules, rollback rules, and evidence source.
- **ReadbackRecord**: The result of a post-write or verification read. Key attributes include expected value, raw readback, normalized readback, tolerance, match status, and audit id.
- **MaintenanceAction**: A controlled R4 request object. Key attributes include action type, target, arguments, expected effect, recovery plan, digest, and permit binding.
- **MaintenancePermit**: A one-time authorization token for a maintenance action. Key attributes include operator identity, endpoint, firmware, capability profile, source commit, expiration, and consumed status.
- **AcceptanceRecord**: A signed or hashed hardware evidence bundle. Key attributes include endpoint identity, model, firmware, acceptance suite version, pass/fail outcomes, and evidence timestamp.
- **AuditEvent**: A durable record of a read, write, denial, verification, or maintenance attempt. Key attributes include actor, host, action, result, timestamp, and latency.
- **CapabilityProfile**: A summary of supported and unsupported console families and behaviors. Key attributes include declared scope, gaps, environment label, and validation status.

## Assumptions

- The current constitution and root PLAN are authoritative for governance and scope.
- The project continues to use the existing local, user-controlled MCP host model for the normal MVP surface.
- Exact native release-supported OS versions will be selected during planning and release validation against the currently maintained desktop platforms.
- Release legal wording and ownership for proprietary notices will be finalized before release packaging.
- Physical hardware acceptance will use the exact production console and firmware available during the acceptance run.
- Snapshot, registry, and acceptance records are stored locally and are expected to be user-owned artifacts.
- The maintenance boundary is separate from the normal proposal path and must not be inferred from normal write behavior.
- Scene, cue, and snippet recall are all in scope, and each family must pass independent capability-gated validation before release-readiness claims.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every registered MCP tool has a real handler and contract coverage; zero placeholder handlers remain.
- **SC-002**: Every supported writable registry entry has encoding, decoding, readback comparison, policy classification, and rollback or recovery classification.
- **SC-003**: Every successful write has a matching typed readback and audit record.
- **SC-004**: Every denied write produces zero console writes.
- **SC-005**: Every R3 write proves a valid bound snapshot before execution.
- **SC-006**: Every R4 attempt without an exact valid local permit is denied with zero writes.
- **SC-007**: Read coverage spans channels 01-32 and all declared aux, bus, matrix, main, DCA, headamp, clock, meter, and RTA domains.
- **SC-008**: External emulator tests report unsupported capabilities explicitly and never use silent skips as passes.
- **SC-009**: Clean-host and published-asset validation pass before release candidate approval.
- **SC-010**: Hardware verification remains false until the exact acceptance evidence for the exact endpoint profile passes.
- **SC-011**: Production readiness remains false until all required release and acceptance gates pass.
- **SC-012**: Historical or superseded governance clauses are clearly marked and never presented as current authority.

## Readiness Notes

- All clarification markers are resolved. This specification is ready for
  planning after the governance consistency gate passes.
- Implementation tasks are intentionally omitted from this artifact.
