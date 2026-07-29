# Feature Specification: Cross-Platform Installers and First-Run Setup

**Feature Branch**: `[003-cross-platform-installers-and-first-run-setup]`

**Created**: 2026-07-26

**Status**: Draft

**Input**: User description: "Create a specification for installing and running M32 Bridge on macOS, Linux, WSL, Windows PowerShell/CMD, and Raspberry Pi OS in a natural user workflow, prioritizing install scripts and integrating the first-run interactive setup wizard into the install experience."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install with a User-Local Script (Priority: P1)

A user installs M32 Bridge on their operating system with the recommended user-local installer, without needing administrator privileges by default and without needing a globally installed Python launcher.

**Why this priority**: Installation is currently the largest adoption gap. Users need a normal entry point before they can use the existing `m32-bridge` CLI, setup, diagnostics, or local MCP server.

**Independent Test**: Can be tested by starting from a clean user account on each supported OS, running the documented installer path, and confirming the stable `m32-bridge` launcher is available from the user's environment.

**Acceptance Scenarios**:

1. **Given** a macOS or Linux user account without M32 Bridge installed, **When** the user runs the documented POSIX installer path, **Then** M32 Bridge is installed in a user-local application location and `m32-bridge health` can be launched without relying on global `py`.
2. **Given** a Windows user account without M32 Bridge installed, **When** the user runs the documented PowerShell installer path, **Then** M32 Bridge is installed in a user-local application location and a CMD-compatible `m32-bridge` launcher is available.
3. **Given** a user who prefers safer installation review, **When** they download the installer script, inspect it, and run it locally, **Then** the documented workflow works equivalently to the one-line install command.
4. **Given** the required runtime manager is unavailable, **When** the installer runs, **Then** it either installs it in user space or gives clear next-step guidance without requiring administrator privileges by default.

---

### User Story 2 - Complete First-Run Setup During Installation (Priority: P1)

After installation, a user is guided through first-run setup to configure the console endpoint, verify read-only connectivity, classify the target, and save user-local configuration only after confirmation.

**Why this priority**: A successful install is not useful until the bridge knows which console endpoint to use. The setup flow must remain safe and must not guess, scan, or write to the console.

**Independent Test**: Can be tested by completing the installer-triggered setup wizard in a terminal and verifying that only `/info` is attempted, no writes are sent, and the saved configuration enables `m32-bridge get-info`.

**Acceptance Scenarios**:

1. **Given** the installer completes in an interactive terminal, **When** first-run setup begins, **Then** it displays the detected OS, recommended mode, and prompts for host, port default `10023`, label/environment, and intended target type.
2. **Given** the user enters a reachable endpoint, **When** the setup wizard probes the endpoint, **Then** it performs `/info` only, displays the result classification, reports `osc_writes_sent=0`, and asks for confirmation before saving configuration.
3. **Given** the setup environment is non-interactive, **When** first-run setup is invoked, **Then** it does not hang and returns a structured response with explicit commands for automation or manual setup.
4. **Given** the target is an emulator, **When** setup classifies the endpoint, **Then** it reports emulator status honestly and does not mark hardware as verified.

---

### User Story 3 - Verify the Installed Runtime (Priority: P2)

A user can confirm that the installation, saved configuration, read-only console access, device classification, and Claude local MCP runtime are ready for local use.

**Why this priority**: Users need a reliable checklist after installation, especially across OS-specific shells and terminal behavior.

**Independent Test**: Can be tested by running the post-install verification commands and confirming each command returns a clear pass, warning, or structured failure without writes.

**Acceptance Scenarios**:

1. **Given** M32 Bridge is installed, **When** the user runs `m32-bridge health`, **Then** the command reports runtime health without requiring a console connection.
2. **Given** configuration has been saved, **When** the user runs `m32-bridge get-info`, `m32-bridge detect-device`, and `m32-bridge doctor-runtime`, **Then** each command returns read-only diagnostics with `osc_writes_sent=0`.
3. **Given** the configured endpoint is missing or unreachable, **When** verification commands run, **Then** they return clear, structured errors and direct the user back to setup rather than guessing or scanning.

---

### User Story 4 - Configure Claude or Other Local MCP Hosts Manually (Priority: P2)

A user receives manual-copy MCP configuration guidance that launches the local stdio server through `m32-bridge mcp-server`, without embedding host or port by default and without automatic changes to Claude Desktop configuration.

**Why this priority**: Claude local MCP is an existing supported path, but installer output must remain safe and user-controlled.

**Independent Test**: Can be tested by viewing generated guidance and confirming it uses the stable launcher, contains no default embedded host/port, and requires manual copy by the user.

**Acceptance Scenarios**:

1. **Given** installation is complete, **When** the user requests MCP guidance, **Then** the guidance provides manual-copy snippets using `m32-bridge mcp-server`.
2. **Given** saved configuration exists, **When** the MCP snippet is shown, **Then** it relies on the bridge reading saved user configuration rather than embedding host or port by default.
3. **Given** a user wants advanced manual overrides, **When** guidance mentions host/port environment overrides, **Then** they are clearly labeled as advanced/manual examples.

---

### User Story 5 - Maintain or Remove the User-Local Install (Priority: P3)

A user can understand how to update, repair, or uninstall the user-local installation without relying on administrator privileges or hidden system changes.

**Why this priority**: Installation is incomplete without a predictable lifecycle story, even before binary packages and signed releases exist.

**Independent Test**: Can be tested by following the documented update, repair, and uninstall guidance and confirming user-local app files, launcher files, and configuration handling are explicit.

**Acceptance Scenarios**:

1. **Given** M32 Bridge is already installed, **When** the installer is run again, **Then** it clearly reports whether it will update, repair, or leave the existing install unchanged.
2. **Given** a user wants to remove the bridge, **When** they follow uninstall guidance, **Then** the user-local app and launcher locations are identified and configuration retention/removal choices are documented.
3. **Given** a future packaging option is mentioned, **When** the user reads the install documentation, **Then** it is clearly labeled as future-only and not available in the current installer scope.

### Edge Cases

- The installer runs in a non-interactive shell where prompts cannot be answered.
- The user does not have administrator privileges and cannot write to system-wide paths.
- The user has no global Python launcher, no `py`, or a conflicting Python installation.
- The required runtime manager is missing, unavailable, blocked by network policy, or already installed in a non-standard location.
- The user shell cannot update PATH automatically, or PATH changes require a new terminal session.
- Windows PowerShell execution policy blocks direct script execution.
- A Windows user starts from CMD rather than PowerShell.
- WSL is detected and must not be confused with native Windows.
- Raspberry Pi OS is detected on ARM hardware, with optional service guidance that remains future-only.
- The console host is missing, invalid, unreachable, or returns an unexpected response address.
- The endpoint is an emulator or Fake M32 and must not be treated as hardware verification.
- The user cancels setup before saving configuration.
- A saved configuration already exists and the installer must avoid overwriting it without confirmation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a POSIX install script entry point named `install.sh` for macOS, Linux, WSL, and Raspberry Pi OS.
- **FR-002**: The system MUST provide a Windows PowerShell install script entry point named `install.ps1`.
- **FR-003**: Installer documentation MUST show future one-line command examples for POSIX and PowerShell installation, including `curl -LsSf <url>/install.sh | sh` and `powershell -ExecutionPolicy Bypass -c "irm <url>/install.ps1 | iex"`, while also documenting the safer download-inspect-run workflow.
- **FR-004**: Installers MUST be user-local by default and MUST NOT require administrator privileges for the default path.
- **FR-005**: The supported OS set MUST include macOS, Linux, WSL, Windows PowerShell, Windows CMD launcher usage, and Raspberry Pi OS.
- **FR-006**: The installation flow MUST NOT assume global Python, global `py`, or an existing Python launcher.
- **FR-007**: The installer MUST verify availability of the required user-managed runtime, install it in user space when allowed, or provide clear manual guidance when installation is not possible.
- **FR-008**: The installed runtime MUST expose a stable launcher command named `m32-bridge`.
- **FR-009**: The stable launcher MUST run from the user installation without requiring a permanently open installer terminal.
- **FR-010**: The default macOS/Linux app location MUST be documented as `~/.m32-bridge/app`, and the default POSIX launcher location MUST be documented as `~/.local/bin/m32-bridge`.
- **FR-011**: The default Windows app location MUST be documented as `%LOCALAPPDATA%\M32Bridge\app`, and the default Windows launcher location MUST be documented as `%LOCALAPPDATA%\M32Bridge\bin\m32-bridge.cmd`.
- **FR-012**: Raspberry Pi OS installation MUST use the user-local default path, with system service behavior documented only as an optional future phase.
- **FR-013**: After installation, the system MUST offer a first-run setup wizard in interactive terminals.
- **FR-014**: The first-run setup wizard MUST display the detected OS and recommended operating mode before asking for console configuration.
- **FR-015**: The first-run setup wizard MUST ask for console host, port default `10023`, label/environment, and intended target type.
- **FR-016**: The setup wizard MUST probe the configured endpoint using `/info` only.
- **FR-017**: Install and setup flows MUST NOT send `/set`, state-changing OSC packets, or real hardware writes.
- **FR-018**: Setup MUST display endpoint classification, including emulator versus hardware-candidate distinctions, without marking emulator evidence as hardware verification.
- **FR-019**: Setup MUST save configuration only after explicit user confirmation.
- **FR-020**: Setup MUST support structured non-interactive operation for automation.
- **FR-021**: If setup or installer first-run behavior is invoked in a non-TTY environment, the system MUST NOT hang and MUST return a clear structured response or actionable help.
- **FR-022**: Post-install guidance MUST include `m32-bridge health`, `m32-bridge setup`, `m32-bridge get-info`, `m32-bridge detect-device`, and `m32-bridge doctor-runtime`.
- **FR-023**: MCP guidance MUST provide manual-copy snippets only and MUST NOT modify Claude Desktop or other host configuration automatically.
- **FR-024**: Default MCP snippets MUST launch `m32-bridge mcp-server`.
- **FR-025**: Default MCP snippets MUST NOT embed host or port; the bridge MUST use saved user configuration by default.
- **FR-026**: Host and port overrides in MCP guidance MUST be clearly labeled as advanced/manual examples.
- **FR-027**: The installer and MCP guidance MUST NOT expose shell execution through MCP tools.
- **FR-028**: The system MUST NOT claim production/live readiness during install, setup, or emulator validation.
- **FR-029**: The system MUST NOT set `hardware_verified=true` based on emulator, Fake M32, or install-time evidence.
- **FR-030**: The installer experience MUST clearly report PowerShell execution-policy issues, missing PATH visibility, missing runtime manager, and unsupported OS cases.
- **FR-031**: The installer experience MUST include WSL-specific detection and messaging distinct from native Windows and native Linux.
- **FR-032**: The installer experience MUST include Raspberry Pi OS recommendations distinct from generic Linux recommendations.
- **FR-033**: The documentation MUST describe update, repair, and uninstall strategy for user-local installation.
- **FR-034**: Packaging options such as macOS `.app`, `.pkg`, `.dmg`, Windows `.exe` and `.msi`, Linux `.deb`, `.rpm`, AppImage, Raspberry Pi service/image, Claude Desktop `.mcpb` or `.dxt`, USB portable kit, code signing, checksums, and release hosting MUST be documented as future phases only.
- **FR-035**: Installers MUST fail with clear, actionable messages rather than partial silent success when required installation steps cannot be completed.

### Key Entities

- **Installation Target**: The user's operating system and shell context, including macOS, Linux, WSL, Windows PowerShell, Windows CMD launcher usage, and Raspberry Pi OS.
- **User-Local Installation**: The application files, launcher files, and PATH guidance installed under user-writable locations.
- **Runtime Manager State**: Whether the required user-managed runtime is present, installable, blocked, or needs manual user action.
- **First-Run Setup Session**: The interactive or structured setup flow that collects endpoint configuration, performs a read-only `/info` probe, displays classification, and saves configuration after confirmation.
- **Saved Runtime Configuration**: The user-local configuration containing host, port, label/environment, and intended target type.
- **MCP Guidance Snippet**: Manual-copy host configuration text that launches the local stdio MCP server through the stable launcher.
- **Lifecycle Guidance**: User-facing update, repair, and uninstall instructions for user-local install artifacts and saved configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On each supported OS family, a new user can reach a working `m32-bridge health` command within 10 minutes using documented install guidance.
- **SC-002**: 100% of default installer flows complete without requiring administrator privileges when user-local paths are writable.
- **SC-003**: 100% of installer and first-run setup flows avoid global `py` assumptions.
- **SC-004**: In interactive terminals, users can complete first-run setup and save configuration in under 5 minutes when they know the console host.
- **SC-005**: In non-interactive contexts, install or setup commands return within 10 seconds with structured guidance rather than waiting for input.
- **SC-006**: 100% of install, setup, detect, and post-install verification flows send zero state-changing OSC writes.
- **SC-007**: Emulator-connected setup results never produce `hardware_verified=true` or production/live readiness claims.
- **SC-008**: PowerShell, POSIX shell, unsupported OS, missing runtime manager, and PATH visibility failures produce clear user-facing errors with next steps.
- **SC-009**: WSL and Raspberry Pi OS are identified distinctly in user-facing recommendations.
- **SC-010**: Manual-copy MCP snippets use `m32-bridge mcp-server` and omit host/port by default in all standard guidance.
- **SC-011**: User-local configuration is saved only after confirmation and is visible to subsequent verification commands.
- **SC-012**: Update, repair, and uninstall guidance identifies the user-local app path, launcher path, and configuration retention choices.
- **SC-013**: Future packaging options are clearly labeled as unavailable future phases in the current installer scope.

## Assumptions

- The existing `m32-bridge` CLI, setup/config commands, device detector, health command, and local stdio MCP server remain the foundation for this feature.
- Install scripts are the first delivery format; binary installers and signed release artifacts are intentionally deferred.
- Default installation is per-user and does not modify system-wide directories unless a future phase explicitly adds that option.
- The installer may guide users through adding the launcher directory to PATH, but must not rely on hidden shell-specific side effects for success reporting.
- The first-run setup wizard reuses the existing safe setup semantics: explicit host entry, port default `10023`, no scanning by default, `/info` read-only probe, and saved user-local configuration.
- Hardware verification remains outside this feature and requires later physical-console acceptance evidence.
- Claude and other MCP host guidance remains manual-copy only; automatic host configuration edits are out of scope.

## Out of Scope

- Actual `.exe`, `.dmg`, `.pkg`, `.msi`, `.deb`, `.rpm`, AppImage, or signed binary generation.
- Code signing, checksum publication, GitHub Releases automation, or official release branding.
- Auto-update services or background updater daemons.
- Official branded desktop app experience.
- WebUI, database, backend service, or microservice additions.
- Remote/cloud MCP, ChatGPT tunnel implementation, or public network exposure.
- Real console write validation or real hardware write tests.
- Production/live readiness claims or hardware verification claims.
