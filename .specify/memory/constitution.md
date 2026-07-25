<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles:
- III. Human-Approved Proposal Execution: R3 limited to SOUNDCHECK only in MVP
- V. Emulator Honesty and Minimal MVP Architecture: network bridge/ICS/forwarding ban added
Added sections:
- Cross-platform Quality Gate
- Event Readiness Gate
Removed sections:
- None
Files modified:
- .specify/memory/constitution.md only
Files requiring future review:
- .specify/templates/plan-template.md
- .specify/templates/spec-template.md
- .specify/templates/tasks-template.md
- .agents/skills/speckit-tasks/SKILL.md
No other files were modified.
Follow-up TODOs:
- None
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
  `set_sample_rate` MUST NOT exist in the MVP MCP surface.
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
  enablement, and host confirmation. R4 operations MUST remain blocked in MVP.
- Phantom-power enablement, sample-rate or clock-source changes, firmware
  operations, shutdown, and SD-card formatting MUST NOT be performed through AI
  in the MVP.
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
- Operating-system network bridging, Internet Connection Sharing, and packet
  forwarding between the Internet-facing interface and the console-control
  interface MUST remain disabled.
- Emulator success MUST NOT be described as hardware verification. Hardware
  readiness MUST require the physical M32 acceptance suite.
- Third-party emulator binaries and community source MUST NOT become runtime
  dependencies or redistributed artifacts unless license rights are confirmed.
- Audio analyzer features requiring USB 32x32 PCM capture, FFT/STFT, feedback
  suppression, or delay alignment MUST remain post-MVP features.

Rationale: The plan's safety depends on a small trusted control gateway and
honest separation between simulated evidence and hardware proof.

## Operational Constraints

- Runtime modes MUST be limited to `OFFLINE`, `OBSERVE`, `SOUNDCHECK`, `LIVE`,
  and `EMERGENCY`, with write permissions matching the plan's risk matrix.
- Risk levels MUST be enforced as R0 read-only, R1 bounded low-risk, R2 bounded
  moderate-risk, R3 soundcheck-only high-risk, and R4 blocked in MVP.
- `LIVE` mode MUST limit fader changes to a maximum of +/-3 dB per approved
  operation unless configured lower.
- EQ feedback treatment MUST NOT perform automatic boosts; proposed cuts MUST
  be bounded for gain and Q.
- Headamp writes MUST NOT execute in `LIVE`.
- Routing and recall operations MUST be soundcheck-only and MUST show affected
  destinations or recall scope before execution.
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
- Emulator gate: Patrick-Gilles Maillot X32 Emulator integration tests MUST pass
  on the primary Windows development environment before emulator evidence is
  used for MCP readiness.
- MCP gate: MCP Inspector and Claude Desktop tests MUST prove tool discovery,
  JSON schemas, read calls, host confirmation for writes, cancellation, timeout,
  malformed input handling, concurrent reads, and clean `stdio` protocol output.
- Cross-platform gate: unit, Fake M32, MCP smoke, packaging, and startup tests
  MUST pass on Windows and macOS before the MVP is released.
- Safety gate: R4 paths, raw OSC bypasses, malformed proposals, model-supplied
  custom paths, and `OBSERVE` writes MUST remain blocked under direct tool calls.
- Hardware gate: the physical M32 suite MUST pass before any `hardware-verified`
  label, production/live deployment claim, or hardware readiness claim is made.
- Success metrics SC-001 through SC-014 in `PLAN.md` MUST be preserved in specs,
  plans, tasks, and acceptance reports unless amended through Governance.

## Governance

This constitution supersedes conflicting implementation habits, generated task
templates, prompt guidance, and model suggestions for the M32 AI MCP Bridge MVP.
`PLAN.md` remains the source of product scope; this constitution extracts its
non-negotiable execution rules and MUST NOT expand that scope.

Amendment Process:

- Any amendment MUST identify the affected `PLAN.md` section, affected principle
  or gate, reason, migration impact, and validation impact.
- Amendments MUST be reviewed for scope drift. A change that adds product scope
  MUST update the plan/spec first or be rejected from the constitution.
- Safety relaxations, R4 changes, public-network exposure, raw OSC exposure,
  hardware-verification claims, or removal of human approval MUST require a major
  version bump and explicit human approval before implementation.
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

**Version**: 1.1.0 | **Ratified**: 2026-07-19 | **Last Amended**: 2026-07-19
