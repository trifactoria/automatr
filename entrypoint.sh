#!/bin/bash
set -e

# Start X server
echo "Starting Xvfb on ${DISPLAY} with geometry ${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D}..."
Xvfb ${DISPLAY} -screen 0 ${AUTOMATR_SCREEN_W}x${AUTOMATR_SCREEN_H}x${AUTOMATR_SCREEN_D} -ac &
XVFB_PID=$!

# Wait for X to be ready
sleep 2

# Start window manager
echo "Starting Openbox..."
openbox --sm-disable &
WM_PID=$!

# Wait for WM to initialize
sleep 1

# Start Firefox in fullscreen
echo "Starting Firefox..."
firefox-esr --kiosk about:blank &
FIREFOX_PID=$!

# Start x11vnc
echo "Starting x11vnc..."
x11vnc -display ${DISPLAY} -forever -shared -rfbport 5900 -nopw &
VNC_PID=$!

# Wait for VNC to be ready
sleep 2

# Start noVNC/websockify
echo "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 &
NOVNC_PID=$!

# Start automation runner
echo "Starting automation runner..."
python3 /usr/local/bin/runner.py &
RUNNER_PID=$!

# Function to cleanup on exit
cleanup() {
    echo "Shutting down services..."
    kill $RUNNER_PID $NOVNC_PID $VNC_PID $FIREFOX_PID $WM_PID $XVFB_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

echo "All services started. Container ready."
echo "  Xvfb:    ${DISPLAY}"
echo "  VNC:     localhost:5900"
echo "  noVNC:   http://localhost:6080"
echo "  Runner:  watching ${AUTOMATR_QUEUE_DIR}"

# Wait for any process to exit
wait -n

# If any process exits, trigger cleanup
cleanup
