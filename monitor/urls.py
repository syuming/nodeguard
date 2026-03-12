from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("device/add/", views.device_add, name="device_add"),
    path("device/<int:pk>/", views.device_detail, name="device_detail"),
    path("device/<int:pk>/edit/", views.device_edit, name="device_edit"),
    path("device/<int:pk>/delete/", views.device_delete, name="device_delete"),

    path("company/", views.company_list, name="company_list"),
    path("company/add/", views.company_add, name="company_add"),
    path("company/<int:pk>/edit/", views.company_edit, name="company_edit"),
    path("company/<int:pk>/delete/", views.company_delete, name="company_delete"),

    path("api/status/", views.api_device_status, name="api_status"),
    path("api/check-all/", views.api_check_all, name="api_check_all"),
    path("api/device/<int:pk>/check/", views.api_check_device, name="api_check_device"),
    path("api/device/<int:pk>/logs/", views.api_device_logs, name="api_device_logs"),
    path("api/monitor/toggle/", views.api_monitor_toggle, name="api_monitor_toggle"),
    path("api/monitor/status/", views.api_monitor_status, name="api_monitor_status"),
]
