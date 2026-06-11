from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from .models import Company, Device, EmailConfig, MonitorCheck, UserProfile


class ApiCheckIpRBACTests(TestCase):
    """api_check_ip 必須遵守多公司 RBAC：非 admin 只能查詢自己公司的設備。"""

    def setUp(self):
        self.company_a = Company.objects.create(name="公司A")
        self.company_b = Company.objects.create(name="公司B")

        self.device_b = Device.objects.create(
            company=self.company_b, name="B公司核心交換器", ip_address="10.0.0.1"
        )

        # A 公司的一般使用者
        self.user_a = User.objects.create_user(username="user_a", password="test-pass-123")
        UserProfile.objects.create(user=self.user_a, role="company_manager", company=self.company_a)

        # 系統管理者
        self.admin = User.objects.create_user(username="admin_u", password="test-pass-123")
        UserProfile.objects.create(user=self.admin, role="admin")

        self.url = reverse("api_check_ip")

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url, {"ip": "10.0.0.1", "company_id": self.company_b.pk})
        self.assertEqual(resp.status_code, 302)

    def test_non_admin_cannot_probe_other_company(self):
        """A 公司使用者查 B 公司的 IP，不可洩漏設備存在與名稱。"""
        self.client.login(username="user_a", password="test-pass-123")
        resp = self.client.get(self.url, {"ip": "10.0.0.1", "company_id": self.company_b.pk})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["exists"])
        self.assertNotIn("device_name", data)

    def test_non_admin_can_check_own_company(self):
        device_a = Device.objects.create(
            company=self.company_a, name="A公司路由器", ip_address="10.0.0.2"
        )
        self.client.login(username="user_a", password="test-pass-123")
        resp = self.client.get(self.url, {"ip": "10.0.0.2", "company_id": self.company_a.pk})
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["device_name"], device_a.name)

    def test_admin_can_check_any_company(self):
        self.client.login(username="admin_u", password="test-pass-123")
        resp = self.client.get(self.url, {"ip": "10.0.0.1", "company_id": self.company_b.pk})
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["device_name"], self.device_b.name)


class EncryptedFieldTests(TestCase):
    """憑證欄位必須加密落盤：DB 內是密文，ORM 讀出是明文。"""

    def setUp(self):
        self.company = Company.objects.create(name="加密測試公司")
        self.device = Device.objects.create(
            company=self.company, name="測試設備", ip_address="10.9.9.9"
        )

    def _raw_db_value(self, table, column, pk):
        with connection.cursor() as cur:
            cur.execute(f"SELECT {column} FROM {table} WHERE id = %s", [pk])
            return cur.fetchone()[0]

    def test_ssh_password_roundtrip_and_encrypted_at_rest(self):
        check = MonitorCheck.objects.create(
            device=self.device, check_type="ssh", port=22,
            ssh_username="ops", ssh_password="plain-text-pw",
        )
        # ORM 讀出必須是明文
        reloaded = MonitorCheck.objects.get(pk=check.pk)
        self.assertEqual(reloaded.ssh_password, "plain-text-pw")
        # DB 原始值必須是 Fernet 密文，不可含明文
        raw = self._raw_db_value("monitor_monitorcheck", "ssh_password", check.pk)
        self.assertNotEqual(raw, "plain-text-pw")
        self.assertNotIn("plain-text-pw", raw)
        self.assertTrue(raw.startswith("gAAAA"))

    def test_snmp_community_encrypted_at_rest(self):
        check = MonitorCheck.objects.create(
            device=self.device, check_type="snmp", snmp_community="secret-community",
        )
        reloaded = MonitorCheck.objects.get(pk=check.pk)
        self.assertEqual(reloaded.snmp_community, "secret-community")
        raw = self._raw_db_value("monitor_monitorcheck", "snmp_community", check.pk)
        self.assertNotIn("secret-community", raw)

    def test_email_password_encrypted_at_rest(self):
        cfg = EmailConfig.get_config()
        cfg.password = "smtp-app-password"
        cfg.save()
        reloaded = EmailConfig.objects.get(pk=cfg.pk)
        self.assertEqual(reloaded.password, "smtp-app-password")
        raw = self._raw_db_value("monitor_emailconfig", "password", cfg.pk)
        self.assertNotIn("smtp-app-password", raw)

    def test_blank_value_stays_blank(self):
        check = MonitorCheck.objects.create(
            device=self.device, check_type="ping", ssh_password="",
        )
        raw = self._raw_db_value("monitor_monitorcheck", "ssh_password", check.pk)
        self.assertEqual(raw, "")

    def test_legacy_plaintext_still_readable(self):
        """加密上線前寫入的舊明文資料，讀取時必須原樣回傳而非報錯。"""
        check = MonitorCheck.objects.create(
            device=self.device, check_type="ssh", ssh_password="x",
        )
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE monitor_monitorcheck SET ssh_password = %s WHERE id = %s",
                ["legacy-plain", check.pk],
            )
        reloaded = MonitorCheck.objects.get(pk=check.pk)
        self.assertEqual(reloaded.ssh_password, "legacy-plain")
