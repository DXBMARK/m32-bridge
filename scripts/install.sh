#!/bin/sh
set -eu

# M32 Bridge POSIX user-local installer surface.
# Official targets: macOS, Linux, WSL, Raspberry Pi OS.
# Safer path: download, inspect, then run locally.
# Download options: curl first when available, wget fallback, or manual download fallback.
# GitHub raw bootstrap: when this script is run without repo files beside it,
# it downloads a source archive into temp staging and runs the same runtime there.
# This is a readable text script. It creates only user-local files unless --dry-run is used.
# No binary installers, ports, or background daemon.
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

DRY_RUN=0
JSON_OUTPUT=0
PLATFORM=""
TARGET_VERSION="0.1.0"
DEFAULT_SOURCE_REF="main"
# Keep these values in parity with src/m32_bridge/installer/runtime_manager.py.
APPROVED_PYTHON_MINOR="3.13"
PROJECT_PYTHON_RANGE=">=3.11,<3.14"
UV_INSTALL_URL_POSIX="https://astral.sh/uv/install.sh"
DEFAULT_SOURCE_URL="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz"
SOURCE_URL="${M32_INSTALL_SOURCE_URL:-${DEFAULT_SOURCE_URL}}"
SOURCE_REF="${M32_INSTALL_SOURCE_REF:-}"
USER_CACHE_HOME="${XDG_CACHE_HOME:-${HOME}/.cache}"
DEFAULT_UV_CACHE_DIR="${USER_CACHE_HOME}/uv"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run|--dry_run)
      DRY_RUN=1
      ;;
    --json)
      JSON_OUTPUT=1
      ;;
    --platform)
      shift
      PLATFORM="${1:-}"
      ;;
    --target-version)
      shift
      TARGET_VERSION="${1:-0.1.0}"
      ;;
    --help|-h)
      cat <<'HELP'
M32 Bridge POSIX installer

Targets: macOS, Linux, WSL, Raspberry Pi OS.
Default install is user-local:
  app:      $HOME/.m32-bridge/app
  launcher: $HOME/.local/bin/m32-bridge
  checks:   m32-bridge health
            m32-bridge setup
            m32-bridge get-info
            m32-bridge detect-device
            m32-bridge doctor-runtime
  managed runtime:
            CPython 3.13.x installed and launched only through uv
            project range >=3.11,<3.14; system Python unchanged
  MCP:      m32-bridge mcp-server
  Lifecycle guidance:
            update, repair, uninstall
            retain saved config by default

Recommended trust workflow:
  1. Download scripts/install.sh with curl, wget, or manual download.
  2. Inspect the script.
  3. Run it locally.
  4. Copy MCP snippets manually only; this script writes no IDE or MCP client config.
  5. For lifecycle actions, review user-local app, launcher, and config paths first.

Options:
  -h, --help        Show this help.
  --dry-run          Print intended status/actions only.
  --json             Emit structured JSON.
  --platform VALUE   macos, linux, wsl, raspberry_pi_os.
  --target-version VERSION

Bootstrap commands:
  /status /help /contact /clear /exit

After installation:
  /health /setup /get-info /verify-device /doctor-runtime /mcp-config

Status colours:
  Green available/success/safe; Yellow action; Red blocker; Slate information.

Contact:
  Website                   : https://www.dxbmark.com
  Email                     : support@dxbmark.com
  Phone / WhatsApp          : +971505121583
HELP
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

if [ "${M32_INSTALL_DRY_RUN:-0}" = "1" ]; then
  DRY_RUN=1
fi
if [ -z "${SOURCE_REF}" ]; then
  SOURCE_REF="${DEFAULT_SOURCE_REF}"
fi

detect_platform() {
  if [ -n "${PLATFORM}" ]; then
    printf '%s\n' "${PLATFORM}"
    return
  fi
  if [ -n "${WSL_DISTRO_NAME:-}" ] || { [ -r /proc/version ] && grep -qi microsoft /proc/version; }; then
    printf '%s\n' "wsl"
    return
  fi
  uname_s="$(uname -s 2>/dev/null || printf unknown)"
  case "${uname_s}" in
    Darwin) printf '%s\n' "macos" ;;
    Linux)
      if [ -r /etc/os-release ] && grep -Eqi 'raspbian|raspberry pi os' /etc/os-release; then
        printf '%s\n' "raspberry_pi_os"
      else
        printf '%s\n' "linux"
      fi
      ;;
    *) printf '%s\n' "linux" ;;
  esac
}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P || pwd)
REPO_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." 2>/dev/null && pwd -P || pwd)
PLATFORM_VALUE="$(detect_platform)"

if [ -d "${REPO_ROOT}/src/m32_bridge" ] && [ -f "${REPO_ROOT}/pyproject.toml" ]; then
  INSTALL_SOURCE="local_checkout"
else
  INSTALL_SOURCE="github_release_or_archive"
  REPO_ROOT="${TMPDIR:-/tmp}/m32-bridge-bootstrap-${$}"
fi

required_actions_json() {
  cat <<JSON
[
  {
    "action_id": "INSTALL_UV_USER_LOCAL",
    "title": "Install uv in user space",
    "reason": "M32 Bridge uses uv to manage Python runtime dependencies without system Python launcher assumptions.",
    "command_preview": "curl -LsSf https://astral.sh/uv/install.sh -o install-uv.sh; inspect install-uv.sh; run only after confirmation",
    "requires_confirmation": true,
    "risk_level": "user_local",
    "target_paths": ["${HOME}/.local/bin/uv"],
    "official_source_url": "https://docs.astral.sh/uv/getting-started/installation/",
    "user_can_skip": false
  }
]
JSON
}

is_tty() {
  [ -t 0 ] && [ -t 1 ]
}

ansi_or_plain() {
  case "$(terminal_color_mode)" in
    truecolor) printf '\033[38;2;249;126;26m%s\033[0m\n' "$1" ;;
    basic) printf '\033[33m%s\033[0m\n' "$1" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

terminal_color_mode() {
  if ! is_tty || [ "${TERM:-dumb}" = "dumb" ] || [ "${NO_COLOR:-}" != "" ]; then
    printf '%s\n' none
    return
  fi
  case "${COLORTERM:-}" in
    truecolor|24bit) printf '%s\n' truecolor ;;
    *) printf '%s\n' basic ;;
  esac
}

tty_width() {
  cols="$(tput cols 2>/dev/null || printf 80)"
  case "${cols}" in
    ''|*[!0-9]*) printf '%s\n' 80 ;;
    *) printf '%s\n' "${cols}" ;;
  esac
}

paint_tty_lines() {
  if ! is_tty; then
    cat
    return
  fi
  width=$(( $(tty_width) - 1 ))
  if [ "${width}" -lt 20 ]; then
    width=20
  fi
  color_mode="$(terminal_color_mode)"
  while IFS= read -r line; do
    visible_len=${#line}
    if [ "${visible_len}" -gt "${width}" ]; then
      line="$(printf '%s' "${line}" | cut -c 1-"${width}")"
      visible_len=${#line}
    fi
    pad=$((width - visible_len))
    if [ "${color_mode}" = "truecolor" ]; then
      printf '\033[48;2;36;57;71m%s' "${line}"
      if [ "${pad}" -gt 0 ]; then
        printf '%*s' "${pad}" ''
      fi
      printf '\033[0m\n'
    elif [ "${color_mode}" = "basic" ]; then
      printf '\033[37m%s\033[0m\n' "${line}"
    else
      printf '%s\n' "${line}"
    fi
  done
}

installer_help() {
  cat <<'HELP'
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
HELP
}

installer_contact() {
  cat <<'CONTACT'
DXBMARK Support
Website                   : https://www.dxbmark.com
Email                     : support@dxbmark.com
Phone / WhatsApp          : +971505121583
CONTACT
}

print_missing_uv_tty() {
  mode="status"
  if [ "${DRY_RUN}" = "1" ]; then
    mode="dry-run"
  fi
  case "$(terminal_color_mode)" in
    truecolor) printf '\033[2J\033[H\033[38;2;249;126;26m' ;;
    basic) printf '\033[2J\033[H\033[33m' ;;
  esac
  {
  cat <<TEXT
X32-BRIDGE MCP INSTALLER
Powered by DXBMARK LLC
#  ______  ______  __  __    _    ____  _  __
# |  _ \\ \\/ / __ )|  \\/  |  / \\  |  _ \\| |/ / LLC
# | | | \\  /|  _ \\| |\\/| | / _ \\ | |_) | ' /
# | |_| /  \\| |_) | |  | |/ ___ \\|  _ <| . \\
# |____/_/\\_\\____/|_|  |_/_/   \\_\\_| \\_\\_|\\_\\ dxbmark.com
User-local installer. No admin, no service, no binary package.
Type / for interactive menu | Type /help for list

System Check
  OS: ${PLATFORM_VALUE}
  architecture: $(uname -m 2>/dev/null || printf unknown)
  shell: ${SHELL:-unknown}
Download capability
  Primary tool: $(if command -v curl >/dev/null 2>&1; then printf 'curl available'; elif command -v wget >/dev/null 2>&1; then printf 'wget available'; else printf 'not available'; fi)
  wget fallback: $(if command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then printf 'optional, not installed'; elif command -v wget >/dev/null 2>&1; then printf available; else printf 'optional, not installed'; fi)
  Manual fallback: available
  uv status: missing
  managed Python state: not_installed
  application installed state: not_installed
  launcher state: not_installed
  Python strategy: CPython 3.13.x managed by uv; system Python unchanged; no global py required
  Runtime config: not inspected until application runtime is ready

Source Check
  install_source: ${INSTALL_SOURCE}
  source_url: ${SOURCE_URL}
  source_ref: ${SOURCE_REF}
  Source configuration: configured: github source archive
  Reachability: not_checked

Install Plan
  mode: ${mode}
  status: RUNTIME_SETUP_REQUIRED
  install_root: ${HOME}/.m32-bridge
  app_path: ${HOME}/.m32-bridge/app
  launcher_path: ${HOME}/.local/bin/m32-bridge
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
    command: download https://astral.sh/uv/install.sh to a temporary file; run only after exact INSTALL confirmation
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
TEXT
  } | paint_tty_lines
}

handle_missing_uv_tty_input() {
  if ! is_tty; then
    return
  fi
  if [ "${DRY_RUN}" = "1" ]; then
    return
  fi
  cat <<'SETUP'
Required Runtime Setup

uv is required to install and run M32 Bridge.
It will be installed for the current user only.
No administrator access is required.
System Python will not be changed.

Options:
  [1] Install uv user-locally
  [2] Show manual instructions
  [3] Exit
SETUP
  printf '%s' "Select [1-3]: "
  IFS= read -r answer || return
  case "${answer}" in
    /help|help)
      installer_help
      ;;
    /contact|contact)
      installer_contact
      ;;
    /status|status)
      printf '%s\n' "installer state: RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "OS: ${PLATFORM_VALUE}"
      printf '%s\n' "architecture: $(uname -m 2>/dev/null || printf unknown)"
      printf '%s\n' "shell: ${SHELL:-unknown}"
      printf '%s\n' "uv: missing"
      printf '%s\n' "managed Python: not_installed"
      printf '%s\n' "application: not_installed"
      printf '%s\n' "launcher: not_installed"
      printf '%s\n' "install source: ${INSTALL_SOURCE}"
      printf '%s\n' "Source configuration: configured: github source archive"
      printf '%s\n' "Reachability: not_checked"
      printf '%s\n' "Runtime config: not inspected until application runtime is ready"
      printf '%s\n' "safety: admin_required=false, system_python_unchanged=true, network_scan=not_run, console_probe=not_run, osc_writes_sent=0"
      ;;
    /clear|clear)
      printf '\033[2J\033[H'
      print_missing_uv_tty
      ;;
    /exit|exit|quit|q)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
    1)
      bootstrap_uv_tty
      ;;
    2)
      printf '%s\n' "Download ${UV_INSTALL_URL_POSIX}, inspect it, install uv for your user, then run: uv python install ${APPROVED_PYTHON_MINOR}"
      ;;
    3)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
    *)
      printf '%s\n' "status=RUNTIME_SETUP_REQUIRED"
      printf '%s\n' "No dependency action was taken."
      ;;
  esac
}

bootstrap_uv_tty() {
  cat <<'CONFIRM'
Source
  Official installer URL: https://astral.sh/uv/install.sh

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
CONFIRM
  IFS= read -r confirmation || return 1
  if [ "${confirmation}" != "INSTALL" ]; then
    printf '%s\n' "Exact INSTALL confirmation was not provided. No download or install was performed."
    return 1
  fi
  uv_temp="$(mktemp "${TMPDIR:-/tmp}/m32-uv-installer.XXXXXX")" || return 1
  trap 'rm -f "${uv_temp}"' 0 HUP INT TERM
  printf '%s\n' "URL: ${UV_INSTALL_URL_POSIX}"
  printf '%s\n' "Temporary path: ${uv_temp}"
  if command -v curl >/dev/null 2>&1; then
    curl -fLsS "${UV_INSTALL_URL_POSIX}" -o "${uv_temp}" || {
      printf '%s\n' "uv installer download failed." >&2
      rm -f "${uv_temp}"
      trap - 0 HUP INT TERM
      return 1
    }
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${uv_temp}" "${UV_INSTALL_URL_POSIX}" || {
      printf '%s\n' "uv installer download failed." >&2
      rm -f "${uv_temp}"
      trap - 0 HUP INT TERM
      return 1
    }
  else
    printf '%s\n' "No download tool is available. Use the manual instructions." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  fi
  if [ ! -s "${uv_temp}" ]; then
    printf '%s\n' "Downloaded uv installer is empty." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  fi
  /bin/sh "${uv_temp}" || {
    printf '%s\n' "uv installer execution failed." >&2
    rm -f "${uv_temp}"
    trap - 0 HUP INT TERM
    return 1
  }
  rm -f "${uv_temp}"
  trap - 0 HUP INT TERM
  UV_BIN="${HOME}/.local/bin/uv"
  if [ ! -x "${UV_BIN}" ]; then
    printf '%s\n' "uv installation completed but the expected user-local executable is unavailable: ${UV_BIN}" >&2
    return 1
  fi
  PATH="${HOME}/.local/bin:${PATH}"
  export PATH
  "${UV_BIN}" --version
  UV_MANAGED_PYTHON=1 "${UV_BIN}" python install "${APPROVED_PYTHON_MINOR}" || {
    printf '%s\n' "Managed CPython 3.13 installation failed." >&2
    return 1
  }
  managed_python="$(UV_MANAGED_PYTHON=1 "${UV_BIN}" python find --managed-python "${APPROVED_PYTHON_MINOR}" 2>/dev/null || true)"
  if [ -z "${managed_python}" ] || [ ! -x "${managed_python}" ]; then
    printf '%s\n' "Managed CPython 3.13 could not be rediscovered." >&2
    return 1
  fi
  "${managed_python}" --version
  printf '%s\n' "Managed Python path: ${managed_python}"
  return 0
}

print_missing_uv_json() {
  APP_PATH="${HOME}/.m32-bridge/app"
  LAUNCHER_PATH="${HOME}/.local/bin/m32-bridge"
  cat <<JSON
{
  "ok": false,
  "status": "RUNTIME_SETUP_REQUIRED",
  "platform": "${PLATFORM_VALUE}",
  "app_path": "${APP_PATH}",
  "launcher_path": "${LAUNCHER_PATH}",
  "install_root": "${HOME}/.m32-bridge",
  "requires_admin": false,
  "admin_required": false,
  "user_local": true,
  "global_py_required": false,
  "global_python_required": false,
  "uv_required": true,
  "uv_detected": false,
  "python_required": true,
  "python_managed_by_uv": true,
  "approved_python_minor": "${APPROVED_PYTHON_MINOR}",
  "project_python_range": "${PROJECT_PYTHON_RANGE}",
  "system_python_modified": false,
  "global_python_installed": false,
  "default_python_aliases_installed": false,
  "installer_can_continue": false,
  "confirmation_required": true,
  "uv_status": "manual_action_required",
  "required_actions": $(required_actions_json),
  "osc_writes_sent": 0,
  "hardware_verified": false,
  "production_live_ready": false,
  "version": "${TARGET_VERSION}",
  "target_version": "${TARGET_VERSION}",
  "install_source": "${INSTALL_SOURCE}",
  "source_url": "${SOURCE_URL}",
  "source_ref": "${SOURCE_REF}",
  "path_updated": false,
  "recommendations": [
    "Install uv in user space, then rerun this installer.",
    "No system-wide interpreter or \`py\` launcher is required.",
    "POSIX bootstrap supports curl first, wget fallback, or manual download."
  ]
}
JSON
}

download_remote_source() {
  mkdir -p "${REPO_ROOT}"
  archive="${REPO_ROOT}/source.tar.gz"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${SOURCE_URL}" -o "${archive}"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${archive}" "${SOURCE_URL}"
  else
    echo "curl and wget are unavailable. Manually download ${SOURCE_URL}, inspect it, and rerun from the extracted project." >&2
    return 1
  fi
  tar -xzf "${archive}" -C "${REPO_ROOT}"
  extracted="$(find "${REPO_ROOT}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "${extracted}" ] || [ ! -d "${extracted}/src/m32_bridge" ] || [ ! -f "${extracted}/pyproject.toml" ]; then
    echo "Downloaded source archive did not contain expected m32_bridge project files." >&2
    return 1
  fi
  REPO_ROOT="${extracted}"
}

cleanup_remote_source() {
  target="${BOOTSTRAP_SOURCE_ROOT:-}"
  case "${target}" in
    "${TMPDIR:-/tmp}"/m32-bridge-bootstrap-*)
      if [ -d "${target}" ]; then
        rm -r -- "${target}"
      fi
      ;;
  esac
}

RUNTIME_MODULE="m32_bridge.installer.script_runtime"
set -- python -m "${RUNTIME_MODULE}" --surface posix --platform "${PLATFORM_VALUE}" --target-version "${TARGET_VERSION}" --install-source "${INSTALL_SOURCE}" --source-url "${SOURCE_URL}" --source-ref "${SOURCE_REF}"
if [ "${DRY_RUN}" = "1" ]; then
  set -- "$@" --dry-run
fi
if [ "${JSON_OUTPUT}" = "1" ]; then
  set -- "$@" --json
fi
if [ "${JSON_OUTPUT}" != "1" ] && is_tty; then
  set -- "$@" --tty --color
fi

UV_BIN="$(command -v uv 2>/dev/null || true)"
if [ -z "${UV_BIN}" ] && [ "${JSON_OUTPUT}" != "1" ] && [ "${DRY_RUN}" != "1" ] && is_tty; then
  print_missing_uv_tty
  if handle_missing_uv_tty_input; then
    UV_BIN="$(command -v uv 2>/dev/null || true)"
    if [ -z "${UV_BIN}" ] && [ -x "${HOME}/.local/bin/uv" ]; then
      UV_BIN="${HOME}/.local/bin/uv"
    fi
  fi
fi

if [ -n "${UV_BIN}" ]; then
  if [ "${INSTALL_SOURCE}" != "local_checkout" ]; then
    BOOTSTRAP_SOURCE_ROOT="${REPO_ROOT}"
    trap 'cleanup_remote_source' 0 HUP INT TERM
    if ! download_remote_source; then
      exit 1
    fi
  fi
  if [ ! -f "${REPO_ROOT}/uv.lock" ]; then
    echo "uv.lock is required for reproducible frozen runtime execution. Refusing unfrozen install." >&2
    exit 1
  fi
  if [ "${DRY_RUN}" != "1" ]; then
    set -- "$@" --bootstrap-apply --uv-bin "${UV_BIN}"
  fi
  PYTHONPATH_VALUE="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  if [ "${M32_INSTALL_ASSUME_UV:-}" = "installed_user_local" ] && [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    shift
    PYTHONPATH="${PYTHONPATH_VALUE}" "${REPO_ROOT}/.venv/bin/python" "$@"
  else
    if [ -z "${UV_CACHE_DIR:-}" ]; then
      mkdir -p "${DEFAULT_UV_CACHE_DIR}"
      UV_CACHE_DIR="${DEFAULT_UV_CACHE_DIR}"
      export UV_CACHE_DIR
    fi
    PYTHONPATH="${PYTHONPATH_VALUE}" UV_MANAGED_PYTHON=1 M32_INSTALL_UV_BIN="${UV_BIN}" \
      "${UV_BIN}" run --managed-python --python "${APPROVED_PYTHON_MINOR}" --no-build --no-project "$@"
  fi
else
  if [ "${JSON_OUTPUT}" = "1" ]; then
    print_missing_uv_json
  elif is_tty && [ "${DRY_RUN}" = "1" ]; then
    print_missing_uv_tty
  else
    echo "M32 Bridge installer status"
    if [ "${DRY_RUN}" = "1" ]; then
      echo "mode: dry-run"
    else
      echo "mode: status"
    fi
    echo "status: RUNTIME_SETUP_REQUIRED"
    echo "install_root: ${HOME}/.m32-bridge"
    echo "app_path: ${HOME}/.m32-bridge/app"
    echo "launcher_path: ${HOME}/.local/bin/m32-bridge"
    echo "install_source: ${INSTALL_SOURCE}"
    echo "source_url: ${SOURCE_URL}"
    echo "user_local: true"
    echo "admin_required=false"
    echo "global_py_required=false"
    echo "global_python_required=false"
    echo "approved_python_minor=${APPROVED_PYTHON_MINOR}"
    echo "project_python_range=${PROJECT_PYTHON_RANGE}"
    echo "system_python_modified=false"
    echo "installer_can_continue=false"
    echo "uv_status=manual_action_required"
    echo "hardware_verified=false"
    echo "production_live_ready=false"
    echo "osc_writes_sent=0"
    echo "Install uv in user space, then rerun this installer. No system-wide interpreter or \`py\` launcher is required."
    echo "Post-install checks: m32-bridge health, m32-bridge setup, m32-bridge get-info, m32-bridge detect-device, m32-bridge doctor-runtime."
  fi
  exit 1
fi
