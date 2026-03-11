from django.contrib import admin
from .models import Company, UserProfile, Device, DeviceLog


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "created_at"]
    search_fields = ["name"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "company"]
    list_filter = ["role", "company"]
    search_fields = ["user__username"]


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ["name", "company", "ip_address", "device_type", "status", "last_checked"]
    list_filter = ["status", "device_type", "company"]
    search_fields = ["name", "ip_address"]


@admin.register(DeviceLog)
class DeviceLogAdmin(admin.ModelAdmin):
    list_display = ["device", "level", "message", "created_at"]
    list_filter = ["level", "device__company"]
    readonly_fields = ["created_at"]
