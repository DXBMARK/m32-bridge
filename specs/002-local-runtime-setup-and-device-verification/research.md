# Research: Local Runtime Setup and Device Verification

## Decision 1: Configuration Resolution

**Decision**: Resolve effective runtime endpoint values in this order: CLI arguments, environment variables, saved user config, then project-local config only when explicitly running in a development or test context.

**Rationale**: Explicit operator input must win over ambient environment and persisted defaults. Project-local config is useful for tests and development but must not unexpectedly override a user's normal runtime.

**Alternatives Rejected**:

- Defaulting or scanning for a host when missing: rejected because the spec requires `NO_CONSOLE_HOST` and no guessing.
- Project-local config before user config: rejected because it could make MCP subprocess behavior depend on current working directory.

## Decision 2: Missing Host Behavior

**Decision**: If no host is found from allowed sources, return `NO_CONSOLE_HOST` with guidance to run setup.

**Rationale**: A missing host is a configuration problem, not a discovery request. Default subnet scans could contact unintended devices and would obscure the reason Claude-launched or terminal-launched runtime differs.

**Alternatives Rejected**:

- Probe common private subnets: rejected as unsafe and outside scope.
- Assume localhost or a common console IP: rejected because `M32_CONSOLE_HOST` must not be hardcoded in production behavior.

## Decision 3: User-Local Configuration

**Decision**: Save non-secret runtime configuration to an application-owned user-local config path by default. Expose the path in command output. Allow project-local config only for development or test contexts.

**Rationale**: Claude Desktop and other local MCP hosts may launch the bridge from different working directories. A user-local config makes default MCP snippets stable without embedding host/port.

**Alternatives Rejected**:

- Automatically editing Claude Desktop or other host config files: rejected by spec.
- Storing endpoint only in environment variables: rejected because MCP host environments often differ from terminal environments.

## Decision 4: Port Default

**Decision**: Default port to `10023` only after a host is configured, and keep it editable through CLI, environment, user config, and development/test config.

**Rationale**: `10023` is the expected console OSC port family default, but emulator, lab, and site-specific setups may differ.

**Alternatives Rejected**:

- Hardcoding host/port into official examples: rejected by configuration-flexibility requirements.
- Requiring port every time: rejected because a safe editable default improves setup usability.

## Decision 5: Stable Launcher

**Decision**: End-user and MCP-host guidance uses `m32-bridge`. Developer-only guidance may mention development runners separately, but normal guidance must not assume global `py`.

**Rationale**: Claude Desktop subprocess launches must not depend on shell aliases, PATH assumptions for Python launchers, or terminal-specific setup.

**Alternatives Rejected**:

- Official examples based on `py -m m32_bridge`: rejected because `py` is not guaranteed globally available.
- Embedding full interpreter paths in normal MCP snippets: rejected because snippets should prefer saved user config and a stable launcher.

## Decision 6: CLI and Interactive Shell Split

**Decision**: Normal CLI subcommands are primary. Running `m32-bridge` with no subcommand opens the optional interactive shell only when stdin is a TTY. Non-interactive no-subcommand launch returns structured help/error instead of blocking.

**Rationale**: Automation and MCP hosts require deterministic process behavior. Slash commands are useful for local operators but must be shell-only.

**Alternatives Rejected**:

- Making slash commands standalone OS terminal commands: rejected by spec.
- Opening an interactive prompt in non-TTY contexts: rejected because it can hang MCP hosts and scripts.

## Decision 7: Device Classification

**Decision**: Device detection reports one of `NOT_CONFIGURED`, `EMULATOR_CONNECTED`, `CONNECTED_UNVERIFIED`, `HARDWARE_CANDIDATE`, or `HARDWARE_VERIFIED`.

**Rationale**: Connectivity is not hardware verification. Emulator responses, Fake M32 responses, OSC `/info`, USB presence, and optional capability reads are evidence with different meanings.

**Alternatives Rejected**:

- Treating `/info` success as hardware verification: rejected because physical M32 acceptance is a separate gate.
- Treating optional path timeout as disconnected when `/info` succeeds: rejected because optional capability limitations must be reported separately.

## Decision 8: USB Detection

**Decision**: USB evidence is best-effort, non-blocking, and reports `usb_control_supported=false` by default.

**Rationale**: USB presence may help human diagnosis, but it cannot authorize control, prove hardware verification, or block setup if unavailable.

**Alternatives Rejected**:

- Requiring USB detection for setup: rejected because many valid control paths are network-only.
- Using USB detection to enable writes: rejected by the hardware-verification requirements.

## Decision 9: MCP Host Guidance

**Decision**: Local stdio remains the default MCP mode. Claude/AI MCP snippets are manual-copy only, launch `m32-bridge mcp-server`, and normally omit host/port so the bridge reads user config.

**Rationale**: This matches local MCP process behavior and prevents documentation from becoming an implicit config editor.

**Alternatives Rejected**:

- Opening a network MCP port by default: rejected by local stdio requirements.
- Implementing remote MCP, tunnels, pairing, or public serving: rejected as future-only scope.

## Decision 10: Unlock Governance

**Decision**: `/unlock` and any CLI equivalent affect only local write-lock state and must be denied when the runtime is disconnected, stale, unreconciled, or in EMERGENCY, or when existing write-governance rules would block writes.

**Rationale**: Unlock must not be a bypass around reconciliation, runtime mode, emergency state, or safety policy. Denials must report `osc_writes_sent=0`.

**Alternatives Rejected**:

- Making unlock a direct write-enablement override: rejected because it weakens fail-closed behavior.
- Sending an OSC message from lock/unlock: rejected by spec.

## Decision 11: OS-Aware Recommendations

**Decision**: Recommendations are platform-specific, user-local by default, and distinguish optional privileged cases from current behavior.

**Rationale**: macOS, Windows, Linux, and Raspberry Pi OS differ in launchers, services, USB inspection, and packaging expectations.

**Alternatives Rejected**:

- Requiring administrator privileges by default: rejected by spec.
- Implementing packages/installers in this feature: rejected as future packaging strategy only.

## Decision 12: Structured Output Contract

**Decision**: Runtime-facing commands and diagnostics share a JSON envelope with endpoint, attempted path, latency, write count, hardware verification, production readiness, status, error code, and recommendations.

**Rationale**: The same fields must support terminal audit, MCP stdio diagnostics, and automated tests without scraping human text.

**Alternatives Rejected**:

- Human text only: rejected because acceptance criteria require JSON-capable diagnostics.
- Separate incompatible envelopes per command: rejected because tests and support need stable fields.

## Decision 13: Future Packaging Strategy

**Decision**: Document current development install, current/future user-local launcher, future OS packages, future Raspberry Pi service/image, future MCP extension bundle, and future portable kit without implementing packaging in this feature.

**Rationale**: Operators need realistic guidance, but implementation must stop before official packaging or installer work.

**Alternatives Rejected**:

- Starting installer/package work now: rejected by scope.
- Treating USB autorun as a supported setup dependency: rejected because it is unreliable and explicitly out of scope.
