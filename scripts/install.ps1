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
# First-run TTY wizard is future work: DXBMARK style in TTY, non-TTY plain and JSON fallback.
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

Options:
  -DryRun
  -Json
  -Platform windows_powershell|windows_cmd
"@
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
if (-not (Test-Path (Join-Path $RepoRoot "src/m32_bridge")) -or -not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
    $SourceKind = "github_release_or_archive"
    $RepoRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("m32-bridge-bootstrap-" + $PID)
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

if (Get-Command uv -ErrorAction SilentlyContinue) {
    if ($SourceKind -ne "local_checkout") {
        Initialize-RemoteSource
        if ([string]::IsNullOrEmpty($existingPythonPath)) {
            $env:PYTHONPATH = Join-Path $RepoRoot "src"
        } else {
            $env:PYTHONPATH = "$(Join-Path $RepoRoot "src");$existingPythonPath"
        }
    }
    if ([string]::IsNullOrEmpty($env:UV_CACHE_DIR)) {
        $env:UV_CACHE_DIR = Join-Path $env:TEMP "uv-cache"
    }
    & uv run python @runtimeArgs
} else {
    $payload = Get-MissingUvPayload
    if ($Json) {
        $payload | ConvertTo-Json -Depth 4
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
