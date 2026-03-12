#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵安裝腳本（Ubuntu，不需要 sudo）
#  安裝位置：~/netmonitor
#
#  用法：
#    export GH_TOKEN="ghp_你的Token"
#    curl -fsSL -H "Authorization: token $GH_TOKEN" \
#      https://raw.githubusercontent.com/syuming/monitor/main/install.sh \
#      | GH_TOKEN=$GH_TOKEN bash
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

# ── Token 檢查 ────────────────────────────────────────────────────────────────
GH_TOKEN="${GH_TOKEN:-}"
[[ -z "$GH_TOKEN" ]] && error "請先設定 GH_TOKEN：\n  export GH_TOKEN=\"ghp_你的Token\"\n  然後重新執行安裝指令"

# ── 設定變數 ──────────────────────────────────────────────────────────────────
APP_DIR="${HOME}/netmonitor"
REPO_URL="https://${GH_TOKEN}@github.com/syuming/monitor.git"
APP_PORT="8000"
ADMIN_USER="admin"
ADMIN_PASS="admin1234"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NetMonitor 一鍵安裝程式        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── 1. 檢查相依指令 ───────────────────────────────────────────────────────────
info "檢查系統環境..."
for cmd in python3 git curl; do
    command -v "$cmd" &>/dev/null || error "找不到 ${cmd}，請先安裝：sudo apt-get install -y ${cmd}"
done
success "系統環境正常"

# ── 2. 下載程式碼 ─────────────────────────────────────────────────────────────
if [[ -d "$APP_DIR/.git" ]]; then
    info "偵測到已有安裝，執行 git pull 更新..."
    cd "$APP_DIR"
    git pull --quiet
    success "程式碼更新完成"
else
    info "從 GitHub 下載程式碼至 ${APP_DIR}..."
    git clone --quiet "$REPO_URL" "$APP_DIR"
    success "程式碼下載完成"
fi
cd "$APP_DIR"

# ── 3. 建立 Python 虛擬環境 ───────────────────────────────────────────────────
info "建立 Python 虛擬環境..."
python3 -m venv venv
source venv/bin/activate
success "虛擬環境啟動完成（$(python --version)）"

# ── 4. 安裝 Python 套件 ───────────────────────────────────────────────────────
info "安裝 Python 套件..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python 套件安裝完成"

# ── 5. 初始化資料庫 ───────────────────────────────────────────────────────────
info "執行資料庫 Migration..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫初始化完成"

# ── 6. 收集靜態檔案 ───────────────────────────────────────────────────────────
info "收集靜態檔案..."
python manage.py collectstatic --noinput --quiet 2>/dev/null || true
success "靜態檔案收集完成"

# ── 7. 建立預設管理員帳號 ─────────────────────────────────────────────────────
info "建立管理員帳號（${ADMIN_USER}）..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${ADMIN_USER}').exists():
    User.objects.create_superuser('${ADMIN_USER}', '', '${ADMIN_PASS}')
    print('帳號建立成功')
else:
    print('帳號已存在，略過')
" 2>/dev/null
success "管理員帳號設定完成"

deactivate

# ── 8. 建立 start / stop / status 腳本 ───────────────────────────────────────
info "建立管理腳本..."

cat > "${APP_DIR}/start.sh" << 'STARTEOF'
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
STARTEOF

cat > "${APP_DIR}/stop.sh" << 'STOPEOF'
#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${APP_DIR}/netmonitor.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")"
    rm -f "$PID_FILE"
    echo "✅ NetMonitor 已停止"
else
    echo "NetMonitor 未在執行中"
    rm -f "$PID_FILE"
fi
STOPEOF

cat > "${APP_DIR}/status.sh" << 'STATUSEOF'
#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${APP_DIR}/netmonitor.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "✅ 執行中（PID: $(cat "$PID_FILE")）"
else
    echo "⛔ 未在執行"
fi
STATUSEOF

chmod +x "${APP_DIR}/start.sh" "${APP_DIR}/stop.sh" "${APP_DIR}/status.sh"
success "管理腳本建立完成"

# ── 9. 啟動服務 ───────────────────────────────────────────────────────────────
info "啟動 NetMonitor..."
bash "${APP_DIR}/start.sh"

# ── 10. 完成提示 ──────────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║          安裝完成！                          ║${RESET}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════╣${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  安裝目錄：${CYAN}${APP_DIR}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  網址：    ${CYAN}http://${SERVER_IP}:${APP_PORT}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  帳號：    ${YELLOW}${ADMIN_USER}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  密碼：    ${YELLOW}${ADMIN_PASS}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  ${BOLD}常用指令：${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  啟動：  ${CYAN}bash ~/netmonitor/start.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  停止：  ${CYAN}bash ~/netmonitor/stop.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  狀態：  ${CYAN}bash ~/netmonitor/status.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  更新：  ${CYAN}bash ~/netmonitor/update.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  移除：  ${CYAN}bash ~/netmonitor/uninstall.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  ${YELLOW}⚠ 請登入後立即修改預設密碼！${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""
