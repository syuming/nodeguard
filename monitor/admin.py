from django.contrib import admin
from .models import Device, DeviceLog


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "ip_address", "device_type", "status", "last_checked"]
    list_filter = ["status", "device_type"]
    search_fields = ["name", "ip_address"]


@admin.register(DeviceLog)
class DeviceLogAdmin(admin.ModelAdmin):
    list_display = ["device", "level", "message", "created_at"]
    list_filter = ["level", "device"]
    readonly_fields = ["created_at"]
