#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${APP_DIR}/netmonitor.pid"
LOG_FILE="${APP_DIR}/netmonitor.log"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "NetMonitor 已在執行中（PID: $(cat "$PID_FILE")）"
    exit 0
fi

source "${APP_DIR}/venv/bin/activate"
cd "$APP_DIR"
nohup "${APP_DIR}/venv/bin/gunicorn" \
    --workers 1 --threads 4 \
    --bind "0.0.0.0:${PORT:-8000}" \
    --timeout 120 \
    --pid "$PID_FILE" \
    --access-logfile "${APP_DIR}/access.log" \
    --error-logfile "$LOG_FILE" \
    netmonitor.wsgi:application >> "$LOG_FILE" 2>&1 &

sleep 1
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "✅ NetMonitor 已啟動（PID: $(cat "$PID_FILE")，Port: ${PORT:-8000}）"
else
    echo "❌ 啟動失敗，查看日誌：cat ${LOG_FILE}"
fi
