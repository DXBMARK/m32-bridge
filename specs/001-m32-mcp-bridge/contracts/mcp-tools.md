# MCP Tool Contracts: M32 MCP Bridge MVP

**Date**: 2026-07-19  
**Scope**: Semantic MCP tools only. Raw OSC and arbitrary path tools are prohibited.

## Common Rules

All tool outputs are structured JSON-compatible objects with `ok`, `tool`, `runtime_mode`, `connection_lifecycle`, `verification_state`, `source`, `hardware_verified`, and `audit_id` when audited. Write-capable tools MUST require proposal, MCP host human confirmation, policy check, readback, and audit.

Common error codes:

- `NOT_CONNECTED`
- `STALE_STATE`
- `PARTIAL_SNAPSHOT`
- `UNKNOWN_FIRMWARE`
- `IDENTITY_MISMATCH`
- `CAPABILITY_MISMATCH`
- `UNSUPPORTED_PATH`
- `POLICY_DENIED`
- `R4_BLOCKED`
- `R3_MODE_DENIED`
- `MAIN_PROTECTED`
- `CONFIRMATION_REQUIRED`
- `PROPOSAL_EXPIRED`
- `PROPOSAL_CONFLICT`
- `READBACK_MISMATCH`
- `ROLLBACK_FAILED`
- `EMERGENCY_LOCKED`
- `HARDWARE_UNVERIFIED`
- `VALIDATION_ERROR`
- `TIMEOUT`
- `MALFORMED_REPLY`
- `RTA_SOURCE_UNKNOWN`
- `OPERATOR_CONFIRMATION_REQUIRED`
- `UNLOCK_RECONCILIATION_REQUIRED`

Freshness levels:

- `none`: Can run without current console state.
- `read_fresh`: Requires fresh enough state for read response confidence.
- `write_fresh`: Requires fresh baseline for all affected paths.
- `reconciled`: Requires identity, capability, critical state, and affected path reconciliation.

## Tool Summary

| Tool | Risk | Modes | Confirmation | Freshness | Sends OSC Writes |
| --- | --- | --- | --- | --- | --- |
| `m32_console_status` | R0 | all | no | none | no |
| `m32_connect` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | none | no |
| `m32_disconnect` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | host-confirmed in LIVE | none | no |
| `m32_reconcile_state` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | no |
| `m32_get_overview` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_list_channels` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_channel` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_bus` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_routing` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_clock_sync` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_meters` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_get_rta` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_capture_snapshot` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_compare_snapshots` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | none | no |
| `m32_get_changes` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_trace_signal` | R0 | OBSERVE, SOUNDCHECK, LIVE, EMERGENCY | no | read_fresh | no |
| `m32_event_preflight` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | reconciled | no |
| `m32_analyze_gain_staging` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | no |
| `m32_analyze_routing` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | no |
| `m32_analyze_processing` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | no |
| `m32_analyze_rta` | R0/RTA-source scan | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | yes, only `/rta/source` scan/restore in explicit SOUNDCHECK scan mode |
| `m32_recommend_event_setup` | R0 | OBSERVE, SOUNDCHECK | no | reconciled | no |
| `m32_propose_changes` | max R3 | OBSERVE, SOUNDCHECK, LIVE | no | reconciled | no |
| `m32_execute_proposal` | proposal risk | SOUNDCHECK, restricted LIVE | MCP host confirmation | reconciled | yes |
| `m32_verify_proposal` | R0 | OBSERVE, SOUNDCHECK, LIVE | no | read_fresh | no |
| `m32_rollback_proposal` | proposal risk | SOUNDCHECK, restricted LIVE | MCP host confirmation | reconciled | yes |
| `m32_lock_writes` | R0 | all | no | none | no |
| `m32_unlock_writes` | R0 | OBSERVE | operator or host confirmation | reconciled | no |
| `m32_enter_emergency` | R0 | all | no | none | no |
| `m32_exit_emergency_to_observe` | R0 | EMERGENCY | no | none | no |

## Connection and Status Tools

### `m32_console_status`

- Purpose: Report connection state, runtime mode, write lock, hardware verification, freshness, and pending proposal count.
- Input schema: `{ "include_diagnostics": boolean }`
- Structured output: connection state, target kind, identity summary, capability status, write readiness, degraded reasons.
- Error codes: none for normal disconnected status.
- Risk level: R0.
- Allowed runtime modes: all.
- Confirmation requirement: none.
- Freshness requirement: none.
- Can send OSC writes: no.

### `m32_connect`

- Purpose: Connect to configured console, Fake M32, or external emulator and perform identity/capability discovery.
- Input schema: `{ "target": "configured" | "fake_m32" | "external_emulator" }`
- Structured output: identity, capability summary, hardware verification flag, connection state.
- Error codes: `TIMEOUT`, `UNKNOWN_FIRMWARE`, `IDENTITY_MISMATCH`, `CAPABILITY_MISMATCH`, `MALFORMED_REPLY`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE.
- Confirmation requirement: none.
- Freshness requirement: none.
- Can send OSC writes: no.

### `m32_disconnect`

- Purpose: Stop active console session and lock writes.
- Input schema: `{ "reason": string }`
- Structured output: disconnected state and audit id.
- Error codes: `VALIDATION_ERROR`, `OPERATOR_CONFIRMATION_REQUIRED`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE, EMERGENCY.
- Confirmation requirement: host/operator confirmation is required when disconnecting during LIVE because it affects system readiness.
- Freshness requirement: none.
- Can send OSC writes: no.

### `m32_reconcile_state`

- Purpose: Re-read identity, capabilities, critical paths, and optionally affected proposal paths.
- Input schema: `{ "scope": "critical" | "full" | "proposal", "proposal_id": string | null }`
- Structured output: reconciliation status, stale paths, conflicts, write-ready eligibility.
- Error codes: `NOT_CONNECTED`, `UNKNOWN_FIRMWARE`, `CAPABILITY_MISMATCH`, `STALE_STATE`, `MALFORMED_REPLY`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE.
- Confirmation requirement: none.
- Freshness requirement: read_fresh.
- Can send OSC writes: no.

## Read Tools

Read tools share this output shape: `data`, `source`, `freshness`, `revision`, `partial`, `warnings`, `hardware_verified`.

- `m32_get_overview`: console identity, firmware, mode, clock/sync, high-level channel/bus status.
- `m32_list_channels`: channel index, labels, roles, mute/fader/gain summary, source labels.
- `m32_get_channel`: detailed state for one channel by numeric id and expected role.
- `m32_get_bus`: detailed state for one bus or matrix.
- `m32_get_routing`: read-only routing summary; routing writes remain R3 SOUNDCHECK-only through proposals.
- `m32_get_clock_sync`: sample rate, clock source, AES50 A/B, expansion-card sync state; no writes.
- `m32_get_meters`: supported OSC meter summaries; not simultaneous independent spectra per channel.
- `m32_get_rta`: console RTA values for a known source only.
- `m32_capture_snapshot`: persist JSON snapshot and return snapshot id.
- `m32_compare_snapshots`: compare two snapshots and classify manual/AI/unknown differences.
- `m32_get_changes`: report changes since revision or snapshot.
- `m32_trace_signal`: read-only signal path trace using known routing and channel roles.

Common input schemas:

- Channel: `{ "channel": integer, "include_processing": boolean }`
- Bus: `{ "bus": integer, "kind": "bus" | "matrix" | "main" }`
- Snapshot: `{ "scope": "critical" | "full" | "event_profile", "label": string | null }`
- Compare: `{ "base_snapshot_id": string, "current_snapshot_id": string }`

Common errors: `NOT_CONNECTED`, `STALE_STATE`, `PARTIAL_SNAPSHOT`, `UNSUPPORTED_PATH`, `RTA_SOURCE_UNKNOWN`, `MALFORMED_REPLY`.

## Diagnostics and Event Preflight

### `m32_event_preflight`

- Purpose: Check readiness for the Event Profile, including channel roles, measurement microphone identity, Main protection, clock, AES50, and expansion-card sync.
- Input schema: `{ "event_profile_id": string, "scope": "readiness" | "soundcheck" }`
- Structured output: findings, blockers, readiness status, write-ready eligibility, deferred fields.
- Error codes: `NOT_CONNECTED`, `STALE_STATE`, `UNKNOWN_FIRMWARE`, `CAPABILITY_MISMATCH`, `RTA_SOURCE_UNKNOWN`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE.
- Confirmation requirement: none.
- Freshness requirement: reconciled.
- Can send OSC writes: no.

### Analysis Tools

- `m32_analyze_gain_staging`: Finds gain/fader/headroom issues from current state and meters.
- `m32_analyze_routing`: Finds routing inconsistencies; no route writes.
- `m32_analyze_processing`: Finds EQ/dynamics issues from current processing state.
- `m32_analyze_rta`: Uses known RTA source in current mode; optional explicit scan mode is SOUNDCHECK-only, requires configured sources, and may write only `/rta/source` for scan selection and restore. It does not claim independent per-channel spectra.
- `m32_recommend_event_setup`: Produces a safe setup recommendation, not execution.

Analysis tools other than explicit `m32_analyze_rta` scan mode are R0, read-only, and cannot send OSC writes. `m32_analyze_rta` MUST be registered conservatively because scan mode can send bounded RTA source selection/restore writes.

## Proposal Tools

### `m32_propose_changes`

- Purpose: Create a proposal from semantic intended changes without execution.
- Input schema: `{ "intent": string, "targets": array, "constraints": object, "event_profile_id": string | null }`
- Structured output: proposal id, digest, human-readable summary, operations, risk summary, blocked operations, rollback candidates, expiry.
- Error codes: `NOT_CONNECTED`, `UNKNOWN_FIRMWARE`, `CAPABILITY_MISMATCH`, `POLICY_DENIED`, `R4_BLOCKED`, `R3_MODE_DENIED`, `MAIN_PROTECTED`, `STALE_STATE`, `VALIDATION_ERROR`.
- Risk level: max operation risk, R3 maximum.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE.
- Confirmation requirement: none at creation.
- Freshness requirement: reconciled.
- Can send OSC writes: no.

### `m32_execute_proposal`

- Purpose: Execute an already-created proposal after explicit human approval.
- Input schema: `{ "proposal_id": string, "proposal_digest": string, "expected_operation_count": integer }`
- Structured output: transaction id, policy decision, operations attempted, readback result, rollback status if any, audit id.
- Error codes: `CONFIRMATION_REQUIRED`, `PROPOSAL_EXPIRED`, `PROPOSAL_CONFLICT`, `POLICY_DENIED`, `R4_BLOCKED`, `R3_MODE_DENIED`, `MAIN_PROTECTED`, `READBACK_MISMATCH`, `TIMEOUT`, `EMERGENCY_LOCKED`.
- Risk level: proposal risk.
- Allowed runtime modes: SOUNDCHECK and restricted LIVE per policy; never EMERGENCY.
- Confirmation requirement: MCP host confirmation before the tool call is the approval boundary; the bridge MUST NOT accept model-supplied approval tokens. `proposal_id`, digest, operation count, expiry, baseline revisions, freshness, and policy are rechecked after the confirmed call arrives. Audit MUST record `approval.source = mcp_host_confirmation`.
- Freshness requirement: reconciled.
- Can send OSC writes: yes, only allowlisted semantic writes.

### `m32_verify_proposal`

- Purpose: Verify current console state against a proposal or completed transaction.
- Input schema: `{ "proposal_id": string, "transaction_id": string | null }`
- Structured output: readback match status, mismatches, stale paths, hardware verification flag.
- Error codes: `NOT_CONNECTED`, `STALE_STATE`, `READBACK_MISMATCH`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE, SOUNDCHECK, LIVE.
- Confirmation requirement: none.
- Freshness requirement: read_fresh.
- Can send OSC writes: no.

### `m32_rollback_proposal`

- Purpose: Roll back an executed proposal using stored rollback candidates when current policy permits.
- Input schema: `{ "proposal_id": string, "transaction_id": string }`
- Structured output: rollback id, policy decision, operations attempted, readback result, audit id.
- Error codes: `CONFIRMATION_REQUIRED`, `POLICY_DENIED`, `PROPOSAL_CONFLICT`, `ROLLBACK_FAILED`, `READBACK_MISMATCH`, `EMERGENCY_LOCKED`.
- Risk level: proposal risk.
- Allowed runtime modes: SOUNDCHECK and restricted LIVE per policy; never EMERGENCY.
- Confirmation requirement: MCP host confirmation before the tool call is the approval boundary; no model-supplied approval token is accepted.
- Freshness requirement: reconciled.
- Can send OSC writes: yes, only stored rollback candidates.

## Emergency Write Lock Tools

### `m32_lock_writes`

- Purpose: Enter or maintain a write-locked state without changing console audio state. This tool cannot unlock writes.
- Input schema: `{ "reason": string }`
- Structured output: write lock state, cancelled proposal ids if applicable, audit id.
- Error codes: `VALIDATION_ERROR`.
- Risk level: R0.
- Allowed runtime modes: all.
- Confirmation requirement: none.
- Freshness requirement: none.
- Can send OSC writes: no.

### `m32_unlock_writes`

- Purpose: Request removal of a non-emergency write lock after reconciliation. This is not available inside EMERGENCY.
- Input schema: `{ "reason": string }`
- Structured output: write lock state, reconciliation summary, audit id.
- Error codes: `OPERATOR_CONFIRMATION_REQUIRED`, `UNLOCK_RECONCILIATION_REQUIRED`, `UNKNOWN_FIRMWARE`, `CAPABILITY_MISMATCH`, `STALE_STATE`, `EMERGENCY_LOCKED`.
- Risk level: R0.
- Allowed runtime modes: OBSERVE only.
- Confirmation requirement: operator or MCP host confirmation required.
- Freshness requirement: reconciled; identity, capabilities, and critical state MUST pass before unlock.
- Can send OSC writes: no.

### `m32_enter_emergency`

- Purpose: Lock all AI writes, stop automation, and cancel pending proposals.
- Input schema: `{ "reason": string }`
- Structured output: `EMERGENCY_LOCKED`, cancelled proposal ids, audit id.
- Error codes: `VALIDATION_ERROR`.
- Risk level: R0.
- Allowed runtime modes: all.
- Confirmation requirement: none.
- Freshness requirement: none.
- Can send OSC writes: no.

### `m32_exit_emergency_to_observe`

- Purpose: Leave EMERGENCY only into OBSERVE, with writes still disabled until reconciliation passes.
- Input schema: `{ "reason": string }`
- Structured output: OBSERVE state, reconciliation required flag, audit id.
- Error codes: `VALIDATION_ERROR`.
- Risk level: R0.
- Allowed runtime modes: EMERGENCY.
- Confirmation requirement: none.
- Freshness requirement: none.
- Can send OSC writes: no.

## Prohibited MCP Tools

The MVP MUST NOT expose:

- Raw OSC send.
- Arbitrary path read/write.
- Arbitrary scene recall.
- Bulk import/apply without semantic proposal.
- Sample rate or clock mutation.
- Phantom auto-enable.
- Main path side-effect mutation.
- Emulator hardware-verification override.
