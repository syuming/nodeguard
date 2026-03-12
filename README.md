# NetMonitor - 網路設備監控系統

基於 Django 開發的網路設備監控平台，支援 Cisco、Juniper、Linux 設備的 Ping / SSH 狀態監控，並提供多公司權限管理。

---

## 系統需求

- Python 3.10+
- pip

---

## ⚡ Ubuntu 一鍵安裝

在 Ubuntu 20.04 / 22.04 / 24.04 上，執行以下指令即可完成全自動安裝：

```bash
curl -fsSL https://raw.githubusercontent.com/syuming/monitor/main/install.sh | sudo bash
```

安裝完成後，終端機會顯示：

```
╔══════════════════════════════════════════════╗
║          安裝完成！                          ║
╠══════════════════════════════════════════════╣
║  網址：  http://<伺服器IP>:8000
║  帳號：  admin
║  密碼：  admin1234
║  ⚠ 請登入後立即修改預設密碼！
╚══════════════════════════════════════════════╝
```

> ✅ 腳本會自動完成：安裝系統套件、下載程式碼、建立虛擬環境、初始化資料庫、建立管理員帳號、設定 systemd 開機自動啟動。

---

## 安裝步驟

### 1. 取得程式碼

```bash
git clone <repo-url>
cd monitor
```

### 2. 安裝相依套件

```bash
pip install django netmiko paramiko
```

> 若系統環境有衝突，加上 `--break-system-packages`：
> ```bash
> pip install django netmiko paramiko --break-system-packages --ignore-installed pyyaml
> ```

### 3. 初始化資料庫

```bash
python manage.py migrate
```

### 4. 建立管理者帳號

```bash
python manage.py createsuperuser
```

### 5. 收集靜態檔案

```bash
python manage.py collectstatic --noinput
```

---

## 正式部署（Gunicorn + Nginx + Supervisor）

開發測試用 `runserver` 即可，**正式上線請用以下方式**。

### 安裝套件

```bash
pip install gunicorn --break-system-packages
apt-get install -y nginx supervisor
```

### Supervisor 設定

建立 `/etc/supervisor/conf.d/netmonitor.conf`：

```ini
[program:netmonitor]
command=/usr/local/bin/gunicorn --workers 3 --bind unix:/run/netmonitor.sock --access-logfile /var/log/netmonitor/access.log --error-logfile /var/log/netmonitor/error.log netmonitor.wsgi:application
directory=/home/user/test1
user=root
autostart=true
autorestart=true
redirect_stderr=true
stopasgroup=true
killasgroup=true

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
redirect_stderr=true
```

### Nginx 設定

建立 `/etc/nginx/sites-available/netmonitor`：

```nginx
server {
    listen 80;
    server_name _;

    location /static/ {
        alias /home/user/test1/staticfiles/;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/netmonitor.sock;
    }
}
```

啟用設定：

```bash
ln -sf /etc/nginx/sites-available/netmonitor /etc/nginx/sites-enabled/netmonitor
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/log/netmonitor
```

### 啟動服務

```bash
supervisord -c /etc/supervisor/supervisord.conf
```

確認狀態：

```bash
supervisorctl status
```

### 常用管理指令

```bash
supervisorctl status          # 查看所有服務狀態
supervisorctl restart all     # 重啟所有服務
supervisorctl restart netmonitor  # 只重啟 Django
supervisorctl stop all        # 停止所有服務
tail -f /var/log/netmonitor/error.log   # 查看錯誤 log
```

開啟瀏覽器前往 `http://<伺服器IP>/`

---

## 帳號權限說明

| 角色 | 說明 |
|------|------|
| **系統管理者** | 可查看、管理所有公司的所有設備 |
| **公司管理者** | 只能查看與管理自己公司的設備 |

使用者角色與公司的對應，請至 `/admin/` 後台的「使用者設定」中設定。

---

## 後台管理

```
http://localhost:8000/admin/
```

在後台可以：
- 新增 / 管理公司（Company）
- 設定使用者角色與所屬公司（UserProfile）
- 管理設備與 Log

---

## 設備監控流程

每次執行「立即檢查」或「全部檢查」時，系統依序：

1. **Ping** — 確認設備是否存活
2. **Port Check** — 確認 SSH Port 是否開啟
3. **SSH 連線**（需填入帳號密碼）— 擷取設備資訊

| 結果 | 狀態 |
|------|------|
| Ping 失敗 | Offline |
| Ping 成功、Port 關閉或 SSH 失敗 | Warning |
| SSH 成功 | Online |

支援設備類型：`Cisco IOS`、`Cisco NX-OS`、`Juniper JunOS`、`Linux`、`Generic`

---

## 專案結構

```
manage.py
netmonitor/          # Django 設定
monitor/
  models.py          # Company, UserProfile, Device, DeviceLog
  views.py           # Dashboard, 登入, CRUD, API
  utils.py           # Ping / Port / SSH 監控邏輯
  forms.py           # DeviceForm
  urls.py            # 路由設定
  admin.py           # 後台設定
  templates/
    monitor/
      base.html
      login.html
      dashboard.html
      device_detail.html
      device_form.html
```
