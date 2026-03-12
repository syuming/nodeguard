import threading
import time
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Device, DeviceLog, Company, UserProfile, DowntimeRecord
from .forms import DeviceForm, CompanyForm
from .utils import check_device

# ── 持續監控全域狀態 ──────────────────────────────────────────────────────────
_monitor_thread = None
_monitor_stop = threading.Event()
MONITOR_INTERVAL = 60  # 每隔幾秒檢查一次（預設 60 秒）


def _monitor_loop():
    from django.utils import timezone as tz
    while not _monitor_stop.is_set():
        now = tz.now()
        devices = list(Device.objects.all())
        for d in devices:
            if _monitor_stop.is_set():
                break
            interval = d.monitor_interval or MONITOR_INTERVAL
            if d.last_checked is None or (now - d.last_checked).total_seconds() >= interval:
                try:
                    check_device(d)
                except Exception:
                    pass
        _monitor_stop.wait(10)  # 每 10 秒輪詢一次，依各設備間隔決定是否檢查


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_profile(user):
    """Return UserProfile, creating a default one if missing.
    Django superuser 自動對應到 admin 角色。
    """
    default_role = "admin" if user.is_superuser else "company_manager"
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": default_role})
    # 若已存在但 superuser 尚未設為 admin，自動修正
    if user.is_superuser and not profile.is_admin:
        profile.role = "admin"
        profile.save(update_fields=["role"])
    return profile


def get_visible_devices(user):
    """Return Device queryset scoped to the user's permission."""
    profile = get_profile(user)
    if profile.is_admin:
        return Device.objects.select_related("company").all()
    if profile.company:
        return Device.objects.select_related("company").filter(company=profile.company)
    return Device.objects.none()


def can_access_device(user, device):
    """Check whether user may access a specific device."""
    profile = get_profile(user)
    if profile.is_admin:
        return True
    return profile.company is not None and device.company_id == profile.company_id


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get("next", "/"))
        messages.error(request, "帳號或密碼錯誤")
    return render(request, "monitor/login.html")


def logout_view(request):
    logout(request)
    return redirect("/login/")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    profile = get_profile(request.user)
    devices = get_visible_devices(request.user).order_by("company__name", "name")
    total   = devices.count()
    online  = devices.filter(status="online").count()
    offline = devices.filter(status="offline").count()
    warning = devices.filter(status="warning").count()

    # Admin sees per-company summary
    company_stats = []
    if profile.is_admin:
        for company in Company.objects.all().order_by("name"):
            cd = devices.filter(company=company)
            company_stats.append({
                "company": company,
                "total":   cd.count(),
                "online":  cd.filter(status="online").count(),
                "offline": cd.filter(status="offline").count(),
                "warning": cd.filter(status="warning").count(),
            })

    return render(request, "monitor/dashboard.html", {
        "devices": devices,
        "total": total,
        "online": online,
        "offline": offline,
        "warning": warning,
        "profile": profile,
        "company_stats": company_stats,
    })


# ── Device Detail ─────────────────────────────────────────────────────────────

@login_required
def device_detail(request, pk):
    device = get_object_or_404(Device.objects.select_related("company"), pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    logs = device.logs.all()[:100]
    downtimes = device.downtimes.all()[:50]
    profile = get_profile(request.user)
    return render(request, "monitor/device_detail.html", {
        "device": device, "logs": logs, "downtimes": downtimes, "profile": profile
    })


# ── Device CRUD ───────────────────────────────────────────────────────────────

@login_required
def device_add(request):
    profile = get_profile(request.user)
    form = DeviceForm(request.POST or None, user_profile=profile)
    if form.is_valid():
        form.save()
        messages.success(request, "設備已新增")
        return redirect("/")
    return render(request, "monitor/device_form.html", {
        "form": form, "title": "新增設備", "profile": profile
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
        "form": form, "title": "編輯設備", "profile": profile
    })


@login_required
@require_POST
def device_delete(request, pk):
    device = get_object_or_404(Device, pk=pk)
    if not can_access_device(request.user, device):
        raise Http404
    device.delete()
    messages.success(request, "設備已刪除")
    return redirect("/")


# ── Company CRUD（僅系統管理者） ───────────────────────────────────────────────

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


# ── API ───────────────────────────────────────────────────────────────────────

@login_required
def api_device_status(request):
    devices = get_visible_devices(request.user).values(
        "id", "name", "ip_address", "status", "last_checked", "company__name"
    )
    return JsonResponse({"devices": list(devices)})


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
    logs = list(device.logs.values("id", "level", "message", "raw_output", "created_at")[:50])
    for log in logs:
        log["created_at"] = log["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    return JsonResponse({"logs": logs})


@login_required
@require_POST
def api_monitor_toggle(request):
    global _monitor_thread, _monitor_stop
    if _monitor_thread and _monitor_thread.is_alive():
        _monitor_stop.set()
        _monitor_thread = None
        return JsonResponse({"monitoring": False, "interval": MONITOR_INTERVAL})
    else:
        _monitor_stop.clear()
        _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        _monitor_thread.start()
        return JsonResponse({"monitoring": True, "interval": MONITOR_INTERVAL})


@login_required
def api_monitor_status(request):
    running = _monitor_thread is not None and _monitor_thread.is_alive()
    return JsonResponse({"monitoring": running, "interval": MONITOR_INTERVAL})
