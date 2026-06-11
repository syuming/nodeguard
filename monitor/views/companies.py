"""公司 CRUD 與孤立設備管理（僅系統管理者）。"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import CompanyForm
from ..models import Company, Device
from .bulk import bulk_create_devices
from .helpers import get_profile


@login_required
def company_detail(request, pk):
    profile = get_profile(request.user)
    company = get_object_or_404(Company, pk=pk)
    if not profile.is_admin and (profile.company is None or profile.company_id != pk):
        raise Http404

    bulk_created = bulk_errors = bulk_skipped = None

    if request.method == "POST" and profile.is_admin:
        bulk_created, bulk_errors, bulk_skipped = bulk_create_devices(request.POST, company)

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
