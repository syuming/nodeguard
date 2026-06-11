"""監控項目 CRUD 與 SNMP 掃描。"""
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from ..forms import MonitorCheckForm
from ..models import Device, MonitorCheck
from .helpers import can_access_device


@login_required
@require_POST
def api_snmp_add_checks(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    import json
    body = json.loads(request.body or b"{}")
    community = body.get("community", "public")
    port      = int(body.get("port", 161))
    version   = int(body.get("version", 2))
    interval  = int(body.get("interval", 60))
    interfaces = body.get("interfaces", [])
    created = 0
    OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
    for iface in interfaces:
        idx = iface.get("index")
        descr = iface.get("descr", f"if{idx}")
        oid = f"{OID_IF_OPER_STATUS}.{idx}" if idx else ""
        MonitorCheck.objects.create(
            device=device,
            check_type="snmp",
            snmp_community=community,
            snmp_version=version,
            snmp_port=port,
            snmp_oid=oid,
            snmp_label=descr,
            interval=interval,
            enabled=True,
        )
        created += 1
    return JsonResponse({"ok": True, "created": created})


@login_required
@require_POST
def api_snmp_scan(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    import json
    from ..utils import snmp_scan_interfaces
    body = json.loads(request.body or b"{}")
    community = body.get("community", "public")
    port      = int(body.get("port", 161))
    try:
        interfaces = snmp_scan_interfaces(device.ip_address, community=community, port=port)
        return JsonResponse({"ok": True, "interfaces": interfaces})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@login_required
@require_POST
def monitor_check_add(request, device_pk):
    device = get_object_or_404(Device, pk=device_pk)
    if not can_access_device(request.user, device):
        raise Http404
    form = MonitorCheckForm(request.POST)
    if form.is_valid():
        check = form.save(commit=False)
        check.device = device
        check.save()
        messages.success(request, "監控項目已新增")
        # 立即觸發一次背景檢查，讓狀態馬上更新而不是等到下一輪監控
        _device_pk = device.pk
        def _bg_check():
            from ..models import Device as _Device
            try:
                check_device(_Device.objects.get(pk=_device_pk))
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()
    else:
        for field_errors in form.errors.values():
            for e in field_errors:
                messages.error(request, e)
    return redirect(f"/device/{device_pk}/?tab=monitors")


@login_required
@require_POST
def monitor_check_delete(request, check_pk):
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    device_pk = check.device_id
    check.delete()
    messages.success(request, "監控項目已刪除")
    return redirect(f"/device/{device_pk}/?tab=monitors")


@login_required
@require_POST
def api_monitor_check_edit(request, check_pk):
    import json
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    body = json.loads(request.body or b"{}")
    check.port                = body.get("port") or None
    check.ssh_username        = body.get("ssh_username", "")
    check.url                 = body.get("url", "")
    check.expected_status_code = int(body.get("expected_status_code") or 200)
    check.snmp_community      = body.get("snmp_community", "public")
    check.snmp_port           = int(body.get("snmp_port") or 161)
    check.interval            = int(body.get("interval") or 60)
    if "snmp_label" in body:
        check.snmp_label = body["snmp_label"]
    if "snmp_oid" in body:
        check.snmp_oid = body["snmp_oid"]
    check.save()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def monitor_check_toggle(request, check_pk):
    check = get_object_or_404(MonitorCheck, pk=check_pk)
    if not can_access_device(request.user, check.device):
        raise Http404
    check.enabled = not check.enabled
    check.save(update_fields=["enabled"])
    return redirect(f"/device/{check.device_id}/?tab=monitors")
