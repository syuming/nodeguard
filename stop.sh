#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${APP_DIR}/netmonitor.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")"
    sleep 1
fi
rm -f "$PID_FILE"

# 確保 port 釋放
fuser -k 8000/tcp 2>/dev/null || true

echo "✅ NetMonitor 已停止"
