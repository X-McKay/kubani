#!/bin/bash
set -e

DISPLAY_WIDTH=${DISPLAY_WIDTH:-1280}
DISPLAY_HEIGHT=${DISPLAY_HEIGHT:-800}

# Start Xvfb (virtual display)
Xvfb :99 -screen 0 ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}x24 -nolisten tcp &
export DISPLAY=:99
sleep 1

# Start x11vnc (VNC server on port 5900)
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -quiet &

# Start noVNC websockify (WebSocket on 6080 -> VNC on 5900)
websockify --web /usr/share/novnc 6080 localhost:5900 &

# Start the MCP server
exec /app/.venv/bin/computer-mcp-server --mode sse --port 8086
