#!/usr/bin/env bash
# entrypoint.sh (updated: no venv; uses system websockify + python3)
set -euo pipefail

: "${AUTOMATR_SCREEN_W:=1366}"
: "${AUTOMATR_SCREEN_H:=768}"
: "${AUTOMATR_SCREEN_D:=24}"
: "${DISPLAY:=:99}"
: "${AUTOMATR_QUEUE_DIR:=/automatr/queue}"
: "${AUTOMATR_NOVNC_WEB:=/opt/novnc}"

# RTP-MIDI control socket (host can poke this if needed)
: "${AUTOMATR_ENABLE_RTPMIDI:=0}"
: "${AUTOMATR_RTPMIDI_SOCK:=/run/rtpmidid/control.sock}"

# Required for bot
: "${AUTOMATR_XMPP_PASSWORD:?AUTOMATR_XMPP_PASSWORD is required}"
: "${AUTOMATR_XMPP_HOST:?AUTOMATR_XMPP_HOST is required}"
: "${AUTOMATR_XMPP_DOMAIN:?AUTOMATR_XMPP_DOMAIN is required}"


log() { echo "[entrypoint] $*"; }

# If running as root, ensure runtime dirs and fix /automatr perms on bind mount
if [[ "$(id -u)" -eq 0 ]]; then
  mkdir -p /run/dbus /run/avahi-daemon /var/run/rtpmidid
  chown -R automatr:automatr /automatr || true

  install -d -m 775 -o automatr -g automatr /run/rtpmidid
  ln -snf /run/rtpmidid /var/run/rtpmidid

  # start dbus + avahi
  dbus-daemon --system --fork
  avahi-daemon --daemonize --no-drop-root || true

  # now re-exec entrypoint as automatr for the rest
  exec gosu automatr "$0" "$@"
fi

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

# Ensure required tools exist
WS_BIN="$(command -v websockify || true)"
PY_BIN="$(command -v python3 || true)"

if [[ -z "${WS_BIN}" ]] || [[ ! -x "${WS_BIN}" ]]; then
  log "ERROR: websockify not found in PATH"
  exit 1
fi
if [[ -z "${PY_BIN}" ]] || [[ ! -x "${PY_BIN}" ]]; then
  log "ERROR: python3 not found in PATH"
  exit 1
fi

log "Using DISPLAY=${DISPLAY}"
log "Using noVNC web dir: ${NOVNC_WEB}"
log "Using python: ${PY_BIN}"
log "Using websockify: ${WS_BIN}"
log "Using rtpmidid control socket: ${AUTOMATR_RTPMIDI_SOCK}"

# --- Start Xvfb ---
log "Starting Xvfb on ${DISPLAY} (${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D})..."
Xvfb "${DISPLAY}" -screen 0 "${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D}" -ac +extension RANDR &
XVFB_PID=$!

# --- Wait for X to be ready ---
for _ in $(seq 1 50); do
  if DISPLAY="${DISPLAY}" xdpyinfo >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

# --- Start WM ---
log "Starting Openbox..."
openbox --sm-disable &
WM_PID=$!

sleep 1

log "Starting Firefox + xterm..."
export HOME="${HOME:-/home/automatr}"

# Start xterm
DISPLAY="${DISPLAY}" xterm >/automatr/logs/xterm.log 2>&1 &
XTERM_PID=$!

# Start firefox
DISPLAY="${DISPLAY}" firefox-esr >/automatr/logs/firefox.log 2>&1 &
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


# --- Start rtpmidid (optional) ---
if [[ "${AUTOMATR_ENABLE_RTPMIDI}" == "1" ]]; then
  log "Starting rtpmidid (control: ${AUTOMATR_RTPMIDI_SOCK})..."
  mkdir -p "$(dirname "${AUTOMATR_RTPMIDI_SOCK}")" /var/run/rtpmidid
  (
    exec rtpmidid --control "${AUTOMATR_RTPMIDI_SOCK}"
  ) || log "ERROR: rtpmidid exited" &
  RTPMIDI_PID=$!
else
  log "rtpmidid disabled (AUTOMATR_ENABLE_RTPMIDI=0)"
  RTPMIDI_PID=""
fi

# --- Start automation runner ---
log "Starting automation runner..."
(
  exec "${PY_BIN}" /usr/local/bin/runner.py
) || log "ERROR: runner.py exited" &
RUNNER_PID=$!

# --- Start agent XMPP bot ---
log "Starting agent XMPP bot..."
(
  exec "${PY_BIN}" /usr/local/bin/agent_bot.py
) || log "ERROR: agent_bot.py exited" &
AGENT_PID=$!

cleanup() {
  log "Shutting down services..."
  kill \
    "${AGENT_PID}" \
    "${RUNNER_PID}" \
    "${RTPMIDI_PID}" \
    "${NOVNC_PID}" \
    "${VNC_PID}" \
    "${FIREFOX_PID}" \
    "${XTERM_PID}" \
    "${WM_PID}" \
    "${XVFB_PID}" \
    2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup SIGTERM SIGINT

log "All services started."
log "  VNC:     tcp://localhost:5900"
log "  noVNC:   http://localhost:6080/vnc.html?autoconnect=1&resize=remote"
log "  Runner:  watching ${AUTOMATR_QUEUE_DIR}"
log "  rtpmidid control socket: ${AUTOMATR_RTPMIDI_SOCK}"

# Keep container alive unless core desktop dies.
# If runner/firefox/xterm/rtpmidid dies, we keep the desktop + VNC up for debugging.
wait "${XVFB_PID}" "${WM_PID}"
cleanup
