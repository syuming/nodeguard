#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵移除腳本（完全刪除，資料不保留）
#  用法：sudo bash uninstall.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

APP_DIR="/opt/netmonitor"
SERVICE_NAME="netmonitor"

# ── 權限檢查 ──────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "請用 sudo 執行：sudo bash uninstall.sh"

echo ""
echo -e "${RED}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${RED}${BOLD}║     NetMonitor 完全移除程式          ║${RESET}"
echo -e "${RED}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "${YELLOW}⚠  警告：此操作將刪除所有資料（資料庫、設定、Log），且無法復原！${RESET}"
echo ""
read -r -p "確定要繼續嗎？輸入 YES 確認：" CONFIRM
[[ "$CONFIRM" != "YES" ]] && echo "已取消。" && exit 0

echo ""

# ── 1. 停止並移除 systemd 服務 ────────────────────────────────────────────────
info "停止服務 ${SERVICE_NAME}..."
systemctl stop ${SERVICE_NAME}  2>/dev/null || true
systemctl disable ${SERVICE_NAME} 2>/dev/null || true
rm -f /etc/systemd/system/${SERVICE_NAME}.service
systemctl daemon-reload
success "服務已停止並移除"

# ── 2. 刪除程式目錄（含資料庫、Log、虛擬環境） ───────────────────────────────
if [[ -d "$APP_DIR" ]]; then
    info "刪除程式目錄 ${APP_DIR}..."
    rm -rf "$APP_DIR"
    success "程式目錄已刪除"
else
    warn "找不到 ${APP_DIR}，略過"
fi

# ── 3. 完成 ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║       NetMonitor 已完全移除          ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
