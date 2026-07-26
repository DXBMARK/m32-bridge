# Feature Specification: Local Runtime Setup and Device Verification

**Feature Branch**: `002-local-runtime-setup-and-device-verification`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Create a new feature specification for Local Runtime Setup plus Device/Hardware Verification before official packaging, branding, or production use. The feature must define a safe local setup wizard, stable launcher behavior, runtime diagnostics, stdio MCP behavior, OS-aware recommendations, and device identity classification without adding control scope, WebUI, packaging, remote MCP, or real hardware writes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a Local Runtime Safely (Priority: P1)

An operator runs a local setup command to configure the bridge endpoint and confirm that the configured target responds to a read-only identity probe before using the bridge from a terminal or local MCP host.

**Why this priority**: Without a clear setup path, operators cannot reliably start the bridge from Claude Desktop or another local MCP host, and runtime failures are difficult to diagnose.

**Independent Test**: Can be fully tested by running the setup flow with valid, invalid, missing, and timed-out endpoint values and confirming that the resulting configuration and diagnostics are structured, clear, and read-only.

**Acceptance Scenarios**:

1. **Given** no saved runtime configuration, **When** the operator runs `m32-bridge setup` and provides host, port, optional label/environment, and intended target type, **Then** the system tests `/info` only, reports the result, and saves a non-secret application configuration only after the operator confirms.
2. **Given** an endpoint that does not respond, **When** the operator runs setup, **Then** the system reports a clear timeout or connection failure, does not claim setup success, and sends zero OSC writes.
3. **Given** the operator requests automation-friendly output, **When** setup is run with JSON output enabled, **Then** all setup status, endpoint, probe, and saved-config fields are returned as structured JSON.
4. **Given** no console host is configured through command input, environment, user config, or allowed development config, **When** setup-related diagnostics run, **Then** the system returns `NO_CONSOLE_HOST` and guides the user to run setup instead of guessing or scanning.

---

### User Story 2 - Detect Target Type Without Overclaiming Hardware (Priority: P1)

An operator runs a device detection command to understand whether the configured endpoint appears to be unconfigured, emulator-connected, connected but unverified, a hardware candidate, or hardware verified.

**Why this priority**: Safe runtime use depends on separating connectivity from hardware verification. Emulator and partial device evidence must never be mistaken for production-ready hardware.

**Independent Test**: Can be tested by providing no config, wrong endpoint, known emulator endpoint, partially responding endpoint, and manually supplied hardware acceptance evidence, then verifying the classification and safety flags.

**Acceptance Scenarios**:

1. **Given** a known emulator endpoint responds to `/info`, **When** the operator runs `m32-bridge detect-device`, **Then** the result is `EMULATOR_CONNECTED`, `connected=true`, `hardware_verified=false`, and `production_live_ready=false`.
2. **Given** a responding endpoint with insufficient evidence to prove real hardware, **When** detection completes, **Then** the result is `CONNECTED_UNVERIFIED` or `HARDWARE_CANDIDATE`, not `HARDWARE_VERIFIED`.
3. **Given** real hardware acceptance evidence is absent, **When** detection finds IP/OSC and optional USB evidence, **Then** the system still keeps `hardware_verified=false`.

---

### User Story 3 - Use Local MCP Hosts Through Stdio Reliably (Priority: P1)

A local AI app such as Claude Desktop, Antigravity, or a Codex-compatible MCP client starts the bridge as a local subprocess over stdio and receives clean MCP messages without requiring a terminal window or network MCP port.

**Why this priority**: The current MVP relies on local stdio MCP. Users need clear expectations for how the bridge is launched and why it should use a stable launcher rather than a global Python command.

**Independent Test**: Can be tested by starting the MCP server from a local MCP-compatible process using the configured launcher, verifying stdout protocol cleanliness, stderr logging, and read-only diagnostics.

**Acceptance Scenarios**:

1. **Given** a valid saved runtime configuration, **When** a local MCP host launches `m32-bridge mcp-server`, **Then** the bridge communicates over stdin/stdout, logs only to stderr, and opens no local MCP network port.
2. **Given** the user requests MCP configuration guidance, **When** snippets are displayed, **Then** the snippets require manual copy and reference a stable launcher command, not a global `py` command.
3. **Given** runtime dependencies are missing or the launcher is unavailable, **When** the MCP server or diagnostics are invoked, **Then** the user sees a clear runtime/dependency diagnostic instead of a silent timeout.
4. **Given** a Claude or AI MCP host configuration is generated for normal use, **When** the snippet is shown, **Then** it launches `m32-bridge` without embedding host or port and relies on the saved user config by default.

---

### User Story 4 - Inspect and Validate Local Configuration (Priority: P2)

An operator can inspect and validate the saved runtime configuration without exposing secrets, modifying Claude Desktop config, or changing console state.

**Why this priority**: Supportable local operation requires a transparent configuration location, predictable validation, and safe failure messages.

**Independent Test**: Can be tested by showing and validating valid, invalid, missing, and malformed configuration files while verifying that no secrets are stored or displayed.

**Acceptance Scenarios**:

1. **Given** a saved application config, **When** the operator runs `m32-bridge config show`, **Then** the system displays the config location and non-secret endpoint metadata.
2. **Given** an invalid host or port, **When** the operator runs `m32-bridge config validate`, **Then** validation fails with a specific error and no connection write is attempted.
3. **Given** no saved config, **When** config commands are run, **Then** the system reports `NOT_CONFIGURED` with guidance to run setup.
4. **Given** host and port values are available from more than one supported source, **When** the system resolves configuration, **Then** explicit command input wins over environment variables, environment variables win over user config, and project-local config is used only for development or testing contexts.

---

### User Story 5 - Receive OS-Aware Installation Guidance (Priority: P2)

An operator receives platform-appropriate guidance for running the bridge locally without assuming global Python, administrator privileges, or production packaging.

**Why this priority**: The setup experience must work across macOS, Windows, Linux, and Raspberry Pi OS while keeping this feature short of official packaging.

**Independent Test**: Can be tested on each supported operating-system family by checking that the recommended path uses user-local setup by default, identifies optional privileged cases, and shows JSON-capable diagnostics.

**Acceptance Scenarios**:

1. **Given** macOS, Windows, Linux, or Raspberry Pi OS, **When** the operator asks for setup recommendations, **Then** the system displays user-local recommendations for that OS and identifies optional future packaging paths separately.
2. **Given** administrator privileges are unavailable, **When** setup runs in the default mode, **Then** the system does not require administrator privileges.
3. **Given** a user asks about USB presence, **When** detection runs on the OS, **Then** USB detection is best-effort and failure to inspect USB does not fail setup.

---

### User Story 6 - Use an Optional Interactive Shell (Priority: P2)

An operator can run `m32-bridge` with no subcommand to open an optional interactive shell with slash commands for setup, diagnostics, configuration, MCP guidance, mode display, and local lock state actions.

**Why this priority**: Some operators prefer a guided shell during setup and troubleshooting, but normal CLI subcommands must remain available for automation, documentation, and MCP host integration.

**Independent Test**: Can be tested by launching `m32-bridge` with no subcommand, running every supported slash command, checking matching CLI equivalents where appropriate, and confirming read-only slash commands send zero OSC writes.

**Acceptance Scenarios**:

1. **Given** the operator runs `m32-bridge` with no subcommand, **When** neither `--help` nor `--version` is provided, **Then** the system opens the interactive shell and shows shell-specific help.
2. **Given** the operator runs `m32-bridge --help` or `m32-bridge --version`, **When** the command starts, **Then** the system prints normal command output and does not enter the interactive shell.
3. **Given** the operator is inside the interactive shell, **When** they run `/getinfo`, `/test`, `/doctor`, `/detect`, `/config`, `/runsetup`, `/mode`, `/lock`, or `/unlock`, **Then** the command completes without exposing raw OSC or arbitrary path execution.
4. **Given** documentation or help output mentions slash commands, **When** the output is shown, **Then** it clearly states that slash commands work only inside the `m32-bridge` interactive shell and are not standalone operating-system terminal commands.
5. **Given** `m32-bridge` is launched with no subcommand in a non-interactive environment where stdin is not a terminal, **When** the command starts, **Then** the system must not open the interactive shell or wait for input and must return a structured error or help response that suggests explicit commands such as `m32-bridge setup`, `m32-bridge health`, and `m32-bridge mcp-server`.

### Edge Cases

- Config file is missing, malformed, unreadable, or contains an invalid host or port.
- Host is missing from all allowed configuration sources.
- Port is missing while host exists.
- Endpoint responds from an unexpected address.
- `/info` succeeds but optional capability reads time out or return unsupported.
- Endpoint appears to be an emulator even when the operator selected "hardware" as the intended target type.
- USB audio device is present but OSC endpoint is absent or unreachable.
- USB inspection command is unavailable, blocked, or returns insufficient details.
- Launcher command is missing from the local environment.
- MCP host launches the bridge with a different working directory or environment from the terminal.
- User asks for Claude Desktop configuration but expects automatic file modification.
- User types a slash command directly in the operating-system terminal instead of inside the interactive shell.
- User runs `m32-bridge` with no subcommand from a non-interactive environment where stdin is not a terminal.
- User requests `/mcp` or `/claude` from inside the shell while no saved config exists.
- Remote MCP or cloud use is requested before local-agent, auth, TLS, pairing, audit, rate-limit, and emergency-lock requirements are satisfied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a local setup flow reachable through a stable launcher command named `m32-bridge setup`.
- **FR-002**: Setup MUST accept host, port, optional label/environment, and intended target type with allowed target values `emulator`, `hardware`, and `unknown`.
- **FR-003**: Setup MUST test the configured endpoint using `/info` only and MUST NOT send `/set` or any state-changing OSC message.
- **FR-004**: Setup MUST show whether the `/info` probe connected, timed out, failed validation, or returned an unexpected response address.
- **FR-005**: Setup MUST save configuration only to an application-owned user-local config path by default and MUST clearly display the saved config location.
- **FR-006**: Setup MUST support a project-local config location for test and development runs without changing the user-local default.
- **FR-007**: The system MUST support configuration through CLI arguments, environment variables, a saved user config file, and project-local config for development or testing only.
- **FR-008**: Configuration resolution MUST prefer CLI arguments first, then environment variables, then saved user config, then project-local config only when explicitly in a development or test context.
- **FR-009**: `M32_CONSOLE_HOST` MUST NOT be hardcoded in production behavior or official examples except as a clearly labelled example value.
- **FR-010**: `M32_CONSOLE_PORT` MUST default to `10023` when a host is configured and no port is provided, but the port MUST remain user-editable in every supported configuration source.
- **FR-011**: If no console host is configured from an allowed source, the system MUST NOT guess, scan, probe common subnets, or infer a host by default.
- **FR-012**: When host is missing, the system MUST return `NO_CONSOLE_HOST` and guide the user to run setup.
- **FR-013**: Setup, config, doctor, and device-detection commands MUST support JSON output for automation and testing.
- **FR-014**: The system MUST expose normal CLI commands for `health`, `setup`, `get-info`, `config show`, `config set --host <host> --port <port>`, `config validate`, `doctor-runtime`, `detect-device`, `mcp-server`, and `help`.
- **FR-015**: The system MUST NOT assume `py` or a globally installed Python exists for end-user operation.
- **FR-016**: Developer guidance MAY use a development runner, but end-user and MCP-host guidance MUST reference the stable launcher command or a future packaged executable.
- **FR-017**: MCP configuration snippets MUST be manual-copy only and MUST NOT automatically modify Claude Desktop, Antigravity, Codex, or other host configuration files.
- **FR-018**: Claude and AI MCP configuration snippets for normal use SHOULD launch `m32-bridge` without embedding host or port, allowing the bridge to read saved user configuration.
- **FR-019**: Environment host and port overrides MAY appear only in clearly labelled advanced or manual examples.
- **FR-020**: Runtime diagnostics MUST report missing launcher, missing dependency, invalid config, wrong working directory, missing environment, wrong host, wrong port, timeout, missing host, and unexpected response address in user-understandable terms.
- **FR-021**: The local MCP server MUST use stdio by default, where the MCP host starts the bridge process and communicates through stdin/stdout.
- **FR-022**: Local stdio MCP mode MUST NOT require an open terminal window during normal use.
- **FR-023**: Local stdio MCP mode MUST NOT open a network MCP port.
- **FR-024**: Logs for stdio MCP mode MUST go to stderr and MUST NOT corrupt stdout protocol messages.
- **FR-025**: The system MUST provide OS-aware setup recommendations for macOS, Windows, Linux, and Raspberry Pi OS.
- **FR-026**: macOS recommendations MUST prefer user-local install or a future app/launcher, Claude Desktop stdio launch, best-effort USB detection, and no administrator privileges by default.
- **FR-027**: Windows recommendations MUST prefer user install or a future executable launcher, best-effort USB detection, and no administrator privileges unless installing a service or system-wide component.
- **FR-028**: Linux recommendations MUST prefer user-local install/package, best-effort USB and audio subsystem detection, optional user service guidance, and no cloud exposure by default.
- **FR-029**: Raspberry Pi OS recommendations MUST describe future dedicated bridge mode, optional service operation, fixed FOH/local bridge suitability, and no cloud exposure by default.
- **FR-030**: The system MUST provide a Device Identity and Hardware Detector that can classify `NOT_CONFIGURED`, `EMULATOR_CONNECTED`, `CONNECTED_UNVERIFIED`, `HARDWARE_CANDIDATE`, and `HARDWARE_VERIFIED`.
- **FR-031**: Device detection MUST collect or attempt to collect `/info`, firmware/system/API version, model/family, configured host/port, response address, latency, capability map, and optional clock, sync, scene, snippet, USB, and MAC-address evidence.
- **FR-032**: Optional capability failures during detection MUST be reported as capability limitations, not as loss of connection when `/info` proves the endpoint is reachable.
- **FR-033**: `connected=true` MUST NOT imply `hardware_verified=true`.
- **FR-034**: Emulator evidence MUST NEVER produce `HARDWARE_VERIFIED`.
- **FR-035**: USB detection alone MUST NOT authorize control, hardware verification, production/live readiness, or write enablement.
- **FR-036**: IP/OSC verification alone MUST prove only endpoint connectivity unless sufficient real hardware acceptance evidence exists.
- **FR-037**: `HARDWARE_VERIFIED` MUST require sufficient real hardware acceptance evidence from a later hardware acceptance process.
- **FR-038**: Real hardware write capability MUST remain blocked until explicit hardware acceptance evidence exists.
- **FR-039**: USB detection MUST be best-effort and MUST report `usb_detected`, `usb_device_name`, vendor/product when available, `usb_confidence`, and `usb_control_supported=false` by default.
- **FR-040**: The default runtime mode MUST be `OBSERVE`.
- **FR-041**: `production_live_ready` MUST default to false.
- **FR-042**: `hardware_verified` MUST default to false.
- **FR-043**: Setup, doctor, config validation, and device detection MUST be read-only and MUST send zero OSC writes.
- **FR-044**: This feature MUST NOT expand R3/R4 permissions or change EMERGENCY behavior from the existing governance model.
- **FR-045**: Installation strategy documentation MUST distinguish current development install, current/future user-local launcher, future OS packages, future Raspberry Pi service/image, future MCP extension bundle, and future portable kit.
- **FR-046**: Installation strategy documentation MUST state that USB autorun is unreliable and MUST NOT be treated as a supported setup dependency.
- **FR-047**: Local stdio MUST be the default MCP mode.
- **FR-048**: Remote MCP or serve mode MAY be described as a future capability only and MUST be disabled by default.
- **FR-049**: Remote mode requirements MUST include authentication, TLS, pairing, audit, rate limits, emergency lock, no direct Internet exposure of OSC, and a local agent or tunnel for access to a private M32 network.
- **FR-050**: Administrator privileges MUST NOT be required by default.
- **FR-051**: Administrator privileges MAY be described only for optional system-wide install, Windows service, macOS LaunchDaemon, Linux system service, or firewall/service registration.
- **FR-052**: AI models MUST NOT receive operating-system administrator privileges through this feature.
- **FR-053**: AI access MUST remain limited to policy-governed MCP tools.
- **FR-054**: Running `m32-bridge` with no subcommand MUST open an optional interactive shell unless `--help` or `--version` is provided.
- **FR-055**: The interactive shell MUST support slash commands `/help`, `/runsetup`, `/getinfo`, `/config`, `/config set host <host>`, `/config set port <port>`, `/test`, `/doctor`, `/detect`, `/mcp`, `/claude`, `/mode`, `/lock`, `/unlock`, and `/exit`.
- **FR-056**: Documentation and help output MUST clearly state that slash commands are valid only inside the `m32-bridge` interactive shell and MUST NOT present slash commands as standalone operating-system terminal commands.
- **FR-057**: Every slash command MUST have a normal CLI equivalent where an equivalent is appropriate for non-interactive use.
- **FR-058**: `/runsetup`, `/getinfo`, `/config`, `/test`, `/doctor`, and `/detect` MUST be read-only with respect to OSC and MUST report `osc_writes_sent=0` when applicable.
- **FR-059**: `/lock` and `/unlock` MUST affect only local write-lock state and MUST NOT send OSC writes.
- **FR-060**: No slash command MAY expose raw OSC, arbitrary path execution, shell execution, firmware operations, shutdown operations, phantom power enablement, sample-rate changes, or clock changes.
- **FR-061**: If `m32-bridge` is launched with no subcommand in a non-interactive environment where stdin is not a terminal, the system MUST NOT open the interactive shell or block waiting for input, and MUST return a structured error or help response explaining that the interactive shell requires an interactive terminal and suggesting explicit commands including `m32-bridge setup`, `m32-bridge health`, and `m32-bridge mcp-server`.
- **FR-062**: `/unlock` and any normal CLI equivalent MUST NOT bypass reconciliation, runtime mode, EMERGENCY state, stale-state checks, disconnected-state checks, or write-governance rules; when the system is disconnected, stale, unreconciled, or in EMERGENCY, unlock MUST be rejected with a clear reason and `osc_writes_sent=0`.
- **FR-063**: The feature MUST NOT introduce WebUI, database, backend service, microservice split, official branding, packaged installers, cloud remote MCP, ChatGPT tunnel implementation, USB autorun, or sound/control policy changes.

### Key Entities *(include if feature involves data)*

- **Runtime Configuration**: Non-secret local configuration containing endpoint host, endpoint port, optional label/environment, intended target type, config version, last validation summary, and source metadata showing whether values came from CLI arguments, environment variables, saved user config, or project-local development config.
- **Setup Result**: The outcome of local setup, including config path, validation status, `/info` probe status, response address, latency, target classification, and zero-write evidence.
- **Device Identity Report**: A structured view of endpoint identity, including connection status, target classification, model/family, version fields, configured endpoint, observed response address, latency, capability map, optional sync details, and safety flags.
- **USB Detection Evidence**: Best-effort physical presence evidence containing detected device flag, device name, vendor/product identifiers when available, confidence, inspection limitations, and `usb_control_supported=false` by default.
- **MCP Launch Guidance**: Manual-copy guidance for local MCP hosts that explains stdio subprocess behavior, stable launcher use, stderr logging, stdout protocol cleanliness, and no local MCP network port.
- **OS Recommendation**: Platform-specific guidance for user-local setup, optional privileged installation cases, USB detection expectations, and future packaging paths.
- **Interactive Shell Session**: Optional local command session that accepts slash commands, displays shell-only help, maps slash commands to safe CLI equivalents, and keeps local state actions separate from OSC writes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of setup, config validation, doctor, and device-detection acceptance tests prove `osc_writes_sent=0`.
- **SC-002**: 100% of emulator detection cases classify as `EMULATOR_CONNECTED` and keep `hardware_verified=false`.
- **SC-003**: 100% of no-config, invalid-config, wrong-host, wrong-port, timeout, and unexpected-response cases return a clear status and a human-readable reason.
- **SC-004**: 100% of command outputs support structured JSON fields for status, configured endpoint, attempted path, latency, write count, and hardware verification state.
- **SC-005**: A first-time operator can identify the saved configuration path and next manual MCP setup step in under 2 minutes using command output alone.
- **SC-006**: 100% of generated MCP host snippets use a stable launcher command or future executable path and never require global `py`.
- **SC-007**: 100% of MCP host guidance requires manual copy and never modifies host configuration files automatically.
- **SC-008**: 100% of normal Claude or AI MCP snippets omit embedded host and port values and rely on saved user configuration.
- **SC-009**: 100% of missing-host cases return `NO_CONSOLE_HOST` without default scanning or guessing.
- **SC-010**: 100% of official examples that mention `M32_CONSOLE_HOST` label it as an example or advanced/manual override.
- **SC-011**: 100% of configuration resolution tests prove CLI arguments, environment variables, user config, and project-local development config are handled in the documented precedence order.
- **SC-012**: 100% of stdio MCP startup checks keep protocol output clean by sending logs away from stdout.
- **SC-013**: 100% of OS recommendation outputs identify whether administrator privileges are unnecessary, optional, or out of scope for the current action.
- **SC-014**: USB detection absence or failure does not block setup in any supported OS recommendation path.
- **SC-015**: No command, status, or documentation created by this feature claims production/live readiness before later hardware acceptance evidence.
- **SC-016**: 100% of interactive shell slash commands are documented as shell-only commands and are not shown as standalone operating-system terminal commands.
- **SC-017**: 100% of slash commands with appropriate non-interactive use have documented normal CLI equivalents.
- **SC-018**: 100% of `/runsetup`, `/getinfo`, `/config`, `/test`, `/doctor`, and `/detect` acceptance tests prove zero OSC writes.
- **SC-019**: 100% of `/lock` and `/unlock` acceptance tests prove only local write-lock state changes and zero OSC writes.
- **SC-020**: No requirement in this feature adds WebUI, database, backend service, microservice architecture, official packaging, remote MCP implementation, ChatGPT tunnel implementation, or sound/control policy changes.

## Assumptions

- The existing MVP runtime acceptance, emulator gate, Claude Desktop stdio gate, runtime diagnostics, read-only overview degradation handling, and safety guards remain in place.
- The stable launcher name for end-user command examples is `m32-bridge`.
- The interactive shell is a local operator convenience and does not replace normal CLI subcommands or MCP tools.
- The default user-local configuration path is application-owned and non-secret; project-local configuration is allowed for tests and development.
- Host values are environment-specific and are not safe to hardcode in production or normal MCP host configuration examples.
- Port `10023` is the expected default OSC port for this bridge family, but users may need to change it for emulator, lab, or site-specific setups.
- Device detection may attempt optional reads beyond `/info`, but setup connection testing is limited to `/info` only.
- External emulator and physical hardware evidence are treated differently even when both respond over the same OSC network protocol.
- Remote MCP, packaging, and branded app delivery require later specifications before implementation.

## Out of Scope

- Real hardware write validation.
- Official branded desktop app.
- Full GUI application.
- WebUI.
- Cloud remote MCP.
- ChatGPT tunnel implementation.
- USB autorun.
- Packaged installers.
- Changing sound/control policy.
- Changing emergency/write governance.
- Automatic modification of Claude Desktop or other MCP host configuration files.
- Using Fake M32 or emulator evidence as production readiness or hardware verification.
