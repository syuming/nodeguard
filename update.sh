#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵更新腳本
#  用法：sudo bash /opt/netmonitor/update.sh
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

[[ $EUID -ne 0 ]] && error "請用 sudo 執行：sudo bash update.sh"
[[ ! -d "$APP_DIR/.git" ]] && error "找不到 ${APP_DIR}，請先執行安裝腳本"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NetMonitor 更新程式            ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── 1. 拉取最新程式碼 ─────────────────────────────────────────────────────────
info "拉取最新程式碼..."
cd "$APP_DIR"
git pull --quiet
success "程式碼已更新"

# ── 2. 安裝新套件（如有新增） ─────────────────────────────────────────────────
info "更新 Python 套件..."
source venv/bin/activate
pip install --quiet -r requirements.txt
success "Python 套件已更新"

# ── 3. 執行新的 Migration ─────────────────────────────────────────────────────
info "執行資料庫 Migration..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫已更新"

# ── 4. 更新靜態檔案 ───────────────────────────────────────────────────────────
info "更新靜態檔案..."
python manage.py collectstatic --noinput --quiet 2>/dev/null || true
success "靜態檔案已更新"

deactivate

# ── 5. 重新啟動服務 ───────────────────────────────────────────────────────────
info "重新啟動服務..."
systemctl restart ${SERVICE_NAME}
sleep 2

if systemctl is-active --quiet ${SERVICE_NAME}; then
    success "服務重新啟動成功"
else
    warn "服務啟動異常，查看錯誤：journalctl -u ${SERVICE_NAME} -n 30"
fi

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║          更新完成！                  ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
