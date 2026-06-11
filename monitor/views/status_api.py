"""設備狀態查詢與手動檢查 API。"""
import threading

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .. import monitoring
from ..models import Device, MonitorConfig
from ..utils import check_device
from .helpers import can_access_device, get_profile, get_visible_devices


@login_required
def api_device_status(request):
    from django.utils import timezone as tz
    devices = get_visible_devices(request.user).select_related("company")
    result = []
    for d in devices:
        result.append({
            "id": d.id,
            "name": d.name,
            "ip_address": d.ip_address,
            "status": d.status,
            "status_display": d.get_status_display(),
            "last_checked": tz.localtime(d.last_checked).strftime("%Y-%m-%d %H:%M:%S") if d.last_checked else None,
            "company_id": d.company_id,
            "company_name": d.company.name if d.company else None,
            "device_type_display": d.get_device_type_display(),
        })
    return JsonResponse({"devices": result})


@login_required
def api_device_detail_status(request, pk):
    """回傳單一設備的狀態、last_checked，以及各監控項目的 last_status"""
    from django.utils import timezone as tz
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    checks = list(device.checks.values("id", "last_status", "last_message", "last_checked"))
    for c in checks:
        if c["last_checked"]:
            c["last_checked"] = tz.localtime(c["last_checked"]).strftime("%m-%d %H:%M")
    return JsonResponse({
        "status": device.status,
        "last_checked": tz.localtime(device.last_checked).strftime("%Y-%m-%d %H:%M:%S") if device.last_checked else None,
        "checks": checks,
    })


@login_required
@require_POST
def api_check_device(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404

    def run():
        check_device(device)

    threading.Thread(target=run, daemon=True).start()
    return JsonResponse({"status": "checking", "device_id": pk})


@login_required
@require_POST
def api_check_all(request):
    devices = list(get_visible_devices(request.user))

    def run():
        for d in devices:
            check_device(d)

    threading.Thread(target=run, daemon=True).start()
    return JsonResponse({"status": "checking", "count": len(devices)})


@login_required
def api_device_logs(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    from django.utils import timezone as tz
    logs = list(device.logs.values("id", "level", "message", "raw_output", "created_at")[:50])
    for log in logs:
        log["created_at"] = tz.localtime(log["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
    return JsonResponse({"logs": logs})


@login_required
@require_POST
def api_monitor_toggle(request):
    interval = monitoring.get_global_interval()
    if monitoring.is_running():
        monitoring.stop()
        return JsonResponse({"monitoring": False, "interval": interval})
    monitoring.start()
    return JsonResponse({"monitoring": True, "interval": interval})


@login_required
def api_monitor_status(request):
    return JsonResponse({
        "monitoring": monitoring.is_running(),
        "interval": monitoring.get_global_interval(),
    })


MIN_INTERVAL = 1
MAX_INTERVAL = 3600


@login_required
@require_POST
def api_monitor_interval(request):
    """設定持續監控全域間隔（秒），僅系統管理者。"""
    profile = get_profile(request.user)
    if not profile.is_admin:
        return JsonResponse({"error": "無權限"}, status=403)
    try:
        interval = int(request.POST.get("interval", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "間隔必須是整數"}, status=400)
    if not (MIN_INTERVAL <= interval <= MAX_INTERVAL):
        return JsonResponse(
            {"error": f"間隔須介於 {MIN_INTERVAL}–{MAX_INTERVAL} 秒"}, status=400)
    cfg = MonitorConfig.get_config()
    cfg.interval = interval
    cfg.save(update_fields=["interval"])
    return JsonResponse({"ok": True, "interval": interval})
