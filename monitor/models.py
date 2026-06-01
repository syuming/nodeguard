from django.db import models
from django.contrib.auth.models import User


class Company(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="公司名稱")
    description = models.TextField(blank=True, verbose_name="描述")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "公司"
        verbose_name_plural = "公司列表"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("admin", "系統管理者"),
        ("company_manager", "公司管理者"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default="company_manager", verbose_name="角色")
    company = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", verbose_name="所屬公司"
    )

    class Meta:
        verbose_name = "使用者設定"
        verbose_name_plural = "使用者設定列表"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == "admin"


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

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="devices",
        verbose_name="所屬公司", null=True, blank=True
    )
    name = models.CharField(max_length=100, verbose_name="設備名稱")
    ip_address = models.GenericIPAddressField(verbose_name="IP 位址")
    device_type = models.CharField(
        max_length=50, choices=DEVICE_TYPE_CHOICES, default="cisco_ios", verbose_name="設備類型"
    )
    customer_name    = models.CharField(max_length=100, blank=True, verbose_name="客戶名稱")
    customer_id      = models.CharField(max_length=50, blank=True, verbose_name="客戶編號")
    circuit_number   = models.CharField(max_length=100, blank=True, verbose_name="電路編號")
    customer_address = models.TextField(blank=True, verbose_name="客戶地址")
    description      = models.TextField(blank=True, verbose_name="描述")
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


class EmailConfig(models.Model):
    METHOD_CHOICES = [
        ("none",  "無驗證（直接轉發）"),
        ("tls",   "帳號密碼 + STARTTLS"),
        ("ssl",   "帳號密碼 + SSL"),
        ("plain", "帳號密碼（無加密）"),
    ]

    method     = models.CharField(max_length=10, choices=METHOD_CHOICES, default="tls", verbose_name="驗證方式")
    host       = models.CharField(max_length=200, default="smtp.gmail.com", verbose_name="SMTP 主機")
    port       = models.IntegerField(default=587, verbose_name="Port")
    username   = models.CharField(max_length=200, blank=True, verbose_name="帳號")
    password   = models.CharField(max_length=200, blank=True, verbose_name="密碼")
    from_email = models.CharField(max_length=200, blank=True, verbose_name="寄件者 Email")
    enabled    = models.BooleanField(default=False, verbose_name="啟用 Email 功能")

    class Meta:
        verbose_name = "Email 設定"

    def __str__(self):
        return f"Email 設定（{self.get_method_display()}）"

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class MonitorCheck(models.Model):
    CHECK_TYPE_CHOICES = [
        ("ping", "Ping"),
        ("tcp",  "TCP Port"),
        ("ssh",  "SSH"),
        ("http", "HTTP"),
        ("snmp", "SNMP"),
    ]

    STATUS_CHOICES = [
        ("online",  "Online"),
        ("offline", "Offline"),
        ("warning", "Warning"),
        ("unknown", "Unknown"),
    ]

    device     = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="checks", verbose_name="設備")
    check_type = models.CharField(max_length=10, choices=CHECK_TYPE_CHOICES, verbose_name="監控類型")
    # TCP / SSH
    port         = models.IntegerField(null=True, blank=True, verbose_name="Port")
    # SSH
    ssh_username = models.CharField(max_length=100, blank=True, verbose_name="SSH 帳號")
    ssh_password = models.CharField(max_length=100, blank=True, verbose_name="SSH 密碼")
    # HTTP
    url                  = models.CharField(max_length=500, blank=True, verbose_name="URL")
    expected_status_code = models.IntegerField(default=200, verbose_name="預期 HTTP 狀態碼")
    # SNMP
    snmp_community = models.CharField(max_length=100, blank=True, default="public", verbose_name="Community String")
    snmp_version   = models.IntegerField(default=2, verbose_name="SNMP 版本")
    snmp_port      = models.IntegerField(default=161, verbose_name="SNMP Port")
    snmp_oid       = models.CharField(max_length=200, blank=True, verbose_name="監控 OID")
    snmp_label     = models.CharField(max_length=200, blank=True, verbose_name="Interface 名稱")
    # Common
    interval = models.IntegerField(default=60, verbose_name="檢查間隔（秒）")
    enabled  = models.BooleanField(default=True, verbose_name="啟用")
    # Last result
    last_status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default="unknown", verbose_name="最後狀態")
    last_checked = models.DateTimeField(null=True, blank=True, verbose_name="最後檢查時間")
    last_message = models.TextField(blank=True, verbose_name="最後訊息")

    class Meta:
        verbose_name = "監控項目"
        verbose_name_plural = "監控項目列表"

    def __str__(self):
        return f"{self.device.name} - {self.get_check_type_display()}"


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


class DowntimeRecord(models.Model):
    device       = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="downtimes")
    started_at   = models.DateTimeField(verbose_name="斷線時間")
    recovered_at = models.DateTimeField(null=True, blank=True, verbose_name="恢復時間")
    duration_seconds = models.IntegerField(null=True, blank=True, verbose_name="持續秒數")

    class Meta:
        verbose_name = "斷線記錄"
        verbose_name_plural = "斷線記錄列表"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.device.name} 斷線 {self.started_at}"

    @property
    def duration_display(self):
        if self.duration_seconds is None:
            return "尚未恢復"
        h, r = divmod(self.duration_seconds, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"
