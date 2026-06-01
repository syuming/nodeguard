#!/usr/bin/env bash
# =============================================================================
#  NodeGuard 一鍵安裝腳本
#
#  一行安裝（需 SSH key 已設定）：
#    bash <(curl -fsSL https://raw.githubusercontent.com/syuming/nodeguard/main/install.sh)
#
#  或先 clone 再安裝：
#    git clone git@github.com:syuming/nodeguard ~/nodeguard && bash ~/nodeguard/install.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }

APP_DIR="${HOME}/nodeguard"
REPO_SSH="git@github.com:syuming/nodeguard.git"
APP_PORT="8000"
ADMIN_USER="admin"
ADMIN_PASS="NodeGuard@2026"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NodeGuard 一鍵安裝程式        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── 1. 檢查必要工具 ──────────────────────────────────────────────────────────
info "檢查系統環境..."
for cmd in python3 git; do
    command -v "$cmd" &>/dev/null || error "找不到 ${cmd}，請先安裝：sudo apt-get install -y ${cmd}"
done
success "系統環境正常（$(python3 --version)）"

# ── 2. 取得程式碼 ─────────────────────────────────────────────────────────────
# 若 install.sh 本身就在 repo 內（clone 後直接執行），直接用該目錄，不重複 clone
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
REPO_ORIGIN="$(git -C "${SCRIPT_DIR}" remote get-url origin 2>/dev/null || true)"

if [[ "$REPO_ORIGIN" == *"syuming/nodeguard"* ]]; then
    APP_DIR="$SCRIPT_DIR"
    info "使用現有目錄：${APP_DIR}"
    git -C "$APP_DIR" pull --quiet && success "程式碼已更新" || warn "git pull 失敗，使用現有版本"
elif [[ -d "${APP_DIR}/.git" ]]; then
    warn "${APP_DIR} 已存在，執行 git pull 更新..."
    git -C "$APP_DIR" pull --quiet
    success "程式碼已更新"
else
    info "從 GitHub 下載程式碼至 ${APP_DIR}..."
    git clone --quiet "$REPO_SSH" "$APP_DIR"
    success "程式碼就緒"
fi
cd "$APP_DIR"

# ── 3. 建立 Python 虛擬環境 ───────────────────────────────────────────────────
if [[ ! -d "${APP_DIR}/venv" ]]; then
    info "建立 Python 虛擬環境..."
    python3 -m venv venv
    success "虛擬環境建立完成"
else
    info "虛擬環境已存在，略過"
fi
source venv/bin/activate

# ── 4. 安裝 Python 套件 ───────────────────────────────────────────────────────
info "安裝 Python 套件..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
success "Python 套件安裝完成"

# ── 5. 建立 .env ──────────────────────────────────────────────────────────────
if [[ ! -f "${APP_DIR}/.env" ]]; then
    info "產生設定檔 .env..."
    SECRET_KEY=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'!@#%^&*-_=+') for _ in range(50)))")
    printf 'SECRET_KEY=%s\nDEBUG=False\nALLOWED_HOSTS=localhost,127.0.0.1\n' "${SECRET_KEY}" > "${APP_DIR}/.env"
    success ".env 建立完成"
else
    info ".env 已存在，略過"
fi

# ── 6. 資料庫 Migration ───────────────────────────────────────────────────────
info "建立資料庫..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫就緒"

# ── 7. 靜態檔案 ───────────────────────────────────────────────────────────────
info "整理靜態檔案..."
python manage.py collectstatic --noinput
success "靜態檔案就緒"

# ── 8. 建立管理員帳號 ─────────────────────────────────────────────────────────
info "建立管理員帳號（${ADMIN_USER}）..."
python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='${ADMIN_USER}').exists():
    User.objects.create_superuser('${ADMIN_USER}', '', '${ADMIN_PASS}')
    print('帳號建立成功')
else:
    print('帳號已存在，略過')
" 2>/dev/null
success "管理員帳號設定完成"

deactivate

# ── 9. 啟動服務 ───────────────────────────────────────────────────────────────
info "啟動 NodeGuard..."
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
echo -e "${GREEN}${BOLD}║${RESET}  啟動：  ${CYAN}bash ~/nodeguard/start.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  停止：  ${CYAN}bash ~/nodeguard/stop.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  狀態：  ${CYAN}bash ~/nodeguard/status.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  更新：  ${CYAN}bash ~/nodeguard/update.sh${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}"
echo -e "${GREEN}${BOLD}║${RESET}  ${YELLOW}⚠ 請登入後立即至「個人資料」修改密碼！${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""
