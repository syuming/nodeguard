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


class ViewSmokeTests(TestCase):
    """重構 views 的回歸安全網：覆蓋主要頁面與 API 的權限和回應。"""

    def setUp(self):
        self.company_a = Company.objects.create(name="冒煙A")
        self.company_b = Company.objects.create(name="冒煙B")
        self.device_a = Device.objects.create(
            company=self.company_a, name="設備A", ip_address="172.16.0.1"
        )
        self.device_b = Device.objects.create(
            company=self.company_b, name="設備B", ip_address="172.16.0.2"
        )
        self.user_a = User.objects.create_user(username="smoke_a", password="test-pass-123")
        UserProfile.objects.create(user=self.user_a, role="company_manager", company=self.company_a)
        self.admin = User.objects.create_user(username="smoke_admin", password="test-pass-123")
        UserProfile.objects.create(user=self.admin, role="admin")

    def test_login_page_renders(self):
        resp = self.client.get("/login/")
        self.assertEqual(resp.status_code, 200)

    def test_login_success_redirects(self):
        resp = self.client.post("/login/", {"username": "smoke_a", "password": "test-pass-123"})
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_requires_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_renders_for_admin(self):
        self.client.login(username="smoke_admin", password="test-pass-123")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_device_detail_rbac(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        ok = self.client.get(f"/device/{self.device_a.pk}/")
        self.assertEqual(ok.status_code, 200)
        denied = self.client.get(f"/device/{self.device_b.pk}/")
        self.assertEqual(denied.status_code, 404)

    def test_api_device_status_scoped_to_company(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        resp = self.client.get("/api/status/")
        names = [d["name"] for d in resp.json()["devices"]]
        self.assertIn("設備A", names)
        self.assertNotIn("設備B", names)

    def test_api_monitor_status_returns_state(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        resp = self.client.get("/api/monitor/status/")
        data = resp.json()
        self.assertIn("monitoring", data)
        self.assertIn("interval", data)

    def test_company_list_admin_only(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        self.assertEqual(self.client.get("/company/").status_code, 404)
        self.client.login(username="smoke_admin", password="test-pass-123")
        self.assertEqual(self.client.get("/company/").status_code, 200)

    def test_orphan_devices_admin_only(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        self.assertEqual(self.client.get("/device/orphans/").status_code, 404)
        self.client.login(username="smoke_admin", password="test-pass-123")
        self.assertEqual(self.client.get("/device/orphans/").status_code, 200)

    def test_email_settings_admin_only(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        self.assertEqual(self.client.get("/settings/email/").status_code, 404)
        self.client.login(username="smoke_admin", password="test-pass-123")
        self.assertEqual(self.client.get("/settings/email/").status_code, 200)

    def test_user_list_admin_only(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        self.assertEqual(self.client.get("/users/").status_code, 404)
        self.client.login(username="smoke_admin", password="test-pass-123")
        self.assertEqual(self.client.get("/users/").status_code, 200)

    def test_api_changelog_returns_releases(self):
        self.client.login(username="smoke_a", password="test-pass-123")
        resp = self.client.get("/api/changelog/")
        self.assertIn("releases", resp.json())


class BulkCreateDevicesTests(TestCase):
    """bulk_create_devices：device_bulk_add 與 company_detail 共用的批量建立邏輯。"""

    def setUp(self):
        from monitor.views.bulk import bulk_create_devices
        self.bulk_create = bulk_create_devices
        self.company = Company.objects.create(name="批量測試公司")

    def test_creates_devices_with_ping_check(self):
        post = {"name_1": "dev1", "ip_1": "10.20.0.1", "name_2": "dev2", "ip_2": "10.20.0.2"}
        created, errors, skipped = self.bulk_create(post, self.company, run_initial_check=False)
        self.assertEqual(len(created), 2)
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        for d in created:
            self.assertEqual(d.company, self.company)
            self.assertTrue(d.checks.filter(check_type="ping", enabled=True).exists())

    def test_skips_duplicate_ip(self):
        Device.objects.create(company=self.company, name="既有設備", ip_address="10.20.0.9")
        post = {"name_1": "新設備", "ip_1": "10.20.0.9"}
        created, errors, skipped = self.bulk_create(post, self.company, run_initial_check=False)
        self.assertEqual(created, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["existing_name"], "既有設備")

    def test_partial_row_reports_error(self):
        post = {"name_1": "只有名稱", "ip_1": "", "name_2": "", "ip_2": ""}
        created, errors, skipped = self.bulk_create(post, self.company, run_initial_check=False)
        self.assertEqual(created, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("第 1 筆", errors[0])

    def test_supports_rows_beyond_ten(self):
        post = {f"name_{i}": f"dev{i}" for i in range(1, 16)}
        post.update({f"ip_{i}": f"10.30.0.{i}" for i in range(1, 16)})
        created, errors, skipped = self.bulk_create(post, self.company, run_initial_check=False)
        self.assertEqual(len(created), 15)

    def test_bulk_add_view_still_works(self):
        """端對端：admin 透過 /device/bulk-add/ 批量新增。"""
        admin = User.objects.create_user(username="bulk_admin", password="test-pass-123")
        UserProfile.objects.create(user=admin, role="admin")
        self.client.login(username="bulk_admin", password="test-pass-123")
        resp = self.client.post("/device/bulk-add/", {
            "company": self.company.pk,
            "name_1": "e2e設備", "ip_1": "10.40.0.1",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Device.objects.filter(name="e2e設備", company=self.company).exists())

    def test_company_detail_bulk_add_still_works(self):
        """端對端：admin 在公司頁面批量新增。"""
        admin = User.objects.create_user(username="bulk_admin2", password="test-pass-123")
        UserProfile.objects.create(user=admin, role="admin")
        self.client.login(username="bulk_admin2", password="test-pass-123")
        resp = self.client.post(f"/company/{self.company.pk}/", {
            "name_1": "公司頁設備", "ip_1": "10.40.0.2",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Device.objects.filter(name="公司頁設備", company=self.company).exists())


class MonitorIntervalTests(TestCase):
    """全域監控間隔設定 + 監控項目「跟隨全域 / 自訂」間隔語意。"""

    def setUp(self):
        from monitor.models import MonitorConfig
        self.MonitorConfig = MonitorConfig
        self.company = Company.objects.create(name="間隔測試公司")
        self.device = Device.objects.create(
            company=self.company, name="間隔設備", ip_address="10.50.0.1"
        )
        self.admin = User.objects.create_user(username="iv_admin", password="test-pass-123")
        UserProfile.objects.create(user=self.admin, role="admin")
        self.user = User.objects.create_user(username="iv_user", password="test-pass-123")
        UserProfile.objects.create(user=self.user, role="company_manager", company=self.company)

    def test_default_global_interval_is_3(self):
        self.assertEqual(self.MonitorConfig.get_config().interval, 3)

    def test_admin_can_set_interval(self):
        self.client.login(username="iv_admin", password="test-pass-123")
        resp = self.client.post("/api/monitor/interval/", {"interval": "10"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.MonitorConfig.get_config().interval, 10)
        status = self.client.get("/api/monitor/status/").json()
        self.assertEqual(status["interval"], 10)

    def test_non_admin_cannot_set_interval(self):
        self.client.login(username="iv_user", password="test-pass-123")
        resp = self.client.post("/api/monitor/interval/", {"interval": "10"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.MonitorConfig.get_config().interval, 3)

    def test_invalid_interval_rejected(self):
        self.client.login(username="iv_admin", password="test-pass-123")
        for bad in ("0", "-5", "abc", "9999"):
            resp = self.client.post("/api/monitor/interval/", {"interval": bad})
            self.assertEqual(resp.status_code, 400, f"interval={bad} 應被拒絕")
        self.assertEqual(self.MonitorConfig.get_config().interval, 3)

    def test_check_interval_nullable_means_follow_global(self):
        check = MonitorCheck.objects.create(device=self.device, check_type="ping")
        self.assertIsNone(check.interval)

    def test_only_due_checks_run(self):
        """only_due 模式：跟隨全域的檢查依全域間隔到期，自訂間隔的依自訂值。"""
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from monitor.utils import check_device

        follow = MonitorCheck.objects.create(device=self.device, check_type="ping", interval=None)
        custom = MonitorCheck.objects.create(device=self.device, check_type="ping", interval=3600)

        with patch("monitor.utils.ping_device", return_value=(True, 1.0)) as mock_ping:
            # 第一次：兩個都沒跑過 → 都到期
            check_device(self.device, only_due=True)
            self.assertEqual(mock_ping.call_count, 2)

            # 把 follow 設成超過全域間隔(3s)前、custom 還在 3600s 內
            now = timezone.now()
            MonitorCheck.objects.filter(pk=follow.pk).update(last_checked=now - timedelta(seconds=5))
            MonitorCheck.objects.filter(pk=custom.pk).update(last_checked=now - timedelta(seconds=5))
            mock_ping.reset_mock()
            check_device(self.device, only_due=True)
            self.assertEqual(mock_ping.call_count, 1)  # 只有 follow 到期

            # 手動模式（only_due=False）跑全部
            mock_ping.reset_mock()
            check_device(self.device)
            self.assertEqual(mock_ping.call_count, 2)

    def test_form_interval_optional(self):
        from monitor.forms import MonitorCheckForm
        form = MonitorCheckForm({
            "check_type": "ping", "interval": "",
            "expected_status_code": "200", "enabled": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["interval"])

    def test_api_check_edit_accepts_null_interval(self):
        check = MonitorCheck.objects.create(device=self.device, check_type="ping", interval=60)
        self.client.login(username="iv_user", password="test-pass-123")
        resp = self.client.post(
            f"/api/checks/{check.pk}/edit/",
            data='{"interval": null}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        check.refresh_from_db()
        self.assertIsNone(check.interval)
