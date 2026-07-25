# Data Model: M32 MCP Bridge MVP

**Date**: 2026-07-19  
**Scope**: Conceptual model for planning. No implementation structure is implied.

## Entity Relationships

ConsoleIdentity has many ConsoleCapabilities and one current VerificationState. Snapshot contains StateValues and StateRevisions. EventProfile defines channel, bus, and output dictionaries, ChannelRoles, protected paths, mode permissions, measurement microphone identity, and known-good references. Proposal contains Operations and references a baseline Snapshot or StateRevisions. Transaction executes one approved Proposal and produces ReadbackResult, optional RollbackResult, DiagnosticFindings, and AuditRecords. ConnectionLifecycle gates network/session availability; VerificationState gates production and Live readiness claims.

## ConsoleIdentity

Fields: `identity_id`, `model`, `firmware_version`, `firmware_status`, `endpoint_host`, `endpoint_port`, `serial_or_unique_hint`, `source`, `observed_at`, `environment_label`, `verification_state`, `hardware_verified`.

Validation rules:

- `firmware_status` MUST be `known`, `unknown`, or `unsupported`.
- Unknown firmware or endpoint identity mismatch MUST force write lock.
- `hardware_verified` MUST be false for Fake M32 and external emulator targets.
- `environment_label` MUST be `emulator`, `hardware-unverified`, or `hardware-verified`.

## ConsoleCapability

Fields: `capability_id`, `identity_id`, `path_family`, `supported`, `risk_class`, `read_supported`, `write_supported`, `verified_by`, `verified_at`.

Validation rules:

- Capability mismatch or missing critical capability MUST block writes.
- R4 capability MUST remain non-writable even if the console accepts an OSC path.
- Clock/sample-rate capabilities are read-only in MVP.

## StateValue

Fields: `path`, `raw_value`, `native_value`, `display_value`, `unit`, `value_type`, `source`, `revision`, `observed_at`, `fresh_until`, `confidence`, `stale`, `partial`, `support_status`, `environment_label`, `capability_id`.

Validation rules:

- StateValue MUST record whether it came from hardware, Fake M32, external emulator, or imported snapshot.
- Writes require non-stale values for all affected paths.
- Partial values cannot authorize writes.
- `display_value`, `support_status`, revision, freshness, and `environment_label` MUST be present for every cached field.

## StateRevision

Fields: `revision`, `path`, `previous_revision`, `observed_at`, `change_source`, `transaction_id`, `manual_change_detected`.

Validation rules:

- Manual console changes have priority.
- A proposal baseline revision that no longer matches current state MUST block execution.
- Duplicate or out-of-order observations MUST NOT advance revision incorrectly.

## Snapshot

Fields: `schema_version`, `snapshot_id`, `identity_id`, `firmware`, `captured_at`, `source`, `mode`, `checksum`, `complete`, `state_values`, `missing_paths`, `critical_stale_paths`, `environment_label`, `hardware_verified`.

Validation rules:

- Snapshot files MUST be JSON.
- Snapshot files MUST include schema version, identity, firmware, capture time, checksum, and completeness status.
- Partial snapshots MUST be labeled and cannot create WriteReady state.
- Emulator snapshots MUST NOT be labeled hardware-verified.

## EventProfile

Fields: `event_profile_id`, `name`, `created_at`, `channel_dictionary`, `bus_dictionary`, `output_dictionary`, `expected_topology`, `channel_roles`, `measurement_microphone_channel`, `measurement_microphone_role`, `measurement_microphone_phantom_policy`, `rta_source`, `clock_requirements`, `aes50_requirements`, `expansion_card_requirements`, `protected_paths`, `mode_specific_permissions`, `known_good_reference`, `deferred_fields`.

Validation rules:

- Measurement microphone MUST be explicitly defined; it MUST NOT be guessed from channel name.
- Measurement microphone phantom policy MUST be `manual_only` or `forbidden`; automatic phantom enable remains prohibited.
- Deferred fields are allowed until hardware/event details arrive, but affected readiness checks MUST remain incomplete.
- RTA-assisted findings require known RTA source.
- Event Profile MUST cover channel, bus, and output dictionaries, expected topology, protected paths, mode-specific permissions, and known-good reference metadata.

## ChannelRole

Fields: `channel_id`, `role`, `source_label`, `expected_source`, `phantom_policy`, `protected`, `main_assignment_expected`.

Validation rules:

- Phantom power MUST NOT be enabled automatically.
- Main assignment changes are protected by default.
- Role confidence MUST be explicit when derived from incomplete data.

## Proposal

Fields: `proposal_id`, `created_at`, `expires_at`, `created_by`, `base_snapshot_id`, `base_revisions`, `runtime_mode_at_creation`, `operations`, `risk_summary`, `human_readable_summary`, `rollback_candidates`, `status`, `proposal_digest`, `server_computed`.

Validation rules:

- Proposal MUST be separate from execution.
- Proposal MUST include baseline revisions for all affected paths.
- Proposal MUST expire or become conflicted if manual changes affect target paths.
- R4 operations MUST NOT be proposed.
- R3 proposals MUST be SOUNDCHECK-only.
- `risk_summary` MUST be computed by the bridge server and MUST NOT be trusted from model-supplied values.

Lifecycle:

`DRAFTED -> PENDING_APPROVAL -> APPROVED_BY_HOST -> EXECUTING -> VERIFIED -> USED`

Terminal states: `EXPIRED`, `CONFLICTED`, `POLICY_DENIED`, `READBACK_FAILED`, `ROLLED_BACK`, `ROLLBACK_FAILED`, `CANCELLED_BY_EMERGENCY`.

## Operation

Fields: `operation_id`, `proposal_id`, `semantic_action`, `target_path`, `target_kind`, `before_value`, `requested_value`, `rollback_value`, `bounds`, `risk_class`, `affects_main`, `requires_readback`, `requires_reconciliation`, `reason`.

Validation rules:

- Operation MUST map to an allowlisted semantic action.
- Operation MUST NOT expose arbitrary raw OSC.
- Main LR/M/C operations MUST be explicit and cannot be side effects.
- Talkback momentary activation and talkback configuration MUST be distinct semantic actions.
- `target_kind`, `rollback_value`, `bounds`, `risk_class`, and `requires_readback` are mandatory.

## PolicyDecision

Fields: `decision_id`, `evaluated_at`, `runtime_mode`, `write_lock`, `verification_state`, `risk_class`, `allowed`, `reasons`, `required_confirmation`, `freshness_result`, `capability_result`, `conflict_result`, `approval_source`.

Validation rules:

- Deny if EMERGENCY, write lock, stale state, unsupported capability, unknown firmware, manual conflict, R4, or R3 outside SOUNDCHECK.
- Human approval is required for writes but does not override policy denial.
- The approval source for MCP writes is host confirmation; the bridge MUST NOT accept a model-supplied approval token.

## Transaction

Fields: `transaction_id`, `proposal_id`, `started_at`, `completed_at`, `actor_host`, `mode_at_execution`, `operations_attempted`, `operations_succeeded`, `operations_failed`, `policy_decision`, `readback_result`, `rollback_result`, `status`.

Validation rules:

- Transaction MUST bind to one approved proposal digest.
- Transaction MUST be audited whether it succeeds or fails.
- Disconnect during write MUST mark transaction uncertain or failed and lock writes until reconciliation.

## ReadbackResult

Fields: `readback_id`, `transaction_id`, `checked_at`, `expected_values`, `actual_values`, `matched`, `mismatches`, `stale_paths`.

Validation rules:

- Every write requires readback of affected values.
- Mismatch MUST be audited and may trigger allowed rollback handling outside EMERGENCY.

## RollbackResult

Fields: `rollback_id`, `transaction_id`, `attempted`, `allowed`, `started_at`, `completed_at`, `operations`, `readback_result`, `status`, `failure_reason`.

Validation rules:

- Rollback can only use stored rollback candidates.
- Rollback still requires policy check, reconciliation, write, readback, and audit.
- Rollback MUST NOT be executed by AI in EMERGENCY.

## AuditRecord

Fields: `audit_id`, `timestamp`, `schema_version`, `actor_host`, `tool_name`, `runtime_mode`, `connection_lifecycle`, `verification_state`, `console_identity`, `proposal_id`, `proposal_digest`, `transaction_id`, `approval_source`, `approval_reference`, `policy_decision`, `operation_count`, `operations`, `result`, `error_code`, `redaction_version`.

Validation rules:

- Audit is append-only JSONL.
- No embedded secrets.
- Denials and emergency state changes are audited.
- Execution, denial, readback, and rollback audit records MUST include per-operation path, old value, requested value, readback value, rollback value, operation status, and latency.

## DiagnosticFinding

Fields: `finding_id`, `created_at`, `severity`, `category`, `source`, `affected_paths`, `summary`, `evidence`, `recommendation`, `blocks_readiness`.

Validation rules:

- Required clock, AES50, or expansion-card sync failure MUST block readiness.
- RTA source unknown MUST block RTA-dependent conclusions.
- Findings based on emulator MUST be labeled unverified for hardware.

## ConnectionLifecycle

Fields: `state`, `since`, `target_kind`, `identity_id`, `last_successful_read_at`, `last_reconciliation_at`, `write_ready`, `write_lock_reason`, `degraded_reasons`.

States: `DISCONNECTED`, `CONNECTING`, `IDENTIFYING`, `SYNCING`, `READY`, `DEGRADED`, `WRITE_LOCKED`, `EMERGENCY_LOCKED`.

Validation rules:

- `write_ready` MUST be false unless identity, capabilities, freshness, reconciliation, mode, and hardware-readiness constraints pass.
- Exiting EMERGENCY MUST set state to OBSERVE first and require reconciliation before write readiness.

## VerificationState

Fields: `state`, `environment_label`, `verified_at`, `verified_by`, `hardware_acceptance_id`.

States: `EMULATOR`, `HARDWARE_UNVERIFIED`, `HARDWARE_VERIFIED`.

Validation rules:

- Fake M32 and external emulator targets MUST use `EMULATOR`.
- Hardware without successful Hardware Acceptance MUST use `HARDWARE_UNVERIFIED`.
- Only real-M32 Hardware Acceptance can set `HARDWARE_VERIFIED`.
- Safe writes on Fake M32 or external emulator MAY be used for testing while still reporting `EMULATOR`.

## Invariants

- Console state is authoritative over cache and proposals.
- No write occurs without proposal, human approval, policy check, readback, and audit.
- Manual console changes override AI proposals.
- R4 is always blocked.
- R3 is SOUNDCHECK-only.
- Main paths are protected by default.
- Unknown firmware or capability mismatch locks writes.
- Emulator validation never grants hardware verification.
- Production and Live readiness require real M32 Hardware Acceptance.
