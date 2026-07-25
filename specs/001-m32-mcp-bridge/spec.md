# Feature Specification: M32 MCP Bridge MVP

**Feature Branch**: `001-m32-mcp-bridge`

**Created**: 2026-07-19

**Status**: Draft

**Input**: User description: "Create the MVP specification for the M32 AI MCP Bridge from PLAN.md and the project constitution."

## Problem Statement

Sound engineers using a Midas M32 console cannot safely ask Claude or ChatGPT to
read, analyze, and control the console directly. A model can misunderstand stale
state, hallucinate unsupported paths, or issue unsafe changes unless the bridge
constrains every action with live console evidence, explicit human approval,
readback verification, audit records, and rollback behavior.

The MVP provides a safe bridge between the existing AI host conversation and the
console or emulator. Claude/ChatGPT are the user interface. The MVP does not add
a custom chat application, mixer frontend, WebUI, or AI backend.

## Clarifications

### Session 2026-07-19

- Q: What is the MVP scope of `EMERGENCY` mode? -> A: `EMERGENCY` locks all
  writes and stops automation only. It allows no mute, rollback, or console write
  through AI. Manual console control remains available. Pending proposals are
  cancelled. Exiting `EMERGENCY` returns to `OBSERVE` first and requires
  reconciliation before any write can be enabled.

## Goals

- Enable an engineer to ask Claude/ChatGPT for current console status, routing,
  channel, bus, meter, RTA, clock, and sync information using structured bridge
  results.
- Treat live console or emulator replies as the authoritative state source, with
  stale, unsupported, emulator-only, and hardware-unverified values labeled.
- Detect manual console or external emulator changes, including a gain change
  from `+10.0 dB` to `+6.0 dB`, and surface the newer value with evidence.
- Produce evidence-based event preflight findings and setup recommendations
  without applying changes automatically.
- Separate change proposals from execution, require human approval for writes,
  verify every successful write by readback, audit every attempt, and support
  targeted rollback.
- Reject execution when a manual change or stale state creates a conflict.
- Validate behavior with deterministic tests, a project-owned Fake M32, an
  external X32 Emulator, MCP host checks, and mandatory later hardware acceptance.

## Actors

- **Engineer**: Supervises the event, asks questions in Claude/ChatGPT, approves
  or rejects sensitive tool calls, and retains manual console control.
- **Claude/ChatGPT Host**: The existing conversation interface that lists and
  calls bridge tools; it supplies the model and host confirmation surface.
- **Bridge**: The local control boundary that reads console state, enforces
  policy, manages proposals, performs readback, records audit entries, and
  blocks unsafe actions.
- **Console or Emulator**: The configured M32/X32 endpoint that supplies live or
  emulated state and accepts only approved, allowlisted writes.
- **External Manual Actor**: A physical engineer gesture or external client that
  changes console/emulator state outside the pending proposal.

## MVP In Scope

- Local connection to a real M32 or compatible X32/M32 emulator endpoint.
- Runtime identity, firmware, model, capability, and environment discovery.
- Supported state snapshots and live state synchronization.
- Manual/external change detection for fader, mute, headamp, trim, EQ,
  dynamics, send, routing, and supported related paths.
- Read tools for console overview, channels, buses, routing, clock/sync, meters,
  RTA, snapshots, changes, comparisons, and signal tracing.
- Analysis tools for event preflight, gain staging, routing, processing, RTA,
  and setup recommendations.
- Explicit measurement microphone role, routing constraints, and phantom policy
  in the event profile.
- Proposal-based safe writes with human approval, conflict rejection, readback,
  audit, and targeted rollback.
- Claude Desktop as the first operational host and ChatGPT as an optional host
  after the local MVP is stable and a secure host transport is available.
- Emulator, MCP host, failure-injection, cross-platform, and later hardware
  acceptance validation.
- A small domain knowledge pack for signal flow, SOPs, vocabulary, and safety
  guidance, with security enforced by bridge policy rather than prompts alone.

## Explicitly Out of Scope

- Custom chat application, full mixer frontend, M32-Edit clone, or general WebUI.
- Local or cloud AI provider adapters or model billing integrations.
- USB 32x32 PCM capture, simultaneous multi-channel spectra, automatic feedback
  suppression, automatic room/speaker delay alignment, or impulse analysis.
- Additional hardware requirements such as Pi, ESP32, Stream Deck, Companion
  runtime, mobile apps, or general application hosting. An approved outbound
  Secure MCP Tunnel is the only optional connectivity exception for ChatGPT.
- OpenX32 installation, firmware modification, or reverse engineering of the
  console operating system.
- Public exposure of OSC, port forwarding to the console, operating-system
  network bridging, Internet Connection Sharing, or packet forwarding between
  the Internet-facing interface and the console-control interface.
- Automatic phantom-power enablement.
- AI-driven sample-rate or clock-source changes.
- SD-card formatting, console shutdown, or firmware operations through AI.
- Claims that emulator success proves real hardware compatibility.
- Production or live-use readiness before hardware acceptance passes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect and Prove Live State (Priority: P1)

As an engineer, I want the bridge to connect to an emulator or M32 and prove
that returned values come from that endpoint, so I can trust later AI answers.

**Why this priority**: All later reads, analysis, and writes depend on knowing
that state is live, current, labeled, and sourced from the configured endpoint.

**Independent Test**: Connect to a reachable emulator, read Channel 1 headamp
gain as `+10.0 dB`, change it outside the bridge to `+6.0 dB`, and confirm the
next bridge result returns `+6.0 dB` with a newer revision, a non-stale timestamp,
and `source=osc_event` or `source=reconciliation_read`.

**Acceptance Scenarios**:

1. **Given** a reachable endpoint in `OBSERVE` mode, **When** the engineer asks
   whether the console is connected, **Then** the bridge returns identity,
   environment, firmware/capability status, freshness, write lock, and the
   evidence source.
2. **Given** Channel 1 headamp gain is reported as `+10.0 dB`, **When** an
   external manual change sets it to `+6.0 dB`, **Then** the bridge reports
   `+6.0 dB`, a newer revision, observed time, and a non-stale source label.
3. **Given** a value is unsupported, stale, emulator-only, or hardware-unverified,
   **When** it appears in a result, **Then** the result labels that status
   explicitly and does not present it as verified hardware state.

---

### User Story 2 - Query Console State Through Claude/ChatGPT (Priority: P1)

As an engineer, I want to ask Claude or ChatGPT about channels, buses, routing,
clock, meters, RTA, and processing, so I can inspect the console without manually
checking every console page.

**Why this priority**: Read-only host access is the first useful MVP workflow and
must be correct before diagnostics or writes can be trusted.

**Independent Test**: Use a host conversation to call read-only bridge tools
against the emulator and verify the host receives structured results that
accurately separate headamp gain, digital trim, fader, routing, clock/sync,
meter positions, RTA source, freshness, and environment labels.

**Acceptance Scenarios**:

1. **Given** the bridge is connected in `OBSERVE`, **When** the engineer asks for
   Channel 1, **Then** the result distinguishes headamp gain, channel trim, and
   fader, and includes units, display values, observed time, source, freshness,
   support status, and revision.
2. **Given** the engineer asks for routing, clock, meters, and RTA, **When** the
   host calls read tools, **Then** outputs are structured objects rather than
   unstructured logs and include clock rate/source/mode, AES50 A/B state,
   expansion-card sync, named meter positions, and the selected RTA source.
3. **Given** the bridge is in `OBSERVE`, **When** the host calls any read or
   analysis workflow, **Then** no state-changing console packet is sent.

---

### User Story 3 - Event Preflight and Evidence-Based Setup Advice (Priority: P1)

As an engineer, I want Claude/ChatGPT to inspect the current console state and
return blockers, warnings, advisories, and best-practice setup recommendations,
so I can prepare the event without accepting unsupported model guesses.

**Why this priority**: Preflight identifies unsafe or broken event conditions
before any write workflow is introduced.

**Independent Test**: Seed an emulator scene with clock, sync, routing, gain,
mute, processing, and protected-path issues; run event preflight; confirm the
findings include severity, evidence paths, observed values, source/confidence,
freshness, and recommended next action, while recommendations remain separate
from executable operations.

**Acceptance Scenarios**:

1. **Given** an event profile and reachable endpoint, **When** preflight runs,
   **Then** it inspects identity, firmware, clock rate/source/mode, AES50 A/B,
   expansion-card sync, routing, gain structure, processing, meters, current RTA
   source, measurement microphone, and protected paths.
2. **Given** required clock or digital sync fails, **When** readiness is
   evaluated, **Then** event readiness and `WriteReady` are blocked until the
   issue is resolved and revalidated.
3. **Given** a recommendation is produced, **When** it is shown to the engineer,
   **Then** it cites console evidence and remains non-executable until converted
   into a separate proposal.

---

### User Story 4 - Create a Safe Proposal Separate From Execution (Priority: P1)

As an engineer, I want Claude/ChatGPT to create a proposed change without
executing it, so I can inspect intent, risk, affected paths, bounds, and rollback
values before approving any control action.

**Why this priority**: Proposal separation is the safety boundary that prevents
analysis from becoming action.

**Independent Test**: Ask the host to create a safe fader proposal; verify the
proposal has an ID, digest, base revision, expiration, operations, risk summary,
required confirmation, affected paths, before/requested values, bounds, rollback
values, and no write occurs.

**Acceptance Scenarios**:

1. **Given** a fresh state revision, **When** the engineer asks for a safe fader
   change proposal, **Then** the bridge creates an expiring proposal and sends no
   state-changing console write.
2. **Given** a requested action targets a raw path or prohibited operation,
   **When** proposal validation runs, **Then** the bridge rejects it and creates
   no executable proposal.
3. **Given** a proposal includes R3 headamp, routing, recall, or bulk work,
   **When** the runtime mode is not `SOUNDCHECK`, **Then** the proposal cannot be
   executed in the MVP.

---

### User Story 5 - Execute Only After Human Approval, Readback, Audit, and Rollback (Priority: P1)

As an engineer, I want a proposal to execute only after explicit host
confirmation, then be read back, audited, and rollback-capable, so I retain
control and can recover from failed verification.

**Why this priority**: This is the core safe-write loop for the MVP.

**Independent Test**: Create a fresh fader proposal, approve the host tool call,
execute it, verify readback matches using the console display grid, confirm an
audit record exists, then roll back and verify the original value is restored.

**Acceptance Scenarios**:

1. **Given** a valid proposal and explicit host confirmation, **When** execution
   starts, **Then** the bridge re-checks policy, mode, risk, allowlist, bounds,
   rate limits, freshness, proposal status, and snapshot requirements before any
   write is sent.
2. **Given** a write succeeds, **When** readback completes, **Then** the returned
   value matches the console's real resolution/grid and the transaction is
   marked verified.
3. **Given** readback does not match, **When** verification fails, **Then** the
   transaction is marked failed, an audit record is appended, and targeted
   rollback is attempted when safe.
4. **Given** rollback is requested for a verified proposal, **When** rollback
   executes, **Then** only the affected proposal parameters are targeted before
   any broader recovery is considered.

---

### User Story 6 - Reject Manual Change Conflicts (Priority: P1)

As an engineer, I want execution to fail if I manually change the console after a
proposal is created, so automation never overwrites my current manual gesture.

**Why this priority**: Manual console control must always win over automation.

**Independent Test**: Create a proposal against a target fader, change that same
target outside the bridge before execution, then approve execution and confirm
the result is `CONFLICT` and zero target writes are sent.

**Acceptance Scenarios**:

1. **Given** a proposal was created at revision N, **When** the affected state
   changes before execution, **Then** execution is rejected as conflicted.
2. **Given** a proposal is expired, already used, modified, missing, or based on
   stale state, **When** execution is requested, **Then** execution is rejected
   and no target write is sent.
3. **Given** a conflict rejection occurs, **When** the engineer reviews the
   result, **Then** the response identifies the conflicting path, previous value,
   current value, revision, and source.

---

### User Story 7 - Measurement Microphone Awareness (Priority: P2)

As an engineer, I want the event profile to explicitly identify the measurement
microphone and its allowed uses, so setup advice protects it from normal channel
heuristics and unsafe phantom behavior.

**Why this priority**: Measurement microphone behavior improves event analysis
but depends on event-specific profile data and is less foundational than basic
read/write safety.

**Independent Test**: Configure a measurement microphone channel, run event
preflight and recommendations, and confirm the channel is excluded from Main
recommendations, eligible as an RTA source when allowed, and never causes
automatic phantom enablement.

**Acceptance Scenarios**:

1. **Given** an event profile defines a measurement microphone role, **When**
   preflight runs, **Then** the bridge uses that explicit role and does not infer
   it from the channel name alone.
2. **Given** the measurement microphone has protected Main or monitor sends,
   **When** recommendations are generated, **Then** those sends remain protected
   unless the event profile explicitly permits otherwise.
3. **Given** phantom appears required by the microphone device, **When** advice
   is generated, **Then** the system may warn or recommend manual action but does
   not enable phantom power through AI.

---

### User Story 8 - RTA-Assisted Soundcheck (Priority: P2)

As an engineer, I want Claude/ChatGPT to read and interpret the current RTA
source during soundcheck and optionally scan configured sources safely, so
spectral observations stay tied to actual source evidence.

**Why this priority**: RTA assistance is valuable during soundcheck but must not
misrepresent meter data or disrupt source settings.

**Independent Test**: Read current RTA data and source identity; then run an
allowed sequential scan in `SOUNDCHECK` and verify the original RTA source is
restored on success, failure, or cancellation.

**Acceptance Scenarios**:

1. **Given** RTA data is available, **When** the engineer asks for RTA analysis,
   **Then** the response includes the selected RTA source and acquisition
   settings and does not claim simultaneous per-channel spectra.
2. **Given** the RTA source is unknown, **When** analysis is requested, **Then**
   the response labels the source as unknown and limits conclusions accordingly.
3. **Given** sequential RTA scanning is requested, **When** the mode is not
   `SOUNDCHECK`, **Then** scanning is rejected.
4. **Given** scanning starts in `SOUNDCHECK`, **When** it ends or is interrupted,
   **Then** the original RTA source is restored or the failure is reported.

---

### User Story 9 - Recover Safely From Connection Failure and Emergency Lock (Priority: P2)

As an engineer, I want writes disabled during disconnection and restored only
after identity and state reconciliation, and I want an emergency mode that stops
automation without allowing AI writes, so stale or unsafe state cannot drive
control actions.

**Why this priority**: Connection loss is expected in UDP/local-network testing
and emergency lockout must fail closed, but recovery comes after the core
read/write workflows.

**Independent Test**: Stop the emulator while connected, confirm writes lock
within one second of heartbeat failure, restart it, and confirm identity plus
critical state reconciliation complete before writes are re-enabled. Enter
`EMERGENCY`, confirm pending proposals are cancelled and no AI mute, rollback, or
console write can execute, then exit to `OBSERVE` and require reconciliation
before writes can be enabled.

**Acceptance Scenarios**:

1. **Given** the bridge is connected, **When** heartbeat or replies are lost,
   **Then** state becomes disconnected or stale and all writes are disabled.
2. **Given** the target returns, **When** reconnect completes, **Then** identity
   and critical state reconciliation must pass before writes can be restored.
3. **Given** malformed, delayed, duplicated, dropped, or out-of-order packets
   occur, **When** state is updated, **Then** the bridge preserves defensive
   parsing, freshness, source labels, and fail-closed write behavior.
4. **Given** `EMERGENCY` mode is activated, **When** the host or model requests
   mute, rollback, or any console write, **Then** the bridge rejects the request,
   cancels pending proposals, keeps manual console control available, and keeps
   all AI writes locked.
5. **Given** `EMERGENCY` mode is exited, **When** the bridge resumes operation,
   **Then** it enters `OBSERVE` first and requires identity plus critical state
   reconciliation before any write mode can be enabled.

### Edge Cases

- UDP packets are lost, delayed, duplicated, malformed, truncated, or delivered
  out of order.
- State is stale, unknown, or based on a partial snapshot.
- Firmware is unknown, capabilities differ, or a requested path is unsupported.
- The connection drops while a proposal is pending, executing, or awaiting
  readback.
- A manual console or external emulator change occurs after proposal creation.
- Readback differs from the requested value or from the console display grid.
- Targeted rollback fails or only partially restores affected values.
- The external emulator behaves differently from the real hardware.
- RTA source identity is unknown or changes during soundcheck.
- AES50 or expansion-card sync fails during event preflight.
- Clock rate/source is unsuitable for the event and must be corrected manually.
- A host attempts to call write tools without explicit confirmation or after an
  operator configured permanent approval.
- A model attempts to invent a raw OSC path, R4 operation, or arbitrary setter.
- A hardware-unverified endpoint returns plausible values that must not be
  represented as hardware readiness.
- `EMERGENCY` mode is entered while proposals are pending or execution is
  requested.
- `EMERGENCY` mode is exited before identity or critical state reconciliation
  has completed.

## Requirements *(mandatory)*

### Functional Requirements

#### Connection and Discovery

- **FR-001**: The bridge MUST connect to a configured OSC target and UDP port on
  the private console-control network.
- **FR-002**: The bridge MUST support `emulator`, `hardware-unverified`, and
  `hardware-verified` environment labels.
- **FR-003**: The bridge MUST query identity, model, firmware, and capability
  information at startup.
- **FR-004**: The bridge MUST renew the console remote-change subscription
  before the subscription expires.
- **FR-005**: The bridge MUST detect heartbeat or reply loss and transition to a
  disconnected, write-locked state.
- **FR-006**: The bridge MUST reconnect with bounded backoff and perform identity
  plus state reconciliation before restoring writes.

#### State and Telemetry

- **FR-010**: The bridge MUST build a typed snapshot of all supported console
  containers.
- **FR-011**: The bridge MUST maintain a live state cache with monotonic revision
  numbers.
- **FR-012**: Every cached field MUST include value, display value, source,
  observed time, freshness, support status, revision, and environment label.
- **FR-013**: The bridge MUST process remote-change notifications and selective
  polling or reconciliation reads.
- **FR-014**: The bridge MUST preserve the distinction between headamp gain,
  channel digital trim, and channel fader.
- **FR-015**: The bridge MUST decode supported meter banks and identify each
  value's signal position.
- **FR-016**: The bridge MUST report RTA data only with the selected RTA source
  and acquisition settings.
- **FR-017**: The bridge MUST expose clock rate/source/mode, expansion-card sync,
  and AES50 A/B state.

#### Analysis

- **FR-020**: Deterministic preflight rules MUST run before model-written prose
  or recommendations are trusted.
- **FR-021**: Findings MUST include severity, evidence paths, observed values,
  confidence or source, freshness, and recommended next action.
- **FR-022**: Recommendations MUST remain separate from executable operations.
- **FR-023**: The bridge MUST NOT represent per-channel meters as per-channel
  frequency spectra.
- **FR-024**: Sequential RTA scanning, if enabled, MUST be restricted to
  `SOUNDCHECK`, save original settings, and restore them on success, failure, or
  cancellation.
- **FR-025**: The event profile MUST explicitly identify the measurement
  microphone role, routing constraints, and phantom policy.

#### Safe Write

- **FR-030**: Every write MUST originate from a stored proposal with an ID,
  digest, snapshot revision, expiration, operations, risks, and rollback values.
- **FR-031**: Execution MUST reject missing, expired, already-used, modified, or
  state-conflicted proposals.
- **FR-032**: The policy decision MUST check operation risk, runtime mode, path
  allowlist, bounds, rate limits, and required snapshot.
- **FR-033**: Writes MUST be serialized per affected console resource to prevent
  overlapping changes.
- **FR-034**: Every write MUST be read back with retry and bounded timeout.
- **FR-035**: A failed verification MUST produce a failed transaction and
  targeted rollback when safe.
- **FR-036**: Headamp, routing, recall, bulk, and talkback configuration
  operations MUST execute only in `SOUNDCHECK` and MUST require a snapshot,
  explicit high-risk enablement, and host confirmation. Momentary talkback
  activation and talkback configuration MUST be treated as separate actions;
  configuration and destination changes are R3 and `SOUNDCHECK`-only, while
  momentary activation is bounded by the active runtime policy.
- **FR-037**: Phantom enable, sample-rate or clock change, firmware, shutdown,
  and SD format MUST remain blocked in the MVP.
- **FR-038**: Physical or manual changes MUST invalidate conflicting proposals.

#### MCP and Host Integration

- **FR-040**: The primary host path MUST allow Claude Desktop to use the bridge
  locally through MCP.
- **FR-041**: The optional secondary host path MUST be disabled by default and
  bound only to loopback or private interfaces when enabled.
- **FR-042**: ChatGPT connectivity MUST use Secure MCP Tunnel or another approved
  outbound secure tunnel; the OSC endpoint MUST never be public.
- **FR-043**: Read tools MUST declare read-only behavior; write tools MUST
  declare destructive or sensitive behavior for host confirmation.
- **FR-044**: Tool outputs MUST be structured JSON-compatible objects, not
  unstructured console logs.
- **FR-045**: No local AI provider integration is required; the MCP host supplies
  the model and conversation.

#### Audit and Recovery

- **FR-050**: Audit records MUST be append-only JSONL during the MVP.
- **FR-051**: Sensitive values and secrets MUST NOT be logged.
- **FR-052**: Snapshots MUST be JSON files with schema version, identity,
  firmware, time, checksum, and completeness status.
- **FR-053**: The operator control surface MUST support health/doctor, snapshot,
  verify-connection, and audit-tail operations.
- **FR-054**: Emergency write lock MUST be available through operator controls
  and take effect without restarting the console. `EMERGENCY` mode MUST lock all
  AI-initiated writes, stop automation, cancel pending proposals, and allow no
  mute, rollback, or console write through AI. Manual console control remains
  available. Exiting `EMERGENCY` MUST return the bridge to `OBSERVE` first and
  require identity plus critical state reconciliation before any write can be
  enabled.

### Security and Governance Requirements

- **SG-001**: The console or emulator endpoint MUST be the authoritative source
  of operational state; model memory MUST NOT be authoritative.
- **SG-002**: Raw OSC tools, arbitrary path setters, shell execution, firmware
  actions, shutdown, SD format, phantom enable, and sample-rate setters MUST NOT
  exist in the MVP tool surface.
- **SG-003**: All state-changing operations MUST follow proposal -> human
  approval -> execution -> readback -> audit.
- **SG-004**: Manual console changes MUST take priority over automation.
- **SG-005**: R4 operations MUST remain blocked under direct tool calls,
  malformed proposals, and model-supplied custom paths.
- **SG-006**: Sample rate and clock source MUST be inspected during setup and
  preflight, but MUST NOT be changed by AI in the MVP.
- **SG-007**: Emulator results MUST NOT be documented or displayed as hardware
  verification.
- **SG-008**: Hardware acceptance MUST pass before the system claims production,
  live-use, or `hardware-verified` readiness.
- **SG-009**: Operating-system network bridging, Internet Connection Sharing,
  packet forwarding, port forwarding, and Internet-exposed OSC MUST remain
  disabled.
- **SG-010**: Unknown firmware, endpoint identity mismatch, capability mismatch,
  or malformed state replies MUST force a write-locked and hardware-unverified
  state. Writes MUST remain disabled until identity, capabilities, and critical
  state reconciliation pass.
- **SG-011**: Main LR/M/C paths MUST be protected by default. Main-level,
  processing, routing, or assignment changes MUST require an explicit proposal
  that identifies the affected Main paths and MUST NOT execute as an implicit
  side effect of another operation.
- **SG-012**: `EMERGENCY` mode MUST NOT grant any emergency write capability to
  AI. It is a write-lock and automation-stop mode only.

### Conceptual Entities

- **Console Identity**: The endpoint identity and verification state, including
  environment label, model, firmware, target address, capability profile, and
  verification time.
- **State Value**: A single observed console value with raw/native/display
  value, unit, revision, observed time, source, freshness, support status, and
  environment label.
- **Snapshot**: A bounded capture of supported console state with identity,
  firmware, time, checksum, schema version, and completeness status.
- **Proposal**: A stored, expiring, digest-protected set of operations based on a
  snapshot revision and containing risk summary, confirmation requirement, and
  rollback values.
- **Operation**: A typed, allowlisted action against a specific target with
  before value, requested value, bounds, risk level, reason, and rollback value.
- **Event Profile**: Event and venue context, channel/bus/output dictionary,
  expected topology, measurement microphone role, protected paths, mode-specific
  permissions, and known-good reference.
- **Audit Record**: Append-only record of an attempted write or rollback,
  including actor/host, console identity, proposal, old/requested/readback
  values, policy decision, result, latency, and rollback result.
- **Finding**: A deterministic diagnostic result with severity, evidence paths,
  observed values, source/confidence, freshness, and recommended next action.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manual or emulated fader, mute, or gain change is visible in
  state within `500 ms p95` under normal local network conditions.
- **SC-002**: Returned display values match the console's documented resolution;
  headamp comparisons respect the real gain grid.
- **SC-003**: A supported full snapshot completes within `5 seconds p95` on the
  local emulator and reports incomplete sections explicitly.
- **SC-004**: `100%` of write attempts have an audit record, including rejected
  operations.
- **SC-005**: `100%` of successful writes have matching readback verification.
- **SC-006**: `OBSERVE` mode sends no state-changing OSC packets in integration
  tests.
- **SC-007**: Every blocked R4 path remains blocked under direct tool calls,
  malformed proposals, and model-supplied custom paths.
- **SC-008**: A stale or disconnected state prevents all writes within `1 second`
  of detected heartbeat failure.
- **SC-009**: After the target returns, identity and critical state reconciliation
  complete before write unlock.
- **SC-010**: Proposal conflict tests send zero target writes after an external
  or manual state change.
- **SC-011**: The system correctly labels `emulator`, `hardware-unverified`, and
  `hardware-verified` in every status response.
- **SC-012**: Claude Desktop can list, call, and receive valid results from all
  MVP MCP tools.
- **SC-013**: The external X32 Emulator integration suite passes on at least the
  primary Windows development environment.
- **SC-014**: The final hardware acceptance suite demonstrates live manual
  gain/fader change detection before the project claims hardware readiness.

### Additional Release Gates

- Unit, Fake M32, MCP smoke, packaging, and startup tests MUST pass on Windows
  and macOS before the MVP is released.
- Hardware acceptance MUST pass before production or live deployment.
- Event readiness MUST remain blocked when required clock, AES50, or expansion
  sync checks fail.
- `EMERGENCY` mode MUST reject AI mute, rollback, and console write attempts,
  cancel pending proposals, exit to `OBSERVE`, and require reconciliation before
  writes can be re-enabled.

## Assumptions

- The engineer remains present for every sensitive write and does not configure
  permanent automatic approval for write tools.
- Claude Desktop is the first operational host; ChatGPT support is optional and
  depends on Developer Mode and an approved secure host path being available.
- The physical M32, expansion card, and stageboxes are unavailable during initial
  implementation; hardware-specific behavior remains unverified until the later
  hardware acceptance phase.
- The physical console will run the latest stable official M32 firmware when
  hardware acceptance begins.
- OSC is enabled and the computer can reach the console-control interface on a
  private network.
- Venue/event channel dictionaries, measurement microphone details, protected
  paths, and known-good references will be supplied before event-specific
  recommendations are trusted.
- Emulator tests prove OSC/MCP behavior only; they do not prove hardware
  compatibility.

## Dependencies

- A project-owned deterministic Fake M32 is required for repeatable automated
  validation and failure injection.
- An external X32 Emulator is required as an independent local OSC integration
  target, with emulator limitations labeled in reports.
- MCP Inspector and Claude Desktop are required for host-level validation.
- The real M32 is required for the final hardware acceptance gate.
- Third-party protocol references and emulator tools are reference or
  developer-test inputs only; unclear license status blocks redistribution, not
  independent validation.

## Constitution Alignment

- Console state authority is preserved: all operational state comes from live
  endpoint replies, snapshots with freshness metadata, or labeled test fixtures.
- Safe MCP surface is preserved: no raw OSC, arbitrary path, shell, firmware,
  shutdown, SD format, phantom-enable, or sample-rate tool is allowed.
- Human approval is preserved: writes require proposal separation, host
  confirmation, policy checks, readback, audit, and rollback path.
- Manual control wins: state changes after proposal creation invalidate affected
  proposals.
- Unknown firmware, identity mismatch, capability mismatch, and malformed state
  replies are fail-closed write locks until reconciliation passes.
- Main LR/M/C paths are protected by default and cannot change as implicit side
  effects of other operations.
- `EMERGENCY` mode is write-lock only for AI: it cancels pending proposals,
  allows no AI mute/rollback/write, and returns to `OBSERVE` before any
  reconciled write mode can be enabled.
- R3 is not expanded: headamp, routing, recall, bulk, and talkback configuration
  operations are limited to `SOUNDCHECK` in the MVP.
- R4 remains blocked: phantom enable, sample-rate/clock change, firmware,
  shutdown, and SD formatting are prohibited through AI.
- Emulator honesty is preserved: emulator pass results never become hardware
  verification or production/live readiness.
- Network safety is preserved: OSC remains private with no public exposure,
  operating-system bridge, Internet Connection Sharing, or packet forwarding.

## Spec Quality Review

- **No implementation code**: Pass. The specification describes behavior and
  constraints, not implementation code.
- **Technology-agnostic**: Pass with allowed domain protocol references. It does
  not prescribe programming language, implementation platform choices, package
  structure, or code-level design.
- **Mandatory sections complete**: Pass. Problem, clarifications, goals, actors,
  scope, user stories, edge cases, requirements, entities, success criteria,
  assumptions, dependencies, and constitution alignment are included.
- **Traceability**: Pass. All 40 functional requirement IDs defined in `PLAN.md`,
  spanning `FR-001` through `FR-054` with intentional numbering gaps, are
  preserved. `SC-001` through `SC-014` are preserved.
- **Clarifications**: Pass. No clarification markers are present.
- **Constitution compliance**: Pass. No MUST or MUST NOT rule is weakened, and
  R3/R4 permissions are not expanded.
