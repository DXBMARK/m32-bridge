#!/bin/sh
set -eu

# M32 Bridge POSIX user-local installer surface.
# Official targets: macOS, Linux, WSL, Raspberry Pi OS.
# Official quick command: curl -fsSL <raw-url>/scripts/install.sh | sh
# Safer path: download, inspect, then run locally.
# Download options: curl first when available, wget fallback, or manual download fallback.
# GitHub raw bootstrap: when this script is run without repo files beside it,
# it downloads a source archive into temp staging and runs the same runtime there.
# This is a readable text script. It creates only user-local files unless --dry-run is used.
# No binary installers, ports, or background daemon.
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

DRY_RUN=0
JSON_OUTPUT=0
PLATFORM=""
TARGET_VERSION="0.1.0"
DEFAULT_SOURCE_REF="main"
DEFAULT_SOURCE_URL="https://github.com/DXBMARK/m32-bridge/archive/refs/heads/main.tar.gz"
SOURCE_URL="${M32_INSTALL_SOURCE_URL:-${DEFAULT_SOURCE_URL}}"
SOURCE_REF="${M32_INSTALL_SOURCE_REF:-}"

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
  --dry-run          Print intended status/actions only.
  --json             Emit structured JSON.
  --platform VALUE   macos, linux, wsl, raspberry_pi_os.
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

RUNTIME_MODULE="m32_bridge.installer.script_runtime"
set -- python -m "${RUNTIME_MODULE}" --surface posix --platform "${PLATFORM_VALUE}" --target-version "${TARGET_VERSION}" --install-source "${INSTALL_SOURCE}" --source-url "${SOURCE_URL}" --source-ref "${SOURCE_REF}"
if [ "${DRY_RUN}" = "1" ]; then
  set -- "$@" --dry-run
fi
if [ "${JSON_OUTPUT}" = "1" ]; then
  set -- "$@" --json
fi

if command -v uv >/dev/null 2>&1; then
  if [ "${INSTALL_SOURCE}" != "local_checkout" ]; then
    if ! download_remote_source; then
      exit 1
    fi
  fi
  PYTHONPATH_VALUE="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  PYTHONPATH="${PYTHONPATH_VALUE}" UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}" uv run "$@"
else
  if [ "${JSON_OUTPUT}" = "1" ]; then
    print_missing_uv_json
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
