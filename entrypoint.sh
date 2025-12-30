#!/bin/bash
set -euo pipefail

: "${AUTOMATR_SCREEN_W:=1366}"
: "${AUTOMATR_SCREEN_H:=768}"
: "${AUTOMATR_SCREEN_D:=24}"
: "${DISPLAY:=:99}"
: "${AUTOMATR_QUEUE_DIR:=/automatr/queue}"
: "${AUTOMATR_NOVNC_WEB:=/opt/novnc}"
: "${VENV_PATH:=/opt/venv}"

log() { echo "[entrypoint] $*"; }

# Ensure X socket dir exists
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# Ensure queue exists (mounted volume may be empty)
mkdir -p "${AUTOMATR_QUEUE_DIR}"

# Resolve noVNC web root:
# 1) If AUTOMATR_NOVNC_WEB is set and valid, use it.
# 2) Otherwise search common locations.
NOVNC_WEB=""
if [[ -n "${AUTOMATR_NOVNC_WEB}" ]] && [[ -d "${AUTOMATR_NOVNC_WEB}" ]] && \
   ([[ -f "${AUTOMATR_NOVNC_WEB}/vnc.html" ]] || [[ -f "${AUTOMATR_NOVNC_WEB}/index.html" ]]); then
  NOVNC_WEB="${AUTOMATR_NOVNC_WEB}"
else
  for d in \
    "/opt/novnc" \
    "/usr/share/novnc" \
    "/usr/share/novnc/www" \
    "/usr/share/noVNC" \
    "/usr/share/noVNC/www" \
  ; do
    if [[ -d "$d" ]] && ([[ -f "$d/vnc.html" ]] || [[ -f "$d/index.html" ]]); then
      NOVNC_WEB="$d"
      break
    fi
  done
fi

if [[ -z "${NOVNC_WEB}" ]]; then
  log "ERROR: Could not find noVNC web directory."
  log "Set AUTOMATR_NOVNC_WEB to a directory containing vnc.html (e.g. /opt/novnc)."
  exit 1
fi

# Ensure venv tools exist
WS_BIN="${VENV_PATH}/bin/websockify"
PY_BIN="${VENV_PATH}/bin/python"

if [[ ! -x "${WS_BIN}" ]]; then
  log "ERROR: websockify not found at ${WS_BIN}"
  exit 1
fi
if [[ ! -x "${PY_BIN}" ]]; then
  log "ERROR: python not found at ${PY_BIN}"
  exit 1
fi

log "Using DISPLAY=${DISPLAY}"
log "Using noVNC web dir: ${NOVNC_WEB}"
log "Using venv python: ${PY_BIN}"
log "Using websockify: ${WS_BIN}"

# --- Start Xvfb ---
log "Starting Xvfb on ${DISPLAY} (${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D})..."
Xvfb "${DISPLAY}" -screen 0 "${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D}" -ac +extension RANDR &
XVFB_PID=$!

sleep 1

# --- Start WM ---
log "Starting Openbox..."
openbox --sm-disable &
WM_PID=$!

sleep 1

# --- Start Firefox (non-fatal) ---
log "Starting Firefox (kiosk)..."
(
  # Ensure HOME is set for profile stability
  export HOME="${HOME:-/home/automatr}"
  firefox-esr --kiosk about:blank
) || log "WARN: firefox-esr exited immediately" &
FIREFOX_PID=$!

# --- Start x11vnc ---
log "Starting x11vnc on :5900..."
x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw -xkb -noxrecord -noxfixes -noxdamage &
VNC_PID=$!

sleep 1

# --- Start noVNC/websockify ---
log "Starting noVNC (websockify) on :6080..."
(
  exec "${WS_BIN}" --web="${NOVNC_WEB}" 6080 localhost:5900
) &
NOVNC_PID=$!

# --- Start runner (non-fatal to desktop) ---
log "Starting automation runner..."
(
  exec "${PY_BIN}" /usr/local/bin/runner.py
) || log "ERROR: runner.py exited" &
RUNNER_PID=$!

cleanup() {
  log "Shutting down services..."
  kill "${RUNNER_PID}" "${NOVNC_PID}" "${VNC_PID}" "${FIREFOX_PID}" "${WM_PID}" "${XVFB_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup SIGTERM SIGINT

log "All services started."
log "  VNC:    tcp://localhost:5900"
log "  noVNC:  http://localhost:6080/vnc.html?autoconnect=1&resize=remote"
log "  Runner: watching ${AUTOMATR_QUEUE_DIR}"

# Keep container alive unless core desktop dies.
# If runner/firefox dies, we keep the desktop + VNC up for debugging.
wait "${XVFB_PID}" "${WM_PID}"
cleanup
