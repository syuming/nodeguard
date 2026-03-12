#!/usr/bin/env bash
# =============================================================================
#  NetMonitor 一鍵安裝腳本（Ubuntu 20.04 / 22.04 / 24.04）
#  用法：
#    export GH_TOKEN="ghp_你的Token"
#    curl -fsSL -H "Authorization: token $GH_TOKEN" \
#      https://raw.githubusercontent.com/syuming/monitor/main/install.sh \
#      | sudo -E bash
# =============================================================================

set -euo pipefail

# ── 顏色輸出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

# ── Token 檢查 ────────────────────────────────────────────────────────────────
GH_TOKEN="${GH_TOKEN:-}"
[[ -z "$GH_TOKEN" ]] && error "請先設定 GH_TOKEN：\n  export GH_TOKEN=\"ghp_你的Token\"\n  然後重新執行安裝指令"

# ── 設定變數（可在這裡修改） ──────────────────────────────────────────────────
APP_DIR="/opt/netmonitor"
REPO_URL="https://${GH_TOKEN}@github.com/syuming/monitor.git"
SERVICE_NAME="netmonitor"
APP_PORT="8000"
ADMIN_USER="admin"
ADMIN_PASS="admin1234"
PYTHON="python3"

# ── 權限檢查 ──────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "請用 sudo 執行：sudo bash install.sh"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NetMonitor 一鍵安裝程式        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── 1. 更新套件清單 ───────────────────────────────────────────────────────────
info "更新套件清單..."
apt-get update -qq
success "套件清單更新完成"

# ── 2. 安裝系統相依套件 ───────────────────────────────────────────────────────
info "安裝系統套件（python3, pip, venv, git, ping）..."
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl iputils-ping net-tools
success "系統套件安裝完成"

# ── 3. 下載程式碼 ─────────────────────────────────────────────────────────────
if [[ -d "$APP_DIR/.git" ]]; then
    info "偵測到已有安裝，執行 git pull 更新..."
    cd "$APP_DIR"
    git pull --quiet
    success "程式碼更新完成"
else
    info "從 GitHub 下載程式碼至 $APP_DIR ..."
    rm -rf "$APP_DIR"
    git clone --quiet "$REPO_URL" "$APP_DIR"
    success "程式碼下載完成"
fi
cd "$APP_DIR"

# ── 4. 建立 Python 虛擬環境 ───────────────────────────────────────────────────
info "建立 Python 虛擬環境..."
$PYTHON -m venv venv
source venv/bin/activate
success "虛擬環境啟動完成（$(python --version)）"

# ── 5. 安裝 Python 套件 ───────────────────────────────────────────────────────
info "安裝 Python 套件（Django / netmiko / gunicorn）..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python 套件安裝完成"

# ── 6. 初始化資料庫 ───────────────────────────────────────────────────────────
info "執行資料庫 Migration..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫初始化完成"

# ── 7. 收集靜態檔案 ───────────────────────────────────────────────────────────
info "收集靜態檔案..."
python manage.py collectstatic --noinput --quiet 2>/dev/null || true
success "靜態檔案收集完成"

# ── 8. 建立預設管理員帳號 ─────────────────────────────────────────────────────
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

# ── 9. 建立 systemd 服務 ──────────────────────────────────────────────────────
info "建立 systemd 服務（${SERVICE_NAME}）..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=NetMonitor - 網路設備監控系統
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/gunicorn \\
    --workers 1 \\
    --threads 4 \\
    --bind 0.0.0.0:${APP_PORT} \\
    --timeout 120 \\
    --access-logfile ${APP_DIR}/access.log \\
    --error-logfile ${APP_DIR}/error.log \\
    netmonitor.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME} --quiet
success "systemd 服務設定完成"

# ── 10. 啟動服務 ──────────────────────────────────────────────────────────────
info "啟動 NetMonitor 服務..."
systemctl restart ${SERVICE_NAME}
sleep 2

if systemctl is-active --quiet ${SERVICE_NAME}; then
    success "服務啟動成功！"
else
    warn "服務啟動異常，查看錯誤：journalctl -u ${SERVICE_NAME} -n 30"
fi

# ── 11. 完成提示 ──────────────────────────────────────────────────────────────
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║          安裝完成！                          ║${RESET}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════════╣${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  網址：  ${CYAN}http://${SERVER_IP}:${APP_PORT}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  帳號：  ${YELLOW}${ADMIN_USER}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  密碼：  ${YELLOW}${ADMIN_PASS}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  ${BOLD}常用指令：${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  查看狀態：${CYAN}systemctl status ${SERVICE_NAME}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  重新啟動：${CYAN}systemctl restart ${SERVICE_NAME}${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  查看日誌：${CYAN}journalctl -u ${SERVICE_NAME} -f${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  ${YELLOW}⚠ 請登入後立即修改預設密碼！${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""
