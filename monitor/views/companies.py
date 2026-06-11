"""公司 CRUD 與孤立設備管理（僅系統管理者）。"""
import logging
import re
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import CompanyForm
from ..models import Company, Device, MonitorCheck
from ..utils import check_device
from .helpers import get_profile

_dup_logger = logging.getLogger("nodeguard.duplicate_ip")


@login_required
def company_detail(request, pk):
    profile = get_profile(request.user)
    company = get_object_or_404(Company, pk=pk)
    if not profile.is_admin and (profile.company is None or profile.company_id != pk):
        raise Http404

    bulk_created = bulk_errors = bulk_skipped = None

    if request.method == "POST" and profile.is_admin:
        row_indices = sorted({
            int(m.group(1))
            for key in request.POST
            if (m := re.match(r'^name_(\d+)$', key))
        })
        bulk_created, bulk_errors, bulk_skipped = [], [], []
        for i in row_indices:
            name = request.POST.get(f"name_{i}", "").strip()
            ip   = request.POST.get(f"ip_{i}", "").strip()
            if not name and not ip:
                continue
            if not name or not ip:
                bulk_errors.append(f"第 {i} 筆：名稱和 IP 都必須填寫")
                continue
            existing = Device.objects.filter(ip_address=ip).select_related("company").first()
            if existing:
                bulk_skipped.append({
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
                bulk_created.append(device)
            except Exception as e:
                bulk_errors.append(f"第 {i} 筆（{name} / {ip}）：{e}")

        if bulk_created:
            def _bg():
                from ..models import Device as _D
                for dev in bulk_created:
                    try:
                        check_device(_D.objects.get(pk=dev.pk))
                    except Exception:
                        pass
            threading.Thread(target=_bg, daemon=True).start()

    devices = Device.objects.filter(company=company).order_by("name")
    status_counts = {s: devices.filter(status=s).count() for s in ("online", "warning", "offline", "unknown")}
    return render(request, "monitor/company_detail.html", {
        "company": company, "devices": devices, "profile": profile,
        "row_range": range(1, 11),
        "bulk_created": bulk_created, "bulk_errors": bulk_errors, "bulk_skipped": bulk_skipped,
        **status_counts,
    })


@login_required
def orphan_devices(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    devices = Device.objects.filter(company__isnull=True).order_by("name")
    companies = Company.objects.all().order_by("name")
    return render(request, "monitor/orphan_devices.html", {
        "devices": devices, "companies": companies, "profile": profile,
    })


@login_required
@require_POST
def api_assign_company(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        return JsonResponse({"ok": False}, status=403)
    device = get_object_or_404(Device, pk=pk, company__isnull=True)
    cid = request.POST.get("company_id", "").strip()
    if not cid:
        return JsonResponse({"ok": False, "error": "未指定公司"})
    try:
        company = Company.objects.get(pk=cid)
    except Company.DoesNotExist:
        return JsonResponse({"ok": False, "error": "公司不存在"})
    device.company = company
    device.save(update_fields=["company"])
    return JsonResponse({"ok": True, "company_name": company.name})


@login_required
def company_list(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    companies = Company.objects.order_by("name")
    return render(request, "monitor/company_list.html", {
        "companies": companies, "profile": profile
    })


@login_required
def company_add(request):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    form = CompanyForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "公司已新增")
        return redirect("/company/")
    return render(request, "monitor/company_form.html", {
        "form": form, "title": "新增公司", "profile": profile
    })


@login_required
def company_edit(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    company = get_object_or_404(Company, pk=pk)
    form = CompanyForm(request.POST or None, instance=company)
    if form.is_valid():
        form.save()
        messages.success(request, "公司已更新")
        return redirect("/company/")
    return render(request, "monitor/company_form.html", {
        "form": form, "title": "編輯公司", "profile": profile
    })


@login_required
@require_POST
def company_delete(request, pk):
    profile = get_profile(request.user)
    if not profile.is_admin:
        raise Http404
    company = get_object_or_404(Company, pk=pk)
    company.delete()
    messages.success(request, "公司已刪除")
    return redirect("/company/")
