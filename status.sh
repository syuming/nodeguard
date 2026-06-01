#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${APP_DIR}/nodeguard.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "✅ 執行中（PID: $(cat "$PID_FILE")）"
else
    echo "⛔ 未在執行"
fi
