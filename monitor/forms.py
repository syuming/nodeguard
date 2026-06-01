from django import forms
from django.contrib.auth.models import User
from .models import Device, Company, MonitorCheck


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        labels = {
            "username":   "帳號",
            "first_name": "名字",
            "last_name":  "姓氏",
            "email":      "Email",
        }


class UserCreateForm(forms.Form):
    username   = forms.CharField(label="帳號")
    first_name = forms.CharField(label="名字", required=False)
    last_name  = forms.CharField(label="姓氏", required=False)
    email      = forms.EmailField(label="Email", required=False)
    password1  = forms.CharField(label="密碼", widget=forms.PasswordInput)
    password2  = forms.CharField(label="確認密碼", widget=forms.PasswordInput)
    role       = forms.ChoiceField(label="角色", choices=[("company_manager", "公司管理者"), ("admin", "系統管理者")])
    company    = forms.ModelChoiceField(label="所屬公司", queryset=Company.objects.all().order_by("name"), required=False, empty_label="（無）")

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("此帳號已存在")
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("兩次輸入的密碼不一致")
        return cleaned


class UserProfileMetaForm(forms.Form):
    role    = forms.ChoiceField(label="角色", choices=[("company_manager", "公司管理者"), ("admin", "系統管理者")])
    company = forms.ModelChoiceField(label="所屬公司", queryset=Company.objects.all().order_by("name"), required=False, empty_label="（無）")


class AdminSetPasswordForm(forms.Form):
    new_password1 = forms.CharField(label="新密碼", widget=forms.PasswordInput)
    new_password2 = forms.CharField(label="確認新密碼", widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("兩次輸入的密碼不一致")
        return cleaned


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class MonitorCheckForm(forms.ModelForm):
    class Meta:
        model = MonitorCheck
        fields = [
            "check_type", "port",
            "ssh_username", "ssh_password",
            "url", "expected_status_code",
            "snmp_community", "snmp_version", "snmp_port",
            "interval", "enabled",
        ]
        widgets = {
            "ssh_password": forms.PasswordInput(render_value=True),
        }
        labels = {
            "check_type":           "監控類型",
            "port":                 "Port",
            "ssh_username":         "SSH 帳號",
            "ssh_password":         "SSH 密碼",
            "url":                  "URL",
            "expected_status_code": "預期 HTTP 狀態碼",
            "snmp_community":       "Community String",
            "snmp_version":         "SNMP 版本",
            "snmp_port":            "SNMP Port",
            "interval":             "檢查間隔（秒）",
            "enabled":              "啟用",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("port", "ssh_username", "ssh_password", "url",
                  "snmp_community", "snmp_version", "snmp_port"):
            self.fields[f].required = False
        self.fields["snmp_version"].widget = forms.Select(choices=[(1, "v1"), (2, "v2c")])

    def clean(self):
        cleaned = super().clean()
        check_type = cleaned.get("check_type")
        if check_type in ("tcp", "ssh") and not cleaned.get("port"):
            self.add_error("port", "TCP / SSH 檢查需填寫 Port")
        if check_type == "http" and not cleaned.get("url"):
            self.add_error("url", "HTTP 檢查需填寫 URL")
        return cleaned


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            "company",
            "customer_name", "customer_id", "circuit_number", "customer_address",
            "name", "ip_address", "device_type", "description",
        ]
        widgets = {
            "description":      forms.Textarea(attrs={"rows": 2}),
            "customer_address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user_profile=None, initial_company_pk=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user_profile and not user_profile.is_admin:
            # Company manager: lock company to their own, hide the field
            self.fields["company"].queryset = Company.objects.filter(pk=user_profile.company_id)
            self.fields["company"].initial = user_profile.company
            self.fields["company"].widget = forms.HiddenInput()
            self.fields["company"].empty_label = None
        else:
            self.fields["company"].queryset = Company.objects.all().order_by("name")
            # Pre-select company when coming from company detail page
            if initial_company_pk:
                try:
                    self.fields["company"].initial = Company.objects.get(pk=initial_company_pk)
                except Company.DoesNotExist:
                    pass
