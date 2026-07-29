# Research: Cross-Platform Installers and First-Run Setup

## Decision: Script installers are the first delivery format

**Rationale**: The spec prioritizes install scripts and explicitly defers binary installers. Scripts allow the project to validate user-local paths, launcher creation, runtime manager handling, first-run setup, and post-install guidance before signing, packaging, and release infrastructure exist.

**Alternatives considered**:

- Binary installers first: rejected because `.exe`, `.msi`, `.app`, `.pkg`, `.dmg`, `.deb`, `.rpm`, and AppImage generation are out of scope for this feature.
- Documentation-only install: rejected because the feature requires installer entry points named `install.sh` and `install.ps1`.

## Decision: Default install is user-local and no-admin

**Rationale**: The default flow must work without administrator privileges and must not let AI or installer logic assume elevated OS authority. User-local paths also make update, repair, and uninstall easier to explain and validate.

**Alternatives considered**:

- System-wide install: rejected as a default because it requires admin privileges and expands blast radius.
- Per-project install only: rejected because the feature requires a stable user launcher that feels natural after installation.

## Decision: POSIX install path covers macOS, Linux, WSL, and Raspberry Pi OS

**Rationale**: A single POSIX installer surface can cover Unix-like shells while still producing OS-specific recommendations and path handling. WSL and Raspberry Pi OS must be detected distinctly for user-facing guidance.

**Alternatives considered**:

- Separate shell scripts per POSIX OS: deferred unless implementation complexity later justifies it.
- Treat WSL as generic Linux: rejected because the spec requires distinct WSL messaging.

## Decision: Windows uses PowerShell install plus CMD-compatible launcher

**Rationale**: PowerShell is the most practical Windows installation shell, while a `.cmd` launcher makes daily use natural from both PowerShell and CMD.

**Alternatives considered**:

- CMD-only installer: rejected because download, error handling, and user-local runtime installation are less ergonomic.
- Windows binary installer first: rejected as future-only packaging scope.

## Decision: `uv` is the managed runtime strategy

**Rationale**: The prior feature established that `m32-bridge` should not rely on global `py`. Verifying `uv`, installing it in user space when allowed, or giving manual guidance when blocked keeps runtime bootstrap explicit and repeatable.

**Alternatives considered**:

- Global Python or `py`: rejected because the spec requires no global Python or `py` assumption.
- Bundled Python runtime: deferred to future binary/package phases.
- System package manager dependency: rejected as default because it often requires admin privileges or distro-specific instructions.

## Decision: Installers must be idempotent and report lifecycle state

**Rationale**: Re-running an installer is common. The installer must clearly distinguish fresh install, existing install, repair, update, already current, and partial failure recovery to avoid silent partial success.

**Alternatives considered**:

- Always overwrite install directory: rejected because it risks destroying local state and hides recovery cases.
- Always fail if installed: rejected because it prevents repair/update flows.

## Decision: First-run setup is integrated but remains the existing safe setup model

**Rationale**: Installation should guide the user to configure the console, but setup must remain no-write and must not scan or guess missing hosts. The wizard uses `/info` only, asks for confirmation before saving, and supports non-interactive structured behavior.

**Alternatives considered**:

- Auto-detect host by scanning: rejected because the system must not guess or scan by default.
- Save config before probe: rejected because users should confirm endpoint evidence before persistence.
- Send capability writes to validate hardware: rejected because real hardware writes are out of scope and unsafe for install.

## Decision: MCP guidance is manual-copy only

**Rationale**: The existing local MCP path should be easy to configure, but automatic edits to Claude Desktop or other host config are out of scope. Snippets use `m32-bridge mcp-server` and rely on saved user config by default.

**Alternatives considered**:

- Automatic Claude Desktop config modification: rejected by spec.
- Embed host/port in default snippets: rejected because saved user config should be the default and host/port overrides should be advanced/manual examples.

## Decision: Packaging strategy remains future-only documentation

**Rationale**: Users should understand the roadmap, but this feature must not start binary packaging, signing, release hosting, Raspberry Pi images/services, Claude package formats, or USB portable kit work.

**Alternatives considered**:

- Start `.mcpb`/`.dxt` package design now: rejected as future-only.
- Add service or app packaging in parallel: rejected because it would expand scope beyond install scripts.

## Decision: Safety claims remain conservative

**Rationale**: Installer success, emulator connectivity, Fake M32 evidence, and `/info` connectivity are not real hardware verification and do not imply production/live readiness.

**Alternatives considered**:

- Treat emulator as readiness proof: rejected by constitution and spec.
- Mark production readiness after setup: rejected because hardware verification remains out of scope.
