import subprocess
import socket
from datetime import datetime
from django.utils import timezone


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


def get_ssh_info(device):
    """Connect via SSH and retrieve basic device info"""
    try:
        from netmiko import ConnectHandler
        conn_params = {
            "device_type": device.device_type,
            "host": device.ip_address,
            "username": device.ssh_username,
            "password": device.ssh_password,
            "port": device.ssh_port,
            "timeout": 10,
            "conn_timeout": 10,
        }
        with ConnectHandler(**conn_params) as conn:
            output = {}
            if device.device_type in ("cisco_ios", "cisco_nxos"):
                output["interfaces"] = conn.send_command("show ip interface brief")
                output["version"] = conn.send_command("show version")
                output["cpu"] = conn.send_command("show processes cpu sorted | head 10")
            elif device.device_type == "juniper_junos":
                output["interfaces"] = conn.send_command("show interfaces terse")
                output["version"] = conn.send_command("show version")
            elif device.device_type == "linux":
                output["uptime"] = conn.send_command("uptime")
                output["interfaces"] = conn.send_command("ip addr show")
                output["disk"] = conn.send_command("df -h")
            else:
                output["raw"] = conn.send_command("show version || uname -a || ver")
            return True, output
    except Exception as e:
        return False, str(e)


def check_device(device):
    """
    Run full check on a device: ping -> port -> SSH
    Returns status string, saves logs, and tracks downtime records.
    """
    from monitor.models import DeviceLog, DowntimeRecord

    prev_status = device.status
    now = timezone.now()
    is_alive, avg_ms = ping_device(device.ip_address)

    if not is_alive:
        DeviceLog.objects.create(
            device=device,
            level="error",
            message=f"Ping 失敗 - {device.ip_address} 無法連線",
        )
        new_status = "offline"
    else:
        ping_msg = f"Ping 成功 - 回應時間 {avg_ms:.1f} ms" if avg_ms else "Ping 成功"
        DeviceLog.objects.create(device=device, level="success", message=ping_msg)

        port_open = check_port(device.ip_address, device.ssh_port)
        if not port_open:
            DeviceLog.objects.create(
                device=device,
                level="warning",
                message=f"Port {device.ssh_port} 關閉，跳過 SSH 連線",
            )
            new_status = "warning"
        elif device.ssh_username:
            success, info = get_ssh_info(device)
            if success:
                for key, val in info.items():
                    DeviceLog.objects.create(
                        device=device,
                        level="info",
                        message=f"SSH [{key}]",
                        raw_output=val,
                    )
                new_status = "online"
            else:
                DeviceLog.objects.create(
                    device=device,
                    level="warning",
                    message=f"SSH 連線失敗: {info}",
                )
                new_status = "warning"
        else:
            new_status = "online"

    # ── 斷線記錄追蹤 ────────────────────────────────────────────────────────
    if new_status == "offline" and prev_status != "offline":
        # 設備剛斷線：開一筆新記錄
        DowntimeRecord.objects.create(device=device, started_at=now)
    elif new_status != "offline" and prev_status == "offline":
        # 設備剛恢復：關閉最近一筆未結束的斷線記錄
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
