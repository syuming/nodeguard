import subprocess
import socket
import smtplib
import urllib.request
from email.mime.text import MIMEText
from email.header import Header
from django.utils import timezone


def _snmp_get(ip, community, oids, port=161, timeout=3):
    """GET one or more OIDs via SNMP v2c. Returns dict {oid: value} or raises."""
    from functools import partial
    from puresnmp import Client, V2C
    from puresnmp.transport import send_udp
    sender = partial(send_udp, timeout=timeout, retries=1)
    client = Client(ip, V2C(community), port=port, sender=sender)
    results = {}
    for oid in oids:
        try:
            results[oid] = client.get(oid)
        except Exception:
            results[oid] = None
    return results


def _format_uptime(centiseconds):
    """Convert SNMP sysUpTime (centiseconds) to human-readable string."""
    try:
        val = centiseconds.pythonize() if hasattr(centiseconds, "pythonize") else int(centiseconds)
        secs = val // 100
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except Exception:
        return str(centiseconds)


def snmp_scan_interfaces(ip, community="public", port=161, timeout=5):
    """
    Walk IF-MIB and return list of interfaces:
    [{"index": 1, "descr": "eth0", "status": "up", "speed_mbps": 1000}, ...]
    Raises on connection failure.
    """
    import asyncio
    from functools import partial
    from puresnmp import Client, V2C
    from puresnmp.transport import send_udp
    from x690.types import ObjectIdentifier

    OID_DESCR  = ObjectIdentifier("1.3.6.1.2.1.2.2.1.2")   # ifDescr
    OID_STATUS = ObjectIdentifier("1.3.6.1.2.1.2.2.1.8")   # ifOperStatus
    OID_SPEED  = ObjectIdentifier("1.3.6.1.2.1.2.2.1.5")   # ifSpeed (bps)

    STATUS_MAP = {1: "up", 2: "down", 3: "testing", 4: "unknown",
                  5: "dormant", 6: "notPresent", 7: "lowerLayerDown"}

    async def _walk():
        sender = partial(send_udp, timeout=timeout, retries=1)
        client = Client(ip, V2C(community), port=port, sender=sender)

        descr_map, status_map, speed_map = {}, {}, {}

        async for vb in client.walk(OID_DESCR):
            idx = int(str(vb.oid).split(".")[-1])
            descr_map[idx] = str(vb.value)

        async for vb in client.walk(OID_STATUS):
            idx = int(str(vb.oid).split(".")[-1])
            status_map[idx] = STATUS_MAP.get(vb.value.pythonize(), str(vb.value))

        async for vb in client.walk(OID_SPEED):
            idx = int(str(vb.oid).split(".")[-1])
            try:
                speed_mbps = vb.value.pythonize() // 1_000_000
            except Exception:
                speed_mbps = 0
            speed_map[idx] = speed_mbps

        interfaces = []
        for idx in sorted(descr_map):
            interfaces.append({
                "index":      idx,
                "descr":      descr_map.get(idx, f"if{idx}"),
                "status":     status_map.get(idx, "unknown"),
                "speed_mbps": speed_map.get(idx, 0),
            })
        return interfaces

    return asyncio.run(_walk())


def send_email_with_config(subject, body, to_list):
    """
    Send email using the EmailConfig stored in the database.
    Raises Exception on failure.
    """
    from monitor.models import EmailConfig
    cfg = EmailConfig.get_config()
    if not cfg.enabled:
        raise Exception("Email 功能未啟用，請先至「Email 設定」頁面開啟")

    from_addr = cfg.from_email or cfg.username
    if not from_addr:
        raise Exception("未設定寄件者 Email")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = from_addr
    msg["To"]      = ", ".join(to_list)

    if cfg.method == "ssl":
        smtp = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=10)
    else:
        smtp = smtplib.SMTP(cfg.host, cfg.port, timeout=10)
        if cfg.method == "tls":
            smtp.starttls()

    if cfg.method in ("tls", "ssl", "plain") and cfg.username:
        smtp.login(cfg.username, cfg.password)

    try:
        smtp.sendmail(from_addr, to_list, msg.as_string())
    finally:
        smtp.quit()


def ping_device(ip_address, count=3):
    """Ping a device and return (is_alive, avg_ms)"""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", ip_address],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "avg" in line or "rtt" in line:
                    parts = line.split("/")
                    if len(parts) >= 5:
                        avg_ms = float(parts[4])
                        return True, avg_ms
            return True, None
        return False, None
    except Exception:
        return False, None


def check_port(ip_address, port, timeout=3):
    """Check if a TCP port is open"""
    try:
        with socket.create_connection((ip_address, port), timeout=timeout):
            return True
    except Exception:
        return False


def _run_ssh_check(check):
    """
    Connect via SSH using MonitorCheck credentials and run device-specific commands.
    Returns (ok: bool, output: str)
    """
    try:
        from netmiko import ConnectHandler
        device_type = check.device.device_type
        conn_params = {
            "device_type": device_type,
            "host": check.device.ip_address,
            "username": check.ssh_username,
            "password": check.ssh_password,
            "port": check.port or 22,
            "timeout": 10,
            "conn_timeout": 10,
        }
        with ConnectHandler(**conn_params) as conn:
            lines = []
            if device_type in ("cisco_ios", "cisco_nxos"):
                lines.append(conn.send_command("show ip interface brief"))
            elif device_type == "juniper_junos":
                lines.append(conn.send_command("show interfaces terse"))
            elif device_type == "linux":
                lines.append(conn.send_command("uptime"))
            else:
                lines.append(conn.send_command("show version"))
            return True, "\n".join(lines)
    except Exception as e:
        return False, str(e)


def run_check(check):
    """
    Run a single MonitorCheck. Updates check.last_status, last_checked, last_message.
    Returns status string: "online" | "offline" | "warning" | "unknown"
    """
    now = timezone.now()
    ip = check.device.ip_address

    if check.check_type == "ping":
        alive, avg_ms = ping_device(ip)
        if alive:
            msg = f"Ping 成功 - 回應時間 {avg_ms:.1f} ms" if avg_ms else "Ping 成功"
            status = "online"
        else:
            msg = f"Ping 失敗 - {ip} 無法連線"
            status = "offline"

    elif check.check_type == "tcp":
        port = check.port or 80
        ok = check_port(ip, port)
        if ok:
            msg = f"TCP Port {port} 開放"
            status = "online"
        else:
            msg = f"TCP Port {port} 無法連線"
            status = "offline"

    elif check.check_type == "ssh":
        port = check.port or 22
        # First check port reachability
        if not check_port(ip, port):
            msg = f"SSH Port {port} 無法連線"
            status = "offline"
        elif check.ssh_username:
            ok, output = _run_ssh_check(check)
            if ok:
                msg = f"SSH 連線成功"
                status = "online"
            else:
                msg = f"SSH 連線失敗: {output}"
                status = "warning"
        else:
            msg = f"SSH Port {port} 開放（未設定帳號，跳過登入）"
            status = "online"

    elif check.check_type == "http":
        url = check.url or f"http://{ip}/"
        expected = check.expected_status_code or 200
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NodeGuard/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
            if code == expected:
                msg = f"HTTP {code} - {url}"
                status = "online"
            else:
                msg = f"HTTP {code}（期望 {expected}）- {url}"
                status = "warning"
        except Exception as e:
            msg = f"HTTP 失敗: {e}"
            status = "offline"

    elif check.check_type == "snmp":
        community = check.snmp_community or "public"
        port      = check.snmp_port or 161
        try:
            data = _snmp_get(ip, community, [
                "1.3.6.1.2.1.1.1.0",  # sysDescr
                "1.3.6.1.2.1.1.3.0",  # sysUpTime
                "1.3.6.1.2.1.1.5.0",  # sysName
            ], port=port)
            uptime_str = _format_uptime(data.get("1.3.6.1.2.1.1.3.0")) if data.get("1.3.6.1.2.1.1.3.0") else "-"
            descr = str(data.get("1.3.6.1.2.1.1.1.0") or "")[:60]
            msg = f"SNMP OK - Uptime: {uptime_str} | {descr}"
            status = "online"
        except Exception as e:
            msg = f"SNMP 失敗: {e}"
            status = "offline"

    else:
        msg = f"未知檢查類型: {check.check_type}"
        status = "unknown"

    check.last_status  = status
    check.last_checked = now
    check.last_message = msg
    check.save(update_fields=["last_status", "last_checked", "last_message"])
    return status, msg


# Status severity: higher = worse
_SEVERITY = {"online": 0, "warning": 1, "offline": 2, "unknown": -1}


def check_device(device):
    """
    Run all enabled MonitorChecks for a device.
    Computes overall device status as the worst check result.
    Saves DeviceLog entries and tracks DowntimeRecord.
    """
    from monitor.models import DeviceLog, DowntimeRecord

    prev_status = device.status
    now = timezone.now()

    checks = list(device.checks.filter(enabled=True))

    if not checks:
        # No checks configured — leave status as-is, just update last_checked
        device.last_checked = now
        device.save(update_fields=["last_checked"])
        return device.status

    worst_status = "online"
    for check in checks:
        prev_check_status = check.last_status
        status, msg = run_check(check)
        label = check.get_check_type_display()
        # 只在狀態改變（或第一次檢查）時寫 LOG，避免持續 up/down 產生大量重複記錄
        if status != prev_check_status or prev_check_status == "unknown":
            level = "success" if status == "online" else ("warning" if status == "warning" else "error")
            DeviceLog.objects.create(
                device=device,
                level=level,
                message=f"[{label}] {msg}",
            )
        if _SEVERITY.get(status, -1) > _SEVERITY.get(worst_status, -1):
            worst_status = status

    new_status = worst_status

    # ── 斷線記錄追蹤 ────────────────────────────────────────────────────────
    if new_status == "offline" and prev_status != "offline":
        DowntimeRecord.objects.create(device=device, started_at=now)
    elif new_status != "offline" and prev_status == "offline":
        open_record = DowntimeRecord.objects.filter(
            device=device, recovered_at__isnull=True
        ).order_by("-started_at").first()
        if open_record:
            duration = int((now - open_record.started_at).total_seconds())
            open_record.recovered_at = now
            open_record.duration_seconds = duration
            open_record.save(update_fields=["recovered_at", "duration_seconds"])

    device.status = new_status
    device.last_checked = now
    device.save(update_fields=["status", "last_checked"])
    return new_status
