# Implementation Plan: M32 MCP Bridge MVP

**Feature**: 001-m32-mcp-bridge  
**Date**: 2026-07-19  
**Inputs**: PLAN.md, .specify/memory/constitution.md, specs/001-m32-mcp-bridge/spec.md  
**Status**: Technical plan only; no executable code, tasks, branch, or commit created.

## Scope Authority Note

The current `spec.md` clarification is the controlling source for EMERGENCY behavior. Any older wording in `PLAN.md` that suggests AI mute, rollback, or console write during EMERGENCY is superseded for this MVP. EMERGENCY is write lock and automation stop only; pending proposals are cancelled; exit returns to OBSERVE and requires reconciliation before writes can be re-enabled.

## Summary

Build a local, safety-first MCP bridge for Midas M32/X32-family console control. Claude Desktop is the primary user interface through MCP stdio. ChatGPT is an optional later transport that reuses the same Bridge Core through Streamable HTTP and an approved Secure MCP Tunnel. The MVP has no Custom WebUI, no AI provider integration, no database, and no control of M32-Edit.

The bridge communicates directly with the console or emulator over OSC/UDP, keeps an in-memory authoritative cache with revisions and freshness, writes JSON snapshots, and appends JSONL audit records. Every write follows:

Read -> Proposal -> MCP Host Human Confirmation -> Policy Check -> Write -> Readback -> Audit.

The console remains the source of truth. Manual console changes have priority and can block or invalidate proposals. Raw OSC tools are prohibited. R4 operations are prohibited. R3 operations are SOUNDCHECK-only. EMERGENCY locks all AI writes and automation, cancels pending proposals, permits no AI mute, rollback, or console write, exits only to OBSERVE, and requires reconciliation before any write can be re-enabled.

## Technical Context

| Area | Decision |
| --- | --- |
| Runtime | Python 3.12 |
| Shape | Local modular monolith |
| Primary MCP transport | stdio for Claude Desktop |
| Optional transport | Streamable HTTP for ChatGPT through Secure MCP Tunnel |
| Console transport | Direct OSC/UDP to M32 or emulator |
| State | In-memory cache with revisions, freshness, and reconciliation |
| Persistence | JSON snapshots and append-only JSONL audit |
| Testing core | Unit/property tests, deterministic Fake M32, failure injection |
| External validation | Patrick-Gilles Maillot X32 Emulator, MCP Inspector, Claude Desktop E2E |
| Hardware gate | Real M32 Hardware Acceptance before production or Live use |
| Non-goals | WebUI, database, microservices, AI backend, raw OSC tools, M32-Edit control |

The implementation may use the official MCP Python SDK stable 1.x. Exact dependency pins are deferred to implementation lock work and MUST NOT be invented in this plan.

## Constitution Check

| Rule | Design Response | Status |
| --- | --- | --- |
| Console is source of truth | All cached state has source, revision, timestamp, and readback; writes require reconciliation | PASS |
| Write control is fail-closed | Unknown firmware, capability mismatch, stale state, malformed replies, sync failure, and conflicts block writes | PASS |
| Human approval required | Write tools only execute approved proposals; no Always Allow workflow is acceptable | PASS |
| No raw OSC tools | MCP contracts expose semantic tools only; arbitrary path/value writes are excluded | PASS |
| R4 prohibited | Policy layer blocks R4 in every mode | PASS |
| R3 SOUNDCHECK-only | Policy matrix allows R3 only in SOUNDCHECK after required gates | PASS |
| Main protected by default | Main LR/M/C operations require explicit proposal and cannot be side effects | PASS |
| EMERGENCY behavior | EMERGENCY is write lock and automation stop only; no AI mute, rollback, or write | PASS |
| Sample rate and clock | Read and readiness checks only; AI cannot change sample rate/clock in MVP | PASS |
| Network isolation | OSC remains local/LAN only; no Internet exposure, OS bridging, ICS, or packet forwarding | PASS |
| Emulator limits | Fake and external emulator results never mark hardware-verified | PASS |
| Hardware Acceptance | Required before production or Live use | PASS |
| Cross-platform gate | Windows and macOS unit, Fake M32, MCP smoke, packaging, and startup tests required before MVP release | PASS |

No blocker was found against the current constitution and spec.

## Architecture

The MVP is a local modular monolith with strict internal boundaries:

1. **MCP Adapter**: Defines semantic tools, validates inputs, returns structured outputs, and never exposes arbitrary OSC paths.
2. **Bridge Core**: Orchestrates reads, proposals, policy decisions, transactions, readback, rollback decisions, and audit.
3. **OSC Console Adapter**: Encodes/decodes OSC, sends UDP requests, manages `/xremote` renewal before expiry, handles packet failure modes, and contains no policy bypass.
4. **State Cache**: Stores current state values, revisions, freshness, partial/stale flags, and snapshot comparison data.
5. **Policy Engine**: Enforces runtime mode, risk class, protected Main paths, R3/R4 limits, approval, firmware/capability readiness, and conflict checks.
6. **Diagnostics Engine**: Performs preflight, clock/AES50/card sync checks, RTA-assisted findings, and setup recommendations.
7. **Audit Writer**: Writes append-only JSONL records with redaction and transaction correlation.
8. **Snapshot Store**: Persists JSON snapshots and comparison metadata.
9. **Fake M32**: Project-owned deterministic test double for CI and failure injection.
10. **Transport Hosts**: stdio first; optional Streamable HTTP host later, reusing Bridge Core.

## Component Boundaries

| Component | Owns | MUST NOT Own |
| --- | --- | --- |
| MCP Adapter | Tool schemas, tool descriptions, request/response shaping | OSC path construction, policy exceptions |
| Bridge Core | Workflow sequencing and transaction lifecycle | Raw socket access, UI concerns |
| OSC Adapter | OSC/UDP protocol details and packet handling | Risk classification, approval decisions |
| State Cache | Revisions, freshness, snapshots, conflict baseline | Policy exceptions |
| Policy Engine | Mode/risk/approval/conflict decisions | Network I/O |
| Diagnostics Engine | Read-only analysis and readiness findings | Console writes |
| Audit Writer | Append-only records | State mutation |
| Fake M32 | Deterministic simulated console behavior | Hardware verification claims |

## Data Flows

### Read Flow

Claude/ChatGPT -> MCP tool -> Bridge Core -> State Cache freshness check -> OSC read if needed -> State Cache update -> structured response.

### Proposal Flow

Claude/ChatGPT -> semantic proposal tool -> Bridge Core reads current state -> Policy Engine validates scope/risk/mode -> proposal created with base revisions and rollback candidates -> audit proposal creation -> proposal returned for human review.

### Write Flow

MCP host confirmation -> execute proposal tool -> proposal digest, operation count, expiry, and baseline checked -> reconciliation verifies current revisions -> Policy Engine checks mode/risk/freshness/capabilities -> OSC Adapter writes allowed operations -> readback verifies values -> audit final result. The bridge does not accept model-supplied approval tokens.

### Rollback Flow

Rollback request -> policy check -> rollback candidate validation -> current state reconciliation -> allowed rollback writes -> readback -> audit. Rollback is unavailable through AI during EMERGENCY.

## Trust Boundaries

1. **AI client boundary**: Claude/ChatGPT can request tools but cannot bypass schemas, policy, approval, or readback.
2. **Human approval boundary**: The host confirmation is necessary but not sufficient; policy and reconciliation still run after approval.
3. **Console network boundary**: OSC/UDP is local/LAN-only and isolated from Internet-facing interfaces.
4. **State boundary**: Cached state is never more authoritative than the console; stale or partial state disables writes.
5. **Emulator boundary**: Emulator behavior validates integration behavior only, never hardware readiness.
6. **Optional ChatGPT boundary**: Secure MCP Tunnel is the only optional connectivity exception and MUST NOT expose OSC or raw console control.

## Connection State Machine

Connection lifecycle states:

- `DISCONNECTED`: No active OSC session; writes disabled.
- `CONNECTING`: Target reachable probe in progress; writes disabled.
- `IDENTIFYING`: Firmware, identity, model, and capability collection; writes disabled.
- `SYNCING`: Full or critical snapshot reconciliation; writes disabled.
- `READY`: Read-only operation available; writes may be considered only if runtime mode, risk, confirmation, verification, and freshness allow them.
- `DEGRADED`: Read-only with stale/partial warnings; writes disabled.
- `WRITE_LOCKED`: Explicit lock or policy lock; reads may continue.
- `EMERGENCY_LOCKED`: AI writes and automation stopped, pending proposals cancelled.

Verification states:

- `EMULATOR`: Fake M32 or external emulator; safe write tests may run, but production/Live readiness is blocked.
- `HARDWARE_UNVERIFIED`: Real hardware target without completed Hardware Acceptance; production/Live readiness is blocked.
- `HARDWARE_VERIFIED`: Real M32 target that passed Hardware Acceptance.

Transitions to write eligibility require successful identity, capability, critical state reconciliation, fresh clock/sync checks, non-emergency runtime mode, and the appropriate verification state for the requested environment. Unknown firmware, identity mismatch, capability mismatch, malformed state replies, or required clock/AES50/expansion-card sync failures MUST transition to a write-locked or degraded lifecycle state and a non-verified verification state.

## Runtime Modes and Permission Enforcement

| Mode | Meaning | Write Behavior |
| --- | --- | --- |
| `OBSERVE` | Read-only analysis and proposal drafting | No console writes |
| `SOUNDCHECK` | Controlled pre-show tuning | R1/R2 and allowed R3 after approval and gates |
| `LIVE` | Show operation | Restricted R1/R2 only if policy permits; R3/R4 blocked |
| `EMERGENCY` | Stop AI automation and lock writes | No AI writes, mute, rollback, or console write; pending proposals cancelled |

Risk classes:

- `R1`: Low-risk labels, notes, read-only derived metadata, and safe non-audio-impacting updates.
- `R2`: Bounded operational changes allowed by policy after proposal and approval.
- `R3`: Headamp, routing, recall, bulk, talkback configuration/destinations, and other high-risk operations; SOUNDCHECK-only.
- `R4`: Destructive, global, unsafe, unsupported, arbitrary OSC, or out-of-scope operations; always prohibited.

Momentary talkback activation and talkback configuration are separate actions. Configuration and destination changes are R3 and SOUNDCHECK-only; momentary activation is bounded by active runtime policy.

## State Synchronization Strategy

The bridge performs startup discovery, full or critical snapshot reads, and recurring synchronization through supported console polling and `/xremote` renewal. Each state value records path, decoded value, type, source, revision, timestamp, freshness deadline, and confidence.

Freshness rules:

- Writes require fresh baseline revisions for every affected path.
- Partial snapshots can support read-only responses but cannot authorize writes.
- Manual console changes after proposal creation invalidate or conflict the proposal.
- Duplicate, delayed, or out-of-order UDP replies are ignored if they do not advance the relevant revision or match a pending correlation.
- Packet loss and disconnects move affected paths to stale and disable writes until revalidated.

## Proposal and Transaction Lifecycle

Proposal states:

`DRAFTED -> PENDING_APPROVAL -> APPROVED -> EXECUTING -> VERIFIED`

Terminal alternatives:

`EXPIRED`, `CONFLICTED`, `POLICY_DENIED`, `READBACK_FAILED`, `ROLLBACK_ATTEMPTED`, `ROLLED_BACK`, `ROLLBACK_FAILED`, `CANCELLED_BY_EMERGENCY`.

Execution MUST:

1. Verify proposal digest, expected operation count, expiry, and host confirmation.
2. Re-read or validate current affected state.
3. Detect manual conflicts.
4. Re-run policy checks using current mode and capabilities.
5. Execute only allowed semantic operations.
6. Read back every affected value.
7. Audit every operation and result.

Write unlock MUST use a separate unlock control, not `m32_lock_writes`. Unlock is allowed only from OBSERVE, requires operator or host confirmation, and requires identity, capability, and critical state reconciliation. Unlock is unavailable in EMERGENCY.

## Error Handling

The bridge fails closed for:

- UDP timeout, packet loss, duplicate/out-of-order ambiguity, malformed packets, or disconnect during write.
- Stale state or partial snapshot for any affected path.
- Unknown firmware, identity mismatch, unsupported path, capability mismatch, or malformed state replies.
- Manual change conflict after proposal creation.
- Readback mismatch.
- Required clock, AES50, or expansion-card sync failure.
- RTA source unknown when an RTA-assisted finding would depend on it.
- EMERGENCY mode active.

Read-only tools may return degraded diagnostics with explicit confidence and source labels. Write tools MUST return structured denial errors rather than best-effort writes.

## Readback and Rollback Behavior

Readback is mandatory after every write. A mismatch marks the transaction failed, records the mismatch, and decides whether rollback is allowed by current mode and policy. Rollback can only use stored rollback candidates from the approved proposal and still requires policy checks, reconciliation, writes, readback, and audit.

Rollback MUST NOT run through AI in EMERGENCY. If rollback fails, the system remains write-locked or degraded and reports operator action required.

## Audit Strategy

Audit records are append-only JSONL. They include schema version, timestamp, actor host, tool name, runtime mode, connection lifecycle, verification state, console identity, proposal digest, approval source/reference, policy decision, operation count, per-operation old/requested/readback/rollback values, operation status, latency, error code, and redaction version. Secrets and credentials MUST NOT be embedded. Audit writes are required for proposal creation, approvals observed by the bridge, execution, denial, readback mismatch, rollback, emergency entry/exit, and write-lock changes.

## Configuration Approach

Configuration is file-based with environment variables for sensitive or host-specific values. Configuration schema is documented in `contracts/config.schema.json`; actual runtime config files are not created in this planning phase.

Configuration MUST cover:

- Console OSC host/port.
- Runtime mode default.
- Write-lock default.
- Freshness thresholds.
- Protected Main paths.
- Event Profile measurement microphone identity.
- Optional Streamable HTTP bind policy for ChatGPT transport.
- Audit/snapshot paths.
- External emulator path as developer-local metadata only, not distributed binary content.
- `/xremote` renewal default of 8 seconds with allowed range 2-9 seconds and write-lock fail-safe on missed renewal.

No embedded secrets are allowed.

## Cross-Platform Considerations

Windows and macOS are first-class MVP targets. The design avoids OS-specific network bridge assumptions, background service dependencies, and shell-only workflows. Startup, packaging, Fake M32, MCP smoke, and core tests MUST pass on both platforms before MVP release.

## Deployment for Claude Desktop

Claude Desktop is the first supported UX. The server runs locally through MCP stdio. stdout is reserved for valid MCP messages and logging goes to stderr, matching MCP transport requirements. Claude tool descriptions MUST emphasize semantic operations, source-of-truth state, proposal-before-write behavior, and confirmation requirements.

## Optional ChatGPT Transport

ChatGPT support is optional and later. It reuses Bridge Core and exposes the same semantic tools through Streamable HTTP and an approved Secure MCP Tunnel. It MUST NOT create a second policy layer, second state authority, WebUI, AI backend, raw OSC surface, or hosted application backend. Streamable HTTP MUST bind safely, validate Origin, and require appropriate authentication when exposed beyond localhost.

## Testing Architecture

Testing layers:

1. Unit and property tests for OSC encoding/decoding, value bounds, policy decisions, risk classification, proposal digesting, schema validation, and state transitions.
2. Project-owned deterministic Fake M32 for CI and predictable console behavior.
3. Failure injection for lost, delayed, duplicate, malformed, out-of-order packets, disconnect, and restart.
4. External Patrick-Gilles Maillot X32 Emulator integration as an independent developer suite and gate before MCP readiness.
5. MCP Inspector smoke tests for tool discovery, schema validation, and read/write workflow denial behavior.
6. Claude Desktop E2E for read-only conversation, proposal creation, approval handling, execution on emulator/Fake M32, and denial cases.
7. Windows/macOS smoke and packaging tests.
8. Final real-M32 Hardware Acceptance before production or Live use.

CI relies on Fake M32. External emulator success does not set `hardware_verified`. Emulator binaries MUST NOT be redistributed until rights and license terms are confirmed.

## Emulator Strategy

The project-owned Fake M32 is deterministic and designed for test coverage, not fidelity claims. External X32 Emulator use is optional for developers but required as a gate before declaring MCP readiness. Hardware Acceptance on a real M32 remains mandatory for production or Live use.

## Security and Network Isolation

- OSC MUST remain local/LAN-only and MUST NOT be exposed to the Internet.
- OS network bridging, Internet Connection Sharing, and packet forwarding between Internet-facing and console-control interfaces MUST remain disabled.
- Raw OSC tools and arbitrary path writes are prohibited.
- Write tools require proposal, human approval, policy check, readback, and audit.
- `Always Allow` approval configuration MUST NOT be used for write tools.
- Optional ChatGPT connectivity uses Secure MCP Tunnel only and MUST NOT expose OSC.
- Unknown firmware/capability mismatch/malformed state replies lock writes.

## Observability and CLI Controls

The MVP may include developer/operator controls for status, write-lock, reconciliation, snapshot capture, and diagnostics. These controls are operational surfaces only and MUST follow the same policy and audit rules. Observability should report connection state, runtime mode, hardware verification, freshness, pending proposals, latest audit ID, and degraded reasons.

## Project Source Tree

The technical plan expects the later implementation to stay in a small local modular monolith. This is a planning target for `/speckit.tasks`, not code created in this phase:

```text
src/m32_bridge/
  mcp/                 # semantic MCP tool adapter and host transport bindings
  core/                # proposal, transaction, policy, orchestration
  osc/                 # OSC UDP client, codec, /xremote, packet handling
  state/               # cache, revisions, snapshots, reconciliation
  diagnostics/         # preflight, findings, RTA/meter interpretation
  audit/               # append-only JSONL audit writer and redaction
  config/              # config loading and schema validation
  fake_m32/            # deterministic project-owned Fake M32
tests/
  unit/
  property/
  integration_fake_m32/
  integration_external_emulator/
  e2e_mcp/
```

No WebUI, AI backend, database service, or microservice split is implied by this tree.

## Phase Rollout

1. **Design contracts**: Complete plan, research, data model, quickstart, MCP tool contracts, and JSON schemas.
2. **Read-only core**: Implement connection, identity, capabilities, state cache, snapshots, status, and read-only MCP tools.
3. **Policy and proposal**: Implement risk model, proposal creation, approval binding, conflict detection, and audit.
4. **Safe writes on Fake M32**: Implement bounded writes with readback and failure injection.
5. **External emulator gate**: Validate against Patrick emulator and MCP Inspector.
6. **Claude Desktop E2E**: Validate read-only, proposal, approval, denial, rollback, emergency lock.
7. **Cross-platform gate**: Windows/macOS startup, packaging, Fake M32, MCP smoke.
8. **Hardware Acceptance**: Real M32 validation before production or Live use.

## Rollback of Application Releases

Application release rollback is separate from console rollback. A release rollback disables writes, stops optional HTTP exposure, returns the bridge to OBSERVE, restarts the previous local version, verifies read-only status, and records audit continuity. It does not imply any console state rollback.

## Complexity Tracking

The MVP intentionally rejects:

- Database persistence beyond JSON/JSONL files.
- WebUI and AI provider integration.
- Microservices.
- Runtime dependency on community console projects.
- Raw OSC and arbitrary path tooling.
- Post-MVP audio analyzer, USB/ASIO capture, and automated feedback suppression.

Any future complexity addition must document the user value, safety impact, test impact, and constitutional compliance before adoption.

## Requirements-to-Design Traceability

| ID | Design Mapping | Test Mapping |
| --- | --- | --- |
| FR-001 | OSC adapter and network isolation | Fake/hardware target connection smoke |
| FR-002 | VerificationState and environment labels | Status label tests |
| FR-003 | Identity/capability discovery | Startup identity and unknown firmware tests |
| FR-004 | `/xremote` renewal at 2-9s, default 8s | Missed-renewal write-lock test |
| FR-005 | Heartbeat/reply loss detection | Disconnect failure injection |
| FR-006 | Bounded reconnect and reconciliation | Reconnect blocks writes until reconciliation |
| FR-010 | Typed Snapshot entity and schema | Snapshot schema and completeness tests |
| FR-011 | StateRevision monotonic cache | Revision monotonic/property tests |
| FR-012 | Full StateValue metadata | Field completeness tests |
| FR-013 | Remote notifications plus selective reads | Manual change detection tests |
| FR-014 | Distinct gain/trim/fader entities | Value classification tests |
| FR-015 | Meter bank decoder | Meter mapping tests |
| FR-016 | RTA source metadata | RTA source unknown denial tests |
| FR-017 | Clock/AES50/card sync reads | Preflight sync blocker tests |
| FR-020 | Deterministic preflight before prose | Preflight ordering tests |
| FR-021 | DiagnosticFinding evidence model | Finding schema/content tests |
| FR-022 | Recommendations separated from operations | Proposal separation tests |
| FR-023 | Meter/RTA representation limits | No per-channel spectra contract tests |
| FR-024 | SOUNDCHECK-only sequential RTA scan | Mode and restore tests if enabled |
| FR-025 | EventProfile measurement mic and phantom policy | Event-profile schema tests |
| FR-030 | Stored proposal with digest, revisions, rollback values, bounds | Proposal schema and digest tests |
| FR-031 | Reject missing/expired/used/modified/conflicted proposals | Execution denial matrix |
| FR-032 | Policy risk/mode/path/bounds/rate/snapshot check | Policy property tests |
| FR-033 | Resource serialization | Overlapping write transaction tests |
| FR-034 | Readback with retry/timeout | Readback timeout/mismatch tests |
| FR-035 | Failed verification and safe rollback | Rollback safety tests outside EMERGENCY |
| FR-036 | R3 SOUNDCHECK-only and talkback split | R3 mode denial and talkback classification tests |
| FR-037 | Blocked phantom/sample-rate/clock/firmware/shutdown/SD | R4/prohibited operation tests |
| FR-038 | Manual conflict invalidation | Manual change after proposal tests |
| FR-040 | Claude Desktop stdio transport | MCP stdio E2E |
| FR-041 | Optional HTTP disabled by default and safely bound | Config schema and startup tests |
| FR-042 | Secure MCP Tunnel only for ChatGPT | Optional transport config tests |
| FR-043 | Tool risk/confirmation declarations | MCP Inspector contract tests |
| FR-044 | Structured outputs | Schema/output tests |
| FR-045 | No local AI provider integration | Dependency/config review |
| FR-050 | Append-only JSONL audit | Audit append and rejected-write audit tests |
| FR-051 | Secret redaction | Audit redaction tests |
| FR-052 | Snapshot schema version, identity, firmware, checksum, completeness | Snapshot schema and checksum tests |
| FR-053 | Operator controls for health, snapshot, verify, audit tail | CLI/operator control smoke tests |
| FR-054 | Emergency write lock, cancel proposals, no AI writes, OBSERVE exit | Emergency lifecycle tests |
| SG-001 | Console/emulator source of truth | State-source tests |
| SG-002 | Prohibited tool surface | MCP tool inventory tests |
| SG-003 | Proposal -> approval -> execution -> readback -> audit | Safe-write workflow E2E |
| SG-004 | Manual priority | Conflict tests |
| SG-005 | R4 always blocked | Malformed proposal/direct call tests |
| SG-006 | Sample rate/clock read-only | Preflight and write-denial tests |
| SG-007 | Emulator not hardware verification | Environment label tests |
| SG-008 | Hardware Acceptance required | Release gate checklist tests |
| SG-009 | No bridge/ICS/forwarding/public OSC | Network isolation gate |
| SG-010 | Unknown firmware/capability lock | Identity mismatch tests |
| SG-011 | Main protection | Main explicit proposal tests |
| SG-012 | EMERGENCY no AI write capability | Emergency no-write tests |
| SC-001 | State notification and polling path | 500ms p95 local state visibility |
| SC-002 | Display values and gain grid | Value formatting/grid tests |
| SC-003 | Snapshot performance and incomplete labeling | 5s p95 emulator snapshot test |
| SC-004 | Audit every write attempt | Audit coverage tests |
| SC-005 | Readback every successful write | Readback coverage tests |
| SC-006 | OBSERVE no state-changing OSC | OBSERVE integration packet test |
| SC-007 | Blocked R4 remains blocked | R4 denial tests |
| SC-008 | Stale/disconnected prevents writes within 1s | Heartbeat failure test |
| SC-009 | Reconciliation before unlock | Reconnect/unlock tests |
| SC-010 | Conflicts send zero target writes | Conflict execution test |
| SC-011 | Environment labels in every status | Status schema tests |
| SC-012 | Claude Desktop tool list/call/results | Claude Desktop E2E |
| SC-013 | External emulator suite on primary Windows dev environment | External emulator gate |
| SC-014 | Final hardware manual change detection | Hardware Acceptance gate |
