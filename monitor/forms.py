from django import forms
from .models import Device


class DeviceForm(forms.ModelForm):
    ssh_password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        required=False,
        label="SSH 密碼",
    )

    class Meta:
        model = Device
        fields = [
            "name", "ip_address", "device_type",
            "ssh_username", "ssh_password", "ssh_port", "description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }
