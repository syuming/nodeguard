# NodeGuard - 網路設備監控系統

基於 Django 開發的網路設備監控平台，支援 Cisco、Juniper、Linux 設備的 Ping / TCP / SSH / HTTP 狀態監控，並提供多公司權限管理。

---

## 系統需求

- Python 3.10+
- git

---

## ⚡ 一鍵安裝

適用 Ubuntu 20.04 / 22.04 / 24.04，安裝至 `~/nodeguard`（安裝 traceroute 與 logrotate 設定時需要 sudo）。

**前置需求（若尚未安裝）：**

```bash
sudo apt-get install -y python3 python3-venv git
```

**執行安裝：**

```bash
curl -fsSL https://raw.githubusercontent.com/syuming/nodeguard/main/install.sh | bash
```

安裝完成後會顯示連線資訊：

```
╔══════════════════════════════════════════════╗
║          安裝完成！                          ║
╠══════════════════════════════════════════════╣
║  網址：    http://<伺服器IP>:8000
║  帳號：    admin
║  密碼：    （安裝時隨機產生，顯示於畫面上）
║  ⚠ 請妥善保存密碼，或登入後自行修改！
╚══════════════════════════════════════════════╝
```

---

## 常用指令

| 動作 | 指令 |
|------|------|
| 啟動 | `bash ~/nodeguard/start.sh` |
| 停止 | `bash ~/nodeguard/stop.sh` |
| 狀態 | `bash ~/nodeguard/status.sh` |
| 更新 | `bash ~/nodeguard/update.sh` |
| 移除 | `bash ~/nodeguard/uninstall.sh` |

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
| **SNMP** | OID 查詢（如 Interface 狀態），支援自動掃描 |

支援設備：`Cisco IOS`、`Cisco NX-OS`、`Juniper JunOS`、`Linux`、`Generic`

**監控間隔**：持續監控的全域間隔可於首頁設定（1–3600 秒，預設 3 秒，admin 限定）。
各監控項目的間隔留空即跟隨全域間隔，填寫數字則以自訂秒數獨立排程。

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
nodeguard/           # Django 設定、wsgi
monitor/
  models.py          # Company、Device、MonitorCheck、DeviceLog、DowntimeRecord
  views/             # 依功能域拆分：auth、devices、companies、checks、status_api、system 等
  monitoring.py      # 持續監控背景執行緒
  fields.py          # 憑證加密欄位（Fernet）
  utils.py           # Ping / TCP / SSH / HTTP / SNMP 監控邏輯
  forms.py           # 表單定義
  urls.py            # 路由設定
  tests.py           # 自動化測試
  templates/monitor/ # HTML 範本
static/              # Bootstrap 5、Bootstrap Icons、custom.css
install.sh           # 一鍵安裝
start.sh / stop.sh / status.sh / update.sh
```
