"""設備 CRUD 與批量新增/刪除。"""
import logging
import re
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import DeviceForm, MonitorCheckForm
from ..models import Company, Device, DowntimeRecord, MonitorCheck
from ..utils import check_device
from .helpers import can_access_device, get_profile, get_visible_devices

_dup_logger = logging.getLogger("nodeguard.duplicate_ip")


@login_required
def device_detail(request, pk):
    device = get_object_or_404(Device.objects.select_related("company"), pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    logs = device.logs.all()[:100]
    downtimes = device.downtimes.all()[:50]
    checks = device.checks.all()
    check_form = MonitorCheckForm()
    profile = get_profile(request.user)
    return render(request, "monitor/device_detail.html", {
        "device": device, "logs": logs, "downtimes": downtimes,
        "checks": checks, "check_form": check_form, "profile": profile
    })


# ── Device CRUD ───────────────────────────────────────────────────────────────

@login_required
def device_add(request):
    profile = get_profile(request.user)
    initial_company_pk = request.GET.get("company")
    form = DeviceForm(request.POST or None, user_profile=profile, initial_company_pk=initial_company_pk)
    if form.is_valid():
        device = form.save()
        MonitorCheck.objects.create(device=device, check_type="ping", interval=3, enabled=True)
        _dpk = device.pk
        def _bg_check():
            from ..models import Device as _D
            try:
                check_device(_D.objects.get(pk=_dpk))
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()
        messages.success(request, "設備已新增")
        company_pk = form.cleaned_data.get("company")
        if company_pk:
            return redirect(f"/company/{company_pk.pk}/")
        return redirect("/")
    return render(request, "monitor/device_form.html", {
        "form": form, "title": "新增設備", "profile": profile, "device_id": None,
    })


@login_required
def device_bulk_add(request):
    profile = get_profile(request.user)
    companies = Company.objects.all().order_by("name") if profile.is_admin else None

    if request.method == "POST":
        # 判斷公司
        company = None
        if profile.is_admin:
            cid = request.POST.get("company")
            if cid:
                try:
                    company = Company.objects.get(pk=cid)
                except Company.DoesNotExist:
                    pass
            if company is None:
                return render(request, "monitor/device_bulk_add.html", {
                    "profile": profile, "companies": companies,
                    "row_range": range(1, 11),
                    "company_error": "請選擇所屬公司",
                })
        elif profile.company:
            company = profile.company

        # 動態收集所有提交的列（支援超過 10 筆）
        row_indices = sorted({
            int(m.group(1))
            for key in request.POST
            if (m := re.match(r'^name_(\d+)$', key))
        })

        created, errors, skipped = [], [], []
        for i in row_indices:
            name = request.POST.get(f"name_{i}", "").strip()
            ip   = request.POST.get(f"ip_{i}", "").strip()
            if not name and not ip:
                continue
            if not name or not ip:
                errors.append(f"第 {i} 筆：名稱和 IP 都必須填寫")
                continue
            existing = Device.objects.filter(ip_address=ip).select_related("company").first()
            if existing:
                skipped.append({
                    "row": i, "name": name, "ip": ip,
                    "existing_name": existing.name,
                    "existing_company": existing.company.name if existing.company else "-",
                })
                _dup_logger.warning(
                    "重複 IP 略過 | row=%d name=%s ip=%s existing=%s company=%s",
                    i, name, ip, existing.name,
                    existing.company.name if existing.company else "-",
                )
                continue
            try:
                device = Device.objects.create(
                    name=name, ip_address=ip,
                    company=company, device_type="generic",
                )
                MonitorCheck.objects.create(device=device, check_type="ping", interval=3, enabled=True)
                created.append(device)
            except Exception as e:
                errors.append(f"第 {i} 筆（{name} / {ip}）：{e}")

        # 背景跑一次初始檢查
        def _bg():
            from ..models import Device as _D
            for dev in created:
                try:
                    check_device(_D.objects.get(pk=dev.pk))
                except Exception:
                    pass
        if created:
            threading.Thread(target=_bg, daemon=True).start()

        return render(request, "monitor/device_bulk_add.html", {
            "profile": profile, "companies": companies,
            "created": created, "errors": errors, "skipped": skipped, "done": True,
        })

    return render(request, "monitor/device_bulk_add.html", {
        "profile": profile, "companies": companies,
        "row_range": range(1, 11),
    })


@login_required
def device_edit(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    profile = get_profile(request.user)
    form = DeviceForm(request.POST or None, instance=device, user_profile=profile)
    if form.is_valid():
        form.save()
        messages.success(request, "設備已更新")
        return redirect(f"/device/{pk}/")
    return render(request, "monitor/device_form.html", {
        "form": form, "title": "編輯設備", "profile": profile, "device_id": pk,
    })


@login_required
@require_POST
def device_delete(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    company_pk = device.company_id
    device.delete()
    messages.success(request, "設備已刪除")
    if company_pk:
        return redirect(f"/company/{company_pk}/")
    return redirect("/")


@login_required
def device_bulk_delete(request):
    from django.utils import timezone as tz
    from datetime import timedelta
    profile = get_profile(request.user)
    companies = Company.objects.all().order_by("name") if profile.is_admin else None

    if request.method == "POST" and "confirm_delete" in request.POST:
        ids = request.POST.getlist("device_ids")
        if ids:
            devices = get_visible_devices(request.user).filter(pk__in=ids)
            count = devices.count()
            devices.delete()
            messages.success(request, f"已刪除 {count} 台設備")
        return redirect("/device/bulk-delete/")

    # 搜尋條件
    duration = request.GET.get("duration", "").strip()
    unit     = request.GET.get("unit", "hours")
    company_id = request.GET.get("company", "")
    devices = None

    if duration:
        try:
            hours = float(duration) * (24 if unit == "days" else 1)
            threshold = tz.now() - timedelta(hours=hours)
            # 目前離線且斷線開始時間超過 threshold
            offline_since_ids = DowntimeRecord.objects.filter(
                recovered_at__isnull=True,
                started_at__lte=threshold,
            ).values_list("device_id", flat=True)
            devices = get_visible_devices(request.user).filter(
                pk__in=offline_since_ids, status="offline"
            ).select_related("company")
            if company_id:
                devices = devices.filter(company_id=company_id)
        except ValueError:
            messages.error(request, "請輸入有效的數字")

    return render(request, "monitor/device_bulk_delete.html", {
        "profile": profile,
        "companies": companies,
        "devices": devices,
        "duration": duration,
        "unit": unit,
        "company_id": company_id,
    })
