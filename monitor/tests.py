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
