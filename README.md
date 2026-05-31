# NetMonitor - 網路設備監控系統

基於 Django 開發的網路設備監控平台，支援 Cisco、Juniper、Linux 設備的 Ping / TCP / SSH / HTTP 狀態監控，並提供多公司權限管理。

---

## 系統需求

- Python 3.10+
- git
- curl

---

## ⚡ 一鍵安裝

適用 Ubuntu 20.04 / 22.04 / 24.04，**不需要 sudo**，安裝至 `~/netmonitor`。

**前置需求（若尚未安裝）：**

```bash
sudo apt-get install -y python3 python3-venv git curl
```

**步驟 1：取得 GitHub Token**

前往 GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)，建立時勾選 `repo` 權限。

```bash
export GH_TOKEN="ghp_你的Token"
```

**步驟 2：執行安裝**

```bash
curl -fsSL -H "Authorization: token $GH_TOKEN" \
  https://raw.githubusercontent.com/syuming/monitor/main/install.sh \
  | GH_TOKEN=$GH_TOKEN bash
```

安裝完成後會顯示連線資訊：

```
╔══════════════════════════════════════════════╗
║          安裝完成！                          ║
╠══════════════════════════════════════════════╣
║  網址：    http://<伺服器IP>:8000
║  帳號：    admin
║  密碼：    Netmon@2026
║  ⚠ 請登入後立即至「個人資料」修改密碼！
╚══════════════════════════════════════════════╝
```

---

## 常用指令

| 動作 | 指令 |
|------|------|
| 啟動 | `bash ~/netmonitor/start.sh` |
| 停止 | `bash ~/netmonitor/stop.sh` |
| 狀態 | `bash ~/netmonitor/status.sh` |
| 更新 | `bash ~/netmonitor/update.sh` |
| 移除 | `bash ~/netmonitor/uninstall.sh` |

---

## 帳號權限

| 角色 | 說明 |
|------|------|
| **系統管理者** | 可查看、管理所有公司的所有設備 |
| **公司管理者** | 只能查看與管理自己公司的設備 |

---

## 監控類型

| 類型 | 說明 |
|------|------|
| **Ping** | ICMP 存活確認 |
| **TCP** | 指定 Port 連線測試 |
| **SSH** | SSH 登入並執行 show 指令 |
| **HTTP** | HTTP/HTTPS 狀態碼確認 |

支援設備：`Cisco IOS`、`Cisco NX-OS`、`Juniper JunOS`、`Linux`、`Generic`

---

## 狀態說明

| 狀態 | 說明 |
|------|------|
| 🟢 Online | 所有監控項目正常 |
| 🟡 Warning | 部分監控項目異常 |
| 🔴 Offline | 主要監控項目失敗 |
| ⚪ Unknown | 尚未執行過檢查 |

---

## 專案結構

```
netmonitor/          # Django 設定、wsgi
monitor/
  models.py          # Company、Device、MonitorCheck、DeviceLog、DowntimeRecord
  views.py           # Dashboard、設備管理、使用者管理、API
  utils.py           # Ping / TCP / SSH / HTTP 監控邏輯
  forms.py           # 表單定義
  urls.py            # 路由設定
  templates/monitor/ # HTML 範本
static/              # Bootstrap 5、Bootstrap Icons、custom.css
install.sh           # 一鍵安裝
start.sh / stop.sh / status.sh / update.sh
```
