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
    Returns status string and saves logs.
    """
    from monitor.models import DeviceLog

    logs = []
    is_alive, avg_ms = ping_device(device.ip_address)

    if not is_alive:
        DeviceLog.objects.create(
            device=device,
            level="error",
            message=f"Ping 失敗 - {device.ip_address} 無法連線",
        )
        device.status = "offline"
        device.last_checked = timezone.now()
        device.save(update_fields=["status", "last_checked"])
        return "offline"

    ping_msg = f"Ping 成功 - 回應時間 {avg_ms:.1f} ms" if avg_ms else "Ping 成功"
    DeviceLog.objects.create(device=device, level="success", message=ping_msg)

    port_open = check_port(device.ip_address, device.ssh_port)
    if not port_open:
        DeviceLog.objects.create(
            device=device,
            level="warning",
            message=f"Port {device.ssh_port} 關閉，跳過 SSH 連線",
        )
        device.status = "warning"
        device.last_checked = timezone.now()
        device.save(update_fields=["status", "last_checked"])
        return "warning"

    if device.ssh_username:
        success, info = get_ssh_info(device)
        if success:
            for key, val in info.items():
                DeviceLog.objects.create(
                    device=device,
                    level="info",
                    message=f"SSH [{key}]",
                    raw_output=val,
                )
            device.status = "online"
        else:
            DeviceLog.objects.create(
                device=device,
                level="warning",
                message=f"SSH 連線失敗: {info}",
            )
            device.status = "warning"
    else:
        device.status = "online"

    device.last_checked = timezone.now()
    device.save(update_fields=["status", "last_checked"])
    return device.status
