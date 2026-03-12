#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵更新腳本（不需要 sudo）
#  用法：bash ~/netmonitor/update.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

APP_DIR="${HOME}/netmonitor"

[[ ! -d "$APP_DIR/.git" ]] && error "找不到 ${APP_DIR}，請先執行安裝腳本"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NetMonitor 更新程式            ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

info "停止服務..."
bash "${APP_DIR}/stop.sh" 2>/dev/null || true

info "拉取最新程式碼..."
cd "$APP_DIR"
git pull --quiet
success "程式碼已更新"

info "更新 Python 套件..."
source venv/bin/activate
pip install --quiet -r requirements.txt
success "Python 套件已更新"

info "執行資料庫 Migration..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫已更新"

info "更新靜態檔案..."
python manage.py collectstatic --noinput --quiet 2>/dev/null || true
success "靜態檔案已更新"

deactivate

info "重新啟動服務..."
bash "${APP_DIR}/start.sh"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║          更新完成！                  ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
