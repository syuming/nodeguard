#!/usr/bin/env bash
# =============================================================================
#  NodeGuard 一鍵更新腳本（不需要 sudo）
#  用法：bash ~/nodeguard/update.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; }

APP_DIR="${HOME}/nodeguard"
BACKUP_DIR="${APP_DIR}/.backups"

[[ ! -d "$APP_DIR/.git" ]] && error "找不到 ${APP_DIR}，請先執行安裝腳本" && exit 1

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║       NodeGuard 更新程式             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""

cd "$APP_DIR"

# ── 記錄當前狀態（供 rollback 用）─────────────────────────────────────────────
PREV_COMMIT=$(git rev-parse HEAD)
PREV_VERSION=$(cat VERSION)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# ── rollback 函式 ──────────────────────────────────────────────────────────────
rollback() {
    echo ""
    warn "更新失敗，開始還原..."
    git reset --hard "$PREV_COMMIT" --quiet 2>/dev/null || true
    DB_BACKUP="${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"
    if [[ -f "$DB_BACKUP" ]]; then
        cp "$DB_BACKUP" "${APP_DIR}/db.sqlite3"
        success "資料庫已還原至備份"
    fi
    source venv/bin/activate 2>/dev/null || true
    pip install --quiet -r requirements.txt 2>/dev/null || true
    deactivate 2>/dev/null || true
    bash "${APP_DIR}/start.sh" 2>/dev/null || true
    echo ""
    echo -e "${RED}${BOLD}╔══════════════════════════════════════╗${RESET}"
    echo -e "${RED}${BOLD}║   更新失敗，已還原至 v${PREV_VERSION}   ║${RESET}"
    echo -e "${RED}${BOLD}╚══════════════════════════════════════╝${RESET}"
    echo ""
    exit 1
}
trap rollback ERR

# ── 1. 備份資料庫 ──────────────────────────────────────────────────────────────
if [[ -f "${APP_DIR}/db.sqlite3" ]]; then
    info "備份資料庫..."
    cp "${APP_DIR}/db.sqlite3" "${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"
    success "資料庫備份至 .backups/db_${TIMESTAMP}.sqlite3"
fi

# 只保留最近 5 份備份
ls -t "${BACKUP_DIR}"/db_*.sqlite3 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true

# ── 2. 停止服務 ────────────────────────────────────────────────────────────────
info "停止服務..."
bash "${APP_DIR}/stop.sh" 2>/dev/null || true

# ── 3. 拉取最新程式碼 ──────────────────────────────────────────────────────────
info "拉取最新程式碼..."
git pull --quiet
NEW_VERSION=$(cat VERSION)
success "程式碼已更新（v${PREV_VERSION} → v${NEW_VERSION}）"

# ── 4. 更新 Python 套件 ────────────────────────────────────────────────────────
info "更新 Python 套件..."
source venv/bin/activate
pip install --quiet -r requirements.txt
success "Python 套件已更新"

# ── 5. 資料庫 Migration ────────────────────────────────────────────────────────
info "執行資料庫 Migration..."
python manage.py migrate --run-syncdb 2>&1 | grep -E "(OK|Apply|No migration)" || true
success "資料庫已更新"

# ── 6. 靜態檔案 ────────────────────────────────────────────────────────────────
info "更新靜態檔案..."
python manage.py collectstatic --noinput
success "靜態檔案已更新"

deactivate

# ── 7. 重新啟動 ────────────────────────────────────────────────────────────────
info "重新啟動服務..."
bash "${APP_DIR}/start.sh"

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║   更新完成！v${PREV_VERSION} → v${NEW_VERSION}   ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
