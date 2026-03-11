from django.db import models


class Device(models.Model):
    DEVICE_TYPE_CHOICES = [
        ("cisco_ios", "Cisco IOS"),
        ("cisco_nxos", "Cisco NX-OS"),
        ("juniper_junos", "Juniper JunOS"),
        ("linux", "Linux Server"),
        ("generic", "Generic"),
    ]

    STATUS_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
        ("warning", "Warning"),
        ("unknown", "Unknown"),
    ]

    name = models.CharField(max_length=100, verbose_name="設備名稱")
    ip_address = models.GenericIPAddressField(verbose_name="IP 位址")
    device_type = models.CharField(
        max_length=50, choices=DEVICE_TYPE_CHOICES, default="cisco_ios", verbose_name="設備類型"
    )
    ssh_username = models.CharField(max_length=100, blank=True, verbose_name="SSH 帳號")
    ssh_password = models.CharField(max_length=100, blank=True, verbose_name="SSH 密碼")
    ssh_port = models.IntegerField(default=22, verbose_name="SSH Port")
    description = models.TextField(blank=True, verbose_name="描述")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="unknown", verbose_name="狀態"
    )
    last_checked = models.DateTimeField(null=True, blank=True, verbose_name="最後檢查時間")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="建立時間")

    class Meta:
        verbose_name = "設備"
        verbose_name_plural = "設備列表"

    def __str__(self):
        return f"{self.name} ({self.ip_address})"


class DeviceLog(models.Model):
    LOG_LEVEL_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
        ("success", "Success"),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="logs")
    level = models.CharField(max_length=20, choices=LOG_LEVEL_CHOICES, default="info")
    message = models.TextField(verbose_name="訊息")
    raw_output = models.TextField(blank=True, verbose_name="原始輸出")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="時間")

    class Meta:
        verbose_name = "設備 Log"
        verbose_name_plural = "設備 Log 列表"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.level}] {self.device.name} - {self.created_at}"
