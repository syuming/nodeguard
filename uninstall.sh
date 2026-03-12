#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵移除腳本（完全刪除，資料不保留，不需要 sudo）
#  用法：bash ~/netmonitor/uninstall.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'

APP_DIR="${HOME}/netmonitor"

echo ""
echo -e "${RED}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${RED}${BOLD}║     NetMonitor 完全移除程式          ║${RESET}"
echo -e "${RED}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "${YELLOW}⚠  警告：將刪除 ${APP_DIR} 的所有資料（資料庫、Log），且無法復原！${RESET}"
echo ""
read -r -p "確定要繼續嗎？輸入 YES 確認：" CONFIRM
[[ "$CONFIRM" != "YES" ]] && echo "已取消。" && exit 0

echo ""

# ── 停止服務 ──────────────────────────────────────────────────────────────────
if [[ -f "${APP_DIR}/stop.sh" ]]; then
    echo -e "${YELLOW}[INFO]${RESET}  停止服務..."
    bash "${APP_DIR}/stop.sh" 2>/dev/null || true
fi

# ── 刪除目錄 ──────────────────────────────────────────────────────────────────
if [[ -d "$APP_DIR" ]]; then
    echo -e "${YELLOW}[INFO]${RESET}  刪除 ${APP_DIR}..."
    rm -rf "$APP_DIR"
    echo -e "${GREEN}[OK]${RESET}    目錄已刪除"
else
    echo -e "${YELLOW}[WARN]${RESET}  找不到 ${APP_DIR}，略過"
fi

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║       NetMonitor 已完全移除          ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
