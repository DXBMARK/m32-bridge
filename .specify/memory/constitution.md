<!--
Sync Impact Report
Version change: 1.1.0 -> 2.0.0
Modified principles:
- III. Human-Approved Proposal Execution -> Human-Approved Proposal Execution and Controlled Maintenance Boundary
- IV. Verification, Audit, and Fail-Closed Recovery -> Verification, Audit, Fail-Closed Recovery, and Maintenance Safety
- V. Emulator Honesty and Minimal MVP Architecture -> Emulator Honesty and Minimal MVP Architecture (expanded for maintenance separation)
Added sections:
- VI. Protocol Authority and Registry Fidelity
- VII. Controlled R4 Maintenance / Break-Glass Boundary
Removed sections:
- None
Templates updated:
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
- ✅ specs/speckit-execution-order.md
- ✅ specs/speckit-specify-004.md
Additional governance sync completed in this patch:
- ✅ PLAN.md
Documents requiring later alignment:
- ⚠ specs/001-m32-mcp-bridge/plan.md
- ⚠ specs/001-m32-mcp-bridge/spec.md
- ⚠ specs/001-m32-mcp-bridge/tasks.md
- ⚠ docs/local-runbook.md
- ⚠ README.md
Follow-up TODOs:
- Tracked follow-up work; the listed documents above still require alignment
  and are not yet synced with this amendment.
-->
# M32 AI MCP Bridge Constitution

## Core Principles

### I. Console State Authority
Live OSC replies from the configured M32/X32 endpoint MUST be the authoritative
source for operational state. Model memory, prompt context, prior chat history,
snapshots without freshness metadata, and emulator assumptions MUST NOT be treated
as authoritative live state.

- Every read result MUST label value, display value, source, observed time,
  freshness, support status, revision, and environment.
- Every write proposal MUST be based on a fresh read or a named snapshot revision.
- Unknown, stale, unsupported, emulator-only, and hardware-unverified values MUST
  be visible in tool outputs and status responses.
- Physical console changes MUST take priority over automation. A manual change
  that conflicts with a pending proposal MUST invalidate that proposal.

Rationale: The bridge controls live audio equipment. Safe analysis and control
depend on current console evidence, not model inference.

### II. Safe MCP Surface and Policy Enforcement
The MCP server MUST expose only typed, bounded, purpose-specific tools. It MUST
NOT expose raw OSC or generic execution surfaces to the model.

- Tools named or equivalent to `send_raw_osc`, `set_any_path`, `execute_shell`,
  `format_sd`, `shutdown_console`, `set_firmware`, `enable_phantom`, or
  `set_sample_rate` MUST NOT exist in the normal MCP surface.
- R4 maintenance actions MUST stay behind a separate maintenance boundary and
  MUST NOT be mixed into the normal proposal/execution toolset.
- MCP tool inputs MUST be schema-validated at the MCP/config/proposal boundaries.
- Tool names and host approvals MUST NOT grant authority by themselves; server
  policy MUST re-check runtime mode, risk level, path allowlist, bounds, rate
  limits, freshness, proposal status, and snapshot requirements.
- Read tools MUST declare read-only behavior. Write tools MUST declare sensitive
  or destructive behavior for host confirmation.
- Prompt instructions and knowledge packs MUST NOT be the only security control;
  blocking rules MUST exist in server-side policy.

Rationale: The model is an untrusted caller. Safety must be enforced by the
bridge, not by wording in a conversation.

### III. Human-Approved Proposal Execution
All state-changing operations MUST follow proposal -> explicit human approval ->
execution -> readback -> audit. Analysis and execution MUST remain separate
user-visible MCP actions.

- Write execution MUST originate from a stored proposal with ID, digest,
  base revision, expiration, operations, risk summary, rollback values, and
  required confirmation.
- Sensitive writes MUST require the MCP host's explicit tool confirmation.
  Write tools MUST NOT be configured or documented as `Always Allow`.
- R1/R2 writes MUST remain bounded by policy and runtime mode. R3 operations
  MUST execute only in `SOUNDCHECK` and MUST require a snapshot, high-risk
  enablement, and host confirmation. R4 operations MUST never take the normal
  proposal path and MUST instead use the separate maintenance boundary.
- Normal R1-R3 writes require typed semantic operations, a stored proposal,
  MCP-host human confirmation, server-owned runtime mode, current policy
  evaluation, reconciliation, snapshot requirements where applicable, exact
  readback, audit, and bounded rollback.
- The model MUST NOT control approval state, runtime mode, write-lock state,
  hardware-verification state, snapshot truth, or maintenance authorization.
- Phantom-power enablement, sample-rate or clock-source changes, firmware
  operations, shutdown, and SD-card formatting MUST NOT be performed through AI
  in the normal proposal path.
- Headamp, routing, scene/cue/snippet recall, and bulk operations MUST capture
  or reference a snapshot before execution.

Rationale: The engineer remains in control, and the bridge must never silently
apply broad or dangerous changes.

### IV. Verification, Audit, and Fail-Closed Recovery
Every write attempt MUST be verifiable, auditable, and recoverable with the
smallest safe rollback. The bridge MUST fail closed when state trust is degraded.

- Every successful write MUST be read back and compared using the console's real
  resolution, grid, and displayed-value rules.
- Failed verification MUST create a failed transaction and attempt targeted
  rollback when policy marks rollback safe.
- Every attempted write, including rejected operations, MUST append an audit
  record with actor/host, proposal, path, old value, requested value, readback,
  result, time, and latency.
- Sensitive values, secrets, tunnel credentials, and private configuration
  values MUST NOT be logged.
- Loss of heartbeat, stale state, malformed packets, unknown firmware, identity
  mismatch, or capability mismatch MUST disable writes until identity and state
  reconciliation pass.
- `OBSERVE` and `OFFLINE` modes MUST NOT emit state-changing OSC packets.
- `EMERGENCY` remains a no-AI-write state. Entry and exit send no console write.
  Exit returns only to `OBSERVE` and requires reconciliation before later writes
  may resume.
- Emulator or Fake M32 evidence MUST NEVER set `hardware_verified=true`.
- The bridge MUST never let the model control write-lock state, approval state,
  snapshot truth, hardware verification, or maintenance authorization.

Rationale: Live control failures must leave a trace and must not continue from
uncertain state.

### V. Emulator Honesty and Minimal MVP Architecture
The MVP MUST remain a local Python modular monolith with no custom chat UI,
full mixer frontend, microservices, external database, local/cloud LLM provider
adapter, or unnecessary runtime dependency.

- Claude Desktop over local MCP `stdio` MUST be the primary host path.
- Optional ChatGPT transport MUST use the same bridge core and MUST bind only to
  loopback/private interfaces behind Secure MCP Tunnel or another approved
  outbound secure tunnel.
- OSC MUST remain on the dedicated private console network. UDP OSC MUST NOT be
  port-forwarded or exposed to the Internet.
- No network scanning or endpoint guessing is allowed.
- Operating-system network bridging, Internet Connection Sharing, and packet
  forwarding between the Internet-facing interface and the console-control
  interface MUST remain disabled.
- Emulator success MUST NOT be described as hardware verification. Hardware
  readiness MUST require the physical M32 acceptance suite.
- `production_live_ready` MUST remain false until release, native platform,
  published-asset, and physical hardware acceptance gates pass.
- Third-party emulator binaries and community source MUST NOT become runtime
  dependencies or redistributed artifacts unless license rights are confirmed.
- Audio analyzer features requiring USB 32x32 PCM capture, FFT/STFT, feedback
  suppression, or delay alignment MUST remain post-MVP features.

Rationale: The plan's safety depends on a small trusted control gateway and
honest separation between simulated evidence and hardware proof.

### VI. Protocol Authority and Registry Fidelity
The user-approved Unofficial X32/M32 OSC Remote Protocol version 4.06-09 MUST
be the primary implementation reference for OSC paths, types, ranges, discrete
values, fader tables, meter blobs, RTA data, and wire behavior. Its provenance
MUST be marked as unofficial in the parameter registry, but implementation
fidelity MUST not be weakened because of that label.

- Every protocol parameter MUST record source document/version/page or section,
  path template, direction, value type, range or enums, discrete grid or table,
  firmware applicability, encoder, decoder, readback comparison, risk class,
  hardware sensitivity, and validation evidence.
- Registry entries MUST be machine-readable, versioned, and reject ambiguous or
  undocumented writable entries.
- A registered MCP tool MUST not remain a placeholder. It MUST either be fully
  implemented for its declared scope or removed from the tools list until it is
  complete.

Rationale: A local control bridge is only safe when its path registry matches
the console protocol precisely and transparently.

### VII. Controlled R4 Maintenance / Break-Glass Boundary
R4 means Critical maintenance / destructive / break-glass. R4 is never part of
the normal proposal/execution path and is never enabled by a normal MCP host
approval alone.

- R4 actions MAY be represented only by a separate `MaintenanceAction` and MUST
  execute only through a separate `MaintenancePermit` and `MaintenanceExecutor`
  boundary.
- The initially approved R4 action names are `phantom_enable`,
  `sample_rate_change`, `clock_change`, `firmware_update`, `format_sd`,
  `raw_osc`, and `arbitrary_path`.
- Every R4 request MUST be prepared as an exact immutable action with typed
  arguments, target path or command, risk explanation, expected effect,
  recovery plan, and digest.
- The digest MUST bind the current configured endpoint, discovered console
  identity, model, firmware, capability profile, operator identity, source
  commit, and maintenance-session identifier.
- R4 MUST require local operator authorization outside the model-controlled MCP
  arguments and MUST use a single-use permit with short expiry and no wildcard,
  batch, permanent, or Always Allow mode.
- Identity, firmware, capability, connection, write-lock, EMERGENCY, snapshot,
  and maintenance-mode checks MUST run immediately before execution.
- The permit MUST be consumed or expire after one execution attempt, whether
  the attempt succeeds or fails.
- R4 MUST fail closed on missing capability evidence, unknown firmware,
  identity drift, endpoint drift, stale state, malformed response, readback
  mismatch, or unavailable rollback or recovery evidence.
- R4 MUST remain unavailable in LIVE mode.
- R4 MUST remain unavailable on emulator/Fake M32 when the action could damage
  hardware or data, except for explicitly non-destructive protocol-contract
  tests.
- `phantom_enable` may be prepared and preflighted in `SOUNDCHECK`, but
  authorization and execution MUST require `MAINTENANCE`. It is channel/headamp
  specific, requires physical hardware acceptance, exact preamp/source mapping,
  protected output isolation as required, local operator confirmation, mandatory
  readback, and a server-generated phantom-disable recovery action bound to the
  consumed permit.
- `phantom_disable` is a server-generated recovery operation stored as a
  `MaintenanceAction`. It may execute only for the exact preamp/path bound to
  the consumed `phantom_enable` permit and is not a generic model-controlled
  MCP tool.
- `sample_rate_change` is MAINTENANCE only, never LIVE, requires physical
  hardware acceptance, clock/AES50/card dependency preflight, a required
  snapshot, local operator confirmation, and mandatory post-change sync
  verification.
- `clock_change` is MAINTENANCE only, never LIVE, requires physical hardware
  acceptance, dependency graph preflight, a required snapshot, local operator
  confirmation, and mandatory post-change sync verification.
- `firmware_update` MUST expose no guessed OSC implementation. It MAY execute
  only when a documented and lab-validated remote mechanism exists in the
  capability registry. Otherwise it MUST return `NOT_REMOTELY_SUPPORTED` and
  provide non-executable operator guidance.
- `format_sd` MUST expose no guessed OSC implementation. It MAY execute only
  when a documented and lab-validated remote mechanism exists, the exact
  storage target is identified, destructive confirmation is local and
  double-confirmed, and recovery limitations are explicit. Otherwise it MUST
  return `NOT_REMOTELY_SUPPORTED`.
- `raw_osc` and `arbitrary_path` MUST remain local break-glass only, never
  general-purpose normal MCP tools. The exact OSC address, type tags, arguments,
  expected response, readback strategy, and protocol-registry compatibility MUST
  be included in the digest. No wildcard address, unbounded batch, subscription
  flood, shell, filesystem, or network action is allowed.
- Console shutdown remains prohibited through AI and through the maintenance
  subsystem.

Rationale: Destructive maintenance is allowed only when the bridge can prove the
exact action, exact target, exact authorization, and exact recovery path.

## Operational Constraints

- Runtime modes MUST be limited to `OFFLINE`, `OBSERVE`, `SOUNDCHECK`,
  `MAINTENANCE`, `LIVE`, and `EMERGENCY`, with write permissions matching the
  plan's risk matrix.
- `MAINTENANCE` is a local operator-controlled break-glass state reserved for
  controlled R4 actions and is never entered by model intent alone.
- Risk levels MUST be enforced as R0 read-only, R1 bounded low-risk, R2 bounded
  moderate-risk, R3 soundcheck-only high-risk, and R4 controlled maintenance /
  break-glass only through the separate maintenance boundary.
- `LIVE` mode MUST limit fader changes to a maximum of +/-3 dB per approved
  operation unless configured lower. This is the owner-approved default LIVE
  safety policy and is separate from OSC protocol precision.
- EQ feedback treatment MUST NOT perform automatic boosts; proposed cuts MUST
  be bounded for gain and Q.
- Headamp writes MUST NOT execute in `LIVE`.
- Routing and recall operations MUST be soundcheck-only unless the operation is
  explicitly approved as an R4 maintenance action; all affected destinations or
  recall scope MUST be shown before execution.
- Measurement microphone role MUST be configured explicitly in the event profile.
  It MUST NOT be inferred only from a channel name.
- Measurement microphone channels MUST be excluded from ordinary vocal/instrument
  heuristics and protected from Main/monitor sends unless the event profile
  explicitly changes that policy.
- RTA conclusions MUST identify the current RTA source and acquisition settings.
  OSC meters MUST NOT be represented as simultaneous per-channel spectra.
- RTA source scanning, if enabled, MUST be restricted to `SOUNDCHECK` and MUST
  save and restore the original source on success, failure, or cancellation.
- Event preflight MUST inspect console clock rate/source, AES50 A/B state, and
  expansion-card sync. A required clock or digital-sync failure MUST block
  `WriteReady` and event readiness until resolved and revalidated.
- Sample-rate and clock maintenance may run only through the controlled R4
  maintenance boundary and never through the normal write path.
- Logs for `stdio` transport MUST go to `stderr`; `stdout` MUST contain MCP
  protocol messages only.
- Snapshots MUST be JSON files containing schema version, identity, firmware,
  time, checksum, and completeness status.
- Audit logs MUST be append-only JSONL during the MVP.

## Quality Gates

The project MUST NOT advance past a phase unless that phase's gate passes and
the result is documented in the relevant SpecKit artifact.

- SpecKit foundation gate: constitution, spec, plan, contracts, data model,
  quickstart, dependency/license register, and tasks MUST be internally
  consistent before implementation begins.
- Codec gate: OSC golden packets, strict type handling, value conversion,
  boundary grids, meter blob parsing, and malformed packet rejection MUST pass.
- Fake gate: project-owned Fake M32 tests for manual changes, failure injection,
  reconnect, stale-state lockout, conflict rejection, and rollback MUST pass
  deterministically.
- Emulator gate: External emulator integration MUST pass on at least one
  supported native development environment before emulator evidence is accepted.
- Before release candidate approval, applicable emulator, runtime, installer,
  and MCP gates MUST be represented in the native macOS, Windows, and Linux
  validation matrix.
- Maintenance gate: every declared R4 action MUST have registry evidence,
  permit checks, local operator authorization, and fail-closed denial tests
  before any execution path is considered valid.
- MCP gate: MCP Inspector and Claude Desktop tests MUST prove tool discovery,
  JSON schemas, read calls, host confirmation for writes, cancellation, timeout,
  malformed input handling, concurrent reads, and clean `stdio` protocol output.
- Cross-platform gate: applicable unit, Fake M32, MCP smoke, packaging,
  startup, runtime, installer, and release gates MUST pass on macOS, Windows,
  and Linux before release candidate approval.
- Safety gate: normal tool calls MUST not reach R4 maintenance paths, raw OSC
  bypasses, malformed proposals, model-supplied custom paths, or `OBSERVE`
  writes.
- Hardware gate: the physical M32 suite MUST pass before any `hardware-verified`
  label, production/live deployment claim, or hardware readiness claim is made.
- Success metrics SC-001 through SC-014 in `PLAN.md` MUST be preserved in specs,
  plans, tasks, and acceptance reports unless amended through Governance.

## Governance

This constitution supersedes conflicting implementation habits, generated task
templates, prompt guidance, and model suggestions for the M32 AI MCP Bridge MVP.
`PLAN.md` remains the source of product scope for the normal MVP surface;
owner-approved governance changes that introduce a controlled maintenance
boundary MUST be recorded there in the same governance patch before
implementation begins. This constitution extracts non-negotiable execution
rules and MUST NOT expand scope by implication.

Amendment Process:

- Any amendment MUST identify the affected `PLAN.md` section, affected principle
  or gate, reason, migration impact, and validation impact.
- Amendments MUST be reviewed for scope drift. A change that adds product scope
  or a controlled maintenance boundary MUST update `PLAN.md` first or in the
  same patch; otherwise it MUST be rejected from the constitution.
- Safety relaxations, R4 changes, public-network exposure, raw OSC exposure,
  hardware-verification claims, or removal of human approval MUST require a
  major version bump and explicit human approval before implementation.
- New mandatory gates, new protected paths, or materially expanded guidance MUST
  require a minor version bump.
- Clarifications that do not change obligations MAY use a patch version bump.
- Ratification date MUST remain the original adoption date. Last amended date
  MUST change on every accepted amendment.

Compliance Review:

- Every spec, plan, task list, and implementation review MUST include a
  Constitution Check covering all core principles and Quality Gates.
- Any violation of a MUST rule is blocking. The project MUST fix the artifact or
  formally amend the constitution before proceeding.
- Deferred hardware inputs listed in `PLAN.md` MUST NOT block emulator/MCP
  development, but they MUST block hardware verification and production/live use.
- Generated tasks MUST include tests whenever required by `PLAN.md`, this
  constitution, a contract, or a quality gate.

**Version**: 2.0.0 | **Ratified**: 2026-07-19 | **Last Amended**: 2026-08-03
