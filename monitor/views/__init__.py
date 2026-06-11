"""views 套件：依功能域拆分，於此重新匯出供 urls.py 使用。"""
from .auth import change_password, login_view, logout_view, profile_edit
from .checks import (
    api_monitor_check_edit,
    api_snmp_add_checks,
    api_snmp_scan,
    monitor_check_add,
    monitor_check_delete,
    monitor_check_toggle,
)
from .companies import (
    api_assign_company,
    company_add,
    company_delete,
    company_detail,
    company_edit,
    company_list,
    orphan_devices,
)
from .dashboard import dashboard
from .devices import (
    device_add,
    device_bulk_add,
    device_bulk_delete,
    device_delete,
    device_detail,
    device_edit,
)
from .email_views import email_settings, email_test
from .helpers import can_access_device, get_profile, get_visible_devices
from .status_api import (
    api_check_all,
    api_check_device,
    api_device_detail_status,
    api_device_logs,
    api_device_status,
    api_monitor_interval,
    api_monitor_status,
    api_monitor_toggle,
)
from .system import (
    api_changelog,
    api_check_ip,
    api_duplicate_ip_log,
    api_ping_check,
    api_system_restart,
    api_system_update,
    api_traceroute_check,
    api_version_check,
    duplicate_ip_log,
)
from .users import user_add, user_edit, user_list
