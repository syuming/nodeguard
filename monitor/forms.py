from django import forms
from .models import Device, Company


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class DeviceForm(forms.ModelForm):
    ssh_password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        required=False,
        label="SSH 密碼",
    )

    class Meta:
        model = Device
        fields = [
            "company",
            "customer_name", "customer_id", "circuit_number", "customer_address",
            "name", "ip_address", "device_type", "monitor_interval",
            "ssh_username", "ssh_password", "ssh_port", "description",
        ]
        widgets = {
            "description":       forms.Textarea(attrs={"rows": 2}),
            "customer_address":  forms.Textarea(attrs={"rows": 2}),
            "monitor_interval":  forms.NumberInput(attrs={"min": 10}),
        }

    def __init__(self, *args, user_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user_profile and not user_profile.is_admin:
            # Company manager: lock company to their own, hide the field
            self.fields["company"].queryset = Company.objects.filter(pk=user_profile.company_id)
            self.fields["company"].initial = user_profile.company
            self.fields["company"].widget = forms.HiddenInput()
            self.fields["company"].empty_label = None
        else:
            self.fields["company"].queryset = Company.objects.all().order_by("name")
