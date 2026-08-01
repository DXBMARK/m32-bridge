Param(
    [switch]$DryRun,
    [switch]$Json,
    [ValidateSet("windows_powershell", "windows_cmd")]
    [string]$Platform = "windows_powershell",
    [string]$TargetVersion = "0.1.0"
)

# M32 Bridge Windows user-local installer surface.
# Official path: PowerShell irm / Invoke-RestMethod, then inspect and run install.ps1.
# CMD support is through PowerShell invocation guidance and the generated m32-bridge.cmd launcher.
# GitHub raw bootstrap: when repo files are not beside this script, download a
# source archive into temp staging and run the same runtime there.
# Default install is user-local under $env:LOCALAPPDATA; no Admin default and no global launcher assumption.
# This readable text script opens no ports, starts no background service, and installs no binary package.
# Structured output includes admin_required=false, hardware_verified=false,
# production_live_ready=false, and osc_writes_sent=0.
# TTY installer wizard uses DXBMARK style; non-TTY stays plain and JSON stays machine-readable.
# Post-install checks: m32-bridge health, m32-bridge setup, m32-bridge get-info,
# m32-bridge detect-device, m32-bridge doctor-runtime.
# MCP guidance is manual-copy only: use m32-bridge mcp-server as a local stdio
# command; this script does not write Claude, ChatGPT, Gemini, Antigravity,
# Codex, VS Code, or Cursor configuration.
# Lifecycle guidance: update, repair, and uninstall stay user-local; retain saved config
# by default and remove config/audit files only after explicit confirmation.
# Idempotency states: fresh_install, existing_install, repair, update,
# already_current, partial_failure, failed. Partial failure includes recovery
# guidance and never claims success quietly.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:RuntimeBootstrapSucceeded = $false
$script:UvBin = $null
$env:M32_POWERSHELL_VERSION = $PSVersionTable.PSVersion.ToString()
# Keep these values in parity with src/m32_bridge/installer/runtime_manager.py.
$ApprovedPythonMinor = "3.13"
$ProjectPythonRange = ">=3.11,<3.14"
$UvInstallUrlWindows = "https://astral.sh/uv/install.ps1"

function Show-M32Help {
    @"
M32 Bridge Windows installer

Targets:
  PowerShell installer: install.ps1
  CMD-compatible launcher after install: %LOCALAPPDATA%\M32Bridge\bin\m32-bridge.cmd
  Check commands:
    m32-bridge health
    m32-bridge setup
    m32-bridge get-info
    m32-bridge detect-device
    m32-bridge doctor-runtime
    m32-bridge mcp-server
  Managed runtime:
    CPython 3.13.x installed and launched only through uv
    Project range >=3.11,<3.14; system Python unchanged
  Lifecycle guidance:
    update, repair, uninstall
    retain saved config by default

Recommended trust workflow:
  1. Download scripts/install.ps1 using irm / Invoke-RestMethod.
  2. Inspect the script.
  3. Run it locally from PowerShell.
  4. Copy MCP snippets manually only; this script writes no IDE or MCP client config.
  5. For lifecycle actions, review user-local app, launcher, and config paths first.

Execution policy guidance:
  PowerShell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -DryRun
  This override is process-scoped for that PowerShell process only.
  This script does not call Set-ExecutionPolicy and makes no permanent policy change.

Options:
  -Help
  -DryRun
  -Json
  -Platform windows_powershell|windows_cmd
  -TargetVersion <version>

Bootstrap commands:
  /status /help /contact /clear /exit

After installation:
  /health /setup /get-info /verify-device /doctor-runtime /mcp-config

Contact:
  Website                   : https://www.dxbmark.com
  Email                     : support@dxbmark.com
  Phone / WhatsApp          : +971505121583
"@
}

function Test-InteractiveTty {
    return -not $Json -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected
}

function Show-InstallerHelp {
    @"
/help - show installer sections and safe next commands
/contact - show DXBMARK support contact
/status - show installer/runtime/source/safety state
/clear - redraw the installer screen
/exit - exit the installer TTY flow
Dry-run prints the plan without writing app or launcher files.
JSON mode is for CI and never includes banners or ANSI colours.
Missing uv requires explicit user-local setup; no global py is required.
Managed Python is CPython 3.13.x through uv; system Python stays unchanged.
Website                   : https://www.dxbmark.com
Email                     : support@dxbmark.com
Phone / WhatsApp          : +971505121583
"@
}

function Show-InstallerContact {
    @"
DXBMARK Support
Website                   : https://www.dxbmark.com
Email                     : support@dxbmark.com
Phone / WhatsApp          : +971505121583
"@
}

function Write-InstallerHeading([string]$Text) {
    if (Test-InteractiveTty) {
        Write-Host $Text -ForegroundColor DarkYellow
    } else {
        Write-Output $Text
    }
}

function Get-TerminalColorMode {
    if (-not (Test-InteractiveTty) -or $env:TERM -eq "dumb" -or -not [string]::IsNullOrEmpty($env:NO_COLOR)) {
        return "none"
    }
    if ($env:COLORTERM -in @("truecolor", "24bit")) {
        return "truecolor"
    }
    return "basic"
}

function Write-CanvasLine([string]$Text) {
    if (-not (Test-InteractiveTty)) {
        Write-Output $Text
        return
    }
    $width = [Console]::WindowWidth - 1
    if ($width -lt 20) { $width = 20 }
    $mode = Get-TerminalColorMode
    if ($mode -eq "truecolor") {
        $line = if ($Text.Length -gt $width) { $Text.Substring(0, $width) } else { $Text.PadRight($width) }
        Write-Output "`e[48;2;36;57;71m$line`e[0m"
    } elseif ($mode -eq "basic") {
        $line = if ($Text.Length -gt $width) { $Text.Substring(0, $width) } else { $Text }
        Write-Output "`e[37m$line`e[0m"
    } else {
        Write-Output $Text
    }
}

function Show-MissingUvWizard($Payload) {
    $mode = if ($DryRun) { "dry-run" } else { "status" }
    if ((Get-TerminalColorMode) -eq "truecolor") {
        Write-Output "`e[2J`e[H`e[38;2;249;126;26m"
    } elseif ((Get-TerminalColorMode) -eq "basic") {
        Write-Output "`e[2J`e[H`e[33m"
    }
    (@"
X32-BRIDGE MCP INSTALLER
Powered by DXBMARK LLC
#  ______  ______  __  __    _    ____  _  __
# |  _ \ \/ / __ )|  \/  |  / \  |  _ \| |/ / LLC
# | | | \  /|  _ \| |\/| | / _ \ | |_) | ' /
# | |_| /  \| |_) | |  | |/ ___ \|  _ <| . \
# |____/_/\_\____/|_|  |_/_/   \_\_| \_\_|\_\ dxbmark.com
User-local installer. No admin, no service, no binary package.
Type / for interactive menu | Type /help for list

System Check
  OS: $($Payload.platform)
  architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)
  shell: powershell
Download capability
  Primary tool: PowerShell Invoke-WebRequest/Invoke-RestMethod available
  wget fallback: optional, not installed
  Manual fallback: available
  uv status: missing
  managed Python state: not_installed
  application installed state: not_installed
  launcher state: not_installed
  Python strategy: CPython 3.13.x managed by uv; system Python unchanged; no global py required
  Runtime config: not inspected until application runtime is ready

Source Check
  install_source: $($Payload.install_source)
  source_url: $($Payload.source_url)
  source_ref: $($Payload.source_ref)
  Source configuration: configured: github source archive
  Reachability: not_checked

Install Plan
  mode: $mode
  status: $($Payload.status)
  install_root: $($Payload.install_root)
  app_path: $($Payload.app_path)
  launcher_path: $($Payload.launcher_path)
  user_local=true
  admin_required=false

Safety
  osc_writes_sent=0
  hardware_verified=false
  production_live_ready=false
  no /set
  no OSC writes
  no IDE or MCP client config writes
  network_scan=not_run
  console_probe=not_run

Required Actions
  INSTALL_UV_USER_LOCAL: Install uv in user space
    reason: M32 Bridge uses uv to manage Python runtime dependencies without system Python launcher assumptions.
    command: Invoke-RestMethod downloads the official installer to a temporary file; run only after exact INSTALL confirmation
    confirmation_required=true

After installation
  These commands become available after the managed application runtime is installed.
  /health          Check runtime and installation readiness
  /setup           Configure a known console endpoint
  /get-info        Read information from the configured endpoint
  /verify-device   Verify the configured endpoint; no network scan
  /doctor-runtime  Diagnose local runtime issues

Commands
  /help
  /contact
  /status
  /clear
  /exit
"@) -split "`n" | ForEach-Object { Write-CanvasLine $_ }
}

function Read-MissingUvTtyCommand {
    if (-not (Test-InteractiveTty) -or $DryRun) {
        return
    }
    @"
Required Runtime Setup

uv is required to install and run M32 Bridge.
It will be installed for the current user only.
No administrator access is required.
System Python will not be changed.

Options:
  [1] Install uv user-locally
  [2] Show manual instructions
  [3] Exit
"@
    $answer = Read-Host "Select [1-3]"
    switch ($answer.ToLowerInvariant()) {
        "/help" { Show-InstallerHelp }
        "help" { Show-InstallerHelp }
        "/contact" { Show-InstallerContact }
        "contact" { Show-InstallerContact }
        "/status" {
            "installer state: RUNTIME_SETUP_REQUIRED"
            "OS: $($payload.platform)"
            "architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
            "shell: powershell"
            "uv: missing"
            "managed Python: not_installed"
            "application: not_installed"
            "launcher: not_installed"
            "install source: $SourceKind"
            "Source configuration: configured: github source archive"
            "Reachability: not_checked"
            "Runtime config: not inspected until application runtime is ready"
            "safety: admin_required=false, system_python_unchanged=true, network_scan=not_run, console_probe=not_run, osc_writes_sent=0"
        }
        "status" {
            "installer state: RUNTIME_SETUP_REQUIRED"
            "OS: $($payload.platform)"
            "architecture: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
            "shell: powershell"
            "uv: missing"
            "managed Python: not_installed"
            "application: not_installed"
            "launcher: not_installed"
            "install source: $SourceKind"
            "Source configuration: configured: github source archive"
            "Reachability: not_checked"
            "Runtime config: not inspected until application runtime is ready"
            "safety: admin_required=false, system_python_unchanged=true, network_scan=not_run, console_probe=not_run, osc_writes_sent=0"
        }
        "/clear" {
            Clear-Host
            Show-MissingUvWizard $payload
        }
        "clear" {
            Clear-Host
            Show-MissingUvWizard $payload
        }
        "/exit" {
            "status=RUNTIME_SETUP_REQUIRED"
            "No dependency action was taken."
        }
        "1" { Install-ApprovedRuntime }
        "2" { "Download $UvInstallUrlWindows, inspect it, install uv for your user, then run: uv python install $ApprovedPythonMinor" }
        "3" {
            "status=RUNTIME_SETUP_REQUIRED"
            "No dependency action was taken."
        }
        default {
            "status=RUNTIME_SETUP_REQUIRED"
            "No dependency action was taken."
        }
    }
}

function Install-ApprovedRuntime {
    @"
Source
  Official installer URL: https://astral.sh/uv/install.ps1

Target
  User-local uv installation paths

Managed Python
  CPython 3.13.x
  Installed and used only through uv

Changes
  Downloads uv installer to a temporary file
  Installs uv for the current user
  Installs approved managed Python if required
  May provide PATH guidance
  Does not use administrator elevation
  Does not change system Python
  Does not install wget or curl

Type INSTALL to continue.
"@
    $confirmation = Read-Host
    if ($confirmation -cne "INSTALL") {
        "Exact INSTALL confirmation was not provided. No download or install was performed."
        return
    }
    $temporaryBase = [System.IO.Path]::GetTempFileName()
    $temporaryPath = "$temporaryBase.ps1"
    Move-Item -LiteralPath $temporaryBase -Destination $temporaryPath -Force
    try {
        "URL: $UvInstallUrlWindows"
        "Temporary path: $temporaryPath"
        Invoke-RestMethod -Uri $UvInstallUrlWindows -OutFile $temporaryPath
        if (-not (Test-Path $temporaryPath) -or (Get-Item $temporaryPath).Length -eq 0) {
            throw "Downloaded uv installer is empty."
        }
        & $temporaryPath
        if ($LASTEXITCODE -ne 0) {
            throw "uv installer execution failed with exit code $LASTEXITCODE."
        }
    } catch {
        "Runtime bootstrap failed: $($_.Exception.GetType().Name): $($_.Exception.Message)"
        return
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $temporaryBase -Force -ErrorAction SilentlyContinue
    }
    $uvPath = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (-not (Test-Path $uvPath)) {
        "uv installation completed but the expected user-local executable is unavailable: $uvPath"
        return
    }
    $script:UvBin = $uvPath
    $env:PATH = "$(Split-Path -Parent $uvPath);$env:PATH"
    & $uvPath --version
    $env:UV_MANAGED_PYTHON = "1"
    & $uvPath python install $ApprovedPythonMinor
    if ($LASTEXITCODE -ne 0) {
        "Managed CPython 3.13 installation failed."
        return
    }
    $managedPython = (& $uvPath python find --managed-python $ApprovedPythonMinor 2>$null | Select-Object -Last 1)
    if ([string]::IsNullOrWhiteSpace($managedPython) -or -not (Test-Path $managedPython)) {
        "Managed CPython 3.13 could not be rediscovered."
        return
    }
    & $managedPython --version
    "Managed Python path: $managedPython"
    $script:RuntimeBootstrapSucceeded = $true
}

if ($args -contains "-Help" -or $args -contains "--help") {
    Show-M32Help
    exit 0
}

if ($env:M32_INSTALL_DRY_RUN -eq "1") {
    $DryRun = $true
}

$ScriptPath = $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ScriptPath)) {
    $RepoRoot = (Get-Location).Path
} else {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptPath)
}

$SourceRef = if ([string]::IsNullOrEmpty($env:M32_INSTALL_SOURCE_REF)) { "main" } else { $env:M32_INSTALL_SOURCE_REF }
$DefaultSourceUrl = "https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.zip"
$SourceUrl = if ([string]::IsNullOrEmpty($env:M32_INSTALL_SOURCE_URL)) { $DefaultSourceUrl } else { $env:M32_INSTALL_SOURCE_URL }
$SourceKind = "local_checkout"
$BootstrapSourceRoot = $null
if (-not (Test-Path (Join-Path $RepoRoot "src/m32_bridge")) -or -not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    $SourceKind = "github_release_or_archive"
    $RepoRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("m32-bridge-bootstrap-" + $PID)
    $BootstrapSourceRoot = $RepoRoot
}

function New-UvRequiredAction {
    @(
        [ordered]@{
            action_id = "INSTALL_UV_USER_LOCAL"
            title = "Install uv in user space"
            reason = "M32 Bridge uses uv to manage Python runtime dependencies without system Python launcher assumptions."
            command_preview = "irm https://astral.sh/uv/install.ps1 -OutFile install-uv.ps1; inspect install-uv.ps1; run only after confirmation"
            requires_confirmation = $true
            risk_level = "user_local"
            target_paths = @(Join-Path $env:LOCALAPPDATA "M32Bridge\runtime\uv")
            official_source_url = "https://docs.astral.sh/uv/getting-started/installation/"
            user_can_skip = $false
        }
    )
}

function Get-MissingUvPayload {
    $appPath = Join-Path $env:LOCALAPPDATA "M32Bridge\app"
    $launcherPath = Join-Path $env:LOCALAPPDATA "M32Bridge\bin\m32-bridge.cmd"
    [ordered]@{
        ok = $false
        status = "RUNTIME_SETUP_REQUIRED"
        platform = $Platform
        app_path = $appPath
        launcher_path = $launcherPath
        install_root = (Join-Path $env:LOCALAPPDATA "M32Bridge")
        requires_admin = $false
        admin_required = $false
        user_local = $true
        global_py_required = $false
        global_python_required = $false
        uv_required = $true
        uv_detected = $false
        python_required = $true
        python_managed_by_uv = $true
        approved_python_minor = $ApprovedPythonMinor
        project_python_range = $ProjectPythonRange
        system_python_modified = $false
        global_python_installed = $false
        default_python_aliases_installed = $false
        installer_can_continue = $false
        confirmation_required = $true
        uv_status = "manual_action_required"
        required_actions = New-UvRequiredAction
        osc_writes_sent = 0
        hardware_verified = $false
        production_live_ready = $false
        version = $TargetVersion
        target_version = $TargetVersion
        install_source = $SourceKind
        source_url = $SourceUrl
        source_ref = $SourceRef
        path_updated = $false
        recommendations = @(
            "Install uv in user space, then rerun this installer.",
            "No system-wide interpreter or ``py`` launcher is required.",
            "Official Windows bootstrap download guidance uses PowerShell irm / Invoke-RestMethod."
        )
    }
}

function Initialize-RemoteSource {
    New-Item -ItemType Directory -Path $RepoRoot -Force | Out-Null
    $archive = Join-Path $RepoRoot "source.zip"
    Invoke-RestMethod -Uri $SourceUrl -OutFile $archive
    Expand-Archive -Path $archive -DestinationPath $RepoRoot -Force
    $project = Get-ChildItem -Path $RepoRoot -Directory | Where-Object {
        (Test-Path (Join-Path $_.FullName "src/m32_bridge")) -and
        (Test-Path (Join-Path $_.FullName "pyproject.toml"))
    } | Select-Object -First 1
    if ($null -eq $project) {
        throw "Downloaded source archive did not contain expected m32_bridge project files."
    }
    $script:RepoRoot = $project.FullName
}

$existingPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrEmpty($existingPythonPath)) {
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
} else {
    $env:PYTHONPATH = "$(Join-Path $RepoRoot "src");$existingPythonPath"
}

$runtimeArgs = @(
    "-m", "m32_bridge.installer.script_runtime",
    "--surface", "windows",
    "--platform", $Platform,
    "--target-version", $TargetVersion,
    "--install-source", $SourceKind,
    "--source-url", $SourceUrl,
    "--source-ref", $SourceRef
)

if ($DryRun) {
    $runtimeArgs += "--dry-run"
}
if ($Json) {
    $runtimeArgs += "--json"
}
if (Test-InteractiveTty) {
    $runtimeArgs += "--tty"
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -ne $uvCommand) {
    $script:UvBin = if ($uvCommand.PSObject.Properties.Name -contains "Source") { $uvCommand.Source } else { $uvCommand.FullName }
}
if ($null -eq $uvCommand -and -not $Json -and -not $DryRun -and (Test-InteractiveTty)) {
    $payload = Get-MissingUvPayload
    Show-MissingUvWizard $payload
    Read-MissingUvTtyCommand
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($null -eq $uvCommand -and $script:RuntimeBootstrapSucceeded) {
        if (-not [string]::IsNullOrEmpty($script:UvBin) -and (Test-Path $script:UvBin)) {
            $uvCommand = Get-Item $script:UvBin
        }
    }
}

if ($null -ne $uvCommand) {
    try {
    if ($SourceKind -ne "local_checkout") {
        Initialize-RemoteSource
        if ([string]::IsNullOrEmpty($existingPythonPath)) {
            $env:PYTHONPATH = Join-Path $RepoRoot "src"
        } else {
            $env:PYTHONPATH = "$(Join-Path $RepoRoot "src");$existingPythonPath"
        }
    }
    if (-not (Test-Path (Join-Path $RepoRoot "uv.lock"))) {
        throw "uv.lock is required for reproducible frozen runtime execution. Refusing unfrozen install."
    }
    if ([string]::IsNullOrEmpty($env:UV_CACHE_DIR)) {
        $env:UV_CACHE_DIR = Join-Path $env:TEMP "uv-cache"
    }
    $uvPath = if ($uvCommand.PSObject.Properties.Name -contains "Source") { $uvCommand.Source } else { $uvCommand.FullName }
    $script:UvBin = $uvPath
    $env:M32_INSTALL_UV_BIN = $script:UvBin
    $env:UV_MANAGED_PYTHON = "1"
    if (-not $DryRun) {
        $runtimeArgs += "--bootstrap-apply"
        $runtimeArgs += "--uv-bin"
        $runtimeArgs += $script:UvBin
    }
    & $uvPath run --managed-python --python $ApprovedPythonMinor --no-build --no-project python @runtimeArgs
    } finally {
        if (-not [string]::IsNullOrEmpty($BootstrapSourceRoot)) {
            $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
            $resolvedBootstrapRoot = [System.IO.Path]::GetFullPath($BootstrapSourceRoot)
            if ($resolvedBootstrapRoot.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
                (Split-Path -Leaf $resolvedBootstrapRoot) -like "m32-bridge-bootstrap-*") {
                Remove-Item -LiteralPath $resolvedBootstrapRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
} else {
    $payload = Get-MissingUvPayload
    if ($Json) {
        $payload | ConvertTo-Json -Depth 4
    } elseif ((Test-InteractiveTty) -and $DryRun) {
        Show-MissingUvWizard $payload
    } else {
        "M32 Bridge installer status"
        "mode: $(if ($DryRun) { "dry-run" } else { "status" })"
        "status: $($payload.status)"
        "install_root: $($payload.install_root)"
        "app_path: $($payload.app_path)"
        "launcher_path: $($payload.launcher_path)"
        "install_source: $($payload.install_source)"
        "source_url: $($payload.source_url)"
        "user_local: true"
        "admin_required=false"
        "global_py_required=false"
        "global_python_required=false"
        "approved_python_minor=$ApprovedPythonMinor"
        "project_python_range=$ProjectPythonRange"
        "system_python_modified=false"
        "installer_can_continue=false"
        "uv_status=manual_action_required"
        "hardware_verified=false"
        "production_live_ready=false"
        "osc_writes_sent=0"
        "Install uv in user space, then rerun this installer. No system-wide interpreter or ``py`` launcher is required."
        "Post-install checks: m32-bridge health, m32-bridge setup, m32-bridge get-info, m32-bridge detect-device, m32-bridge doctor-runtime."
    }
    exit 1
}
