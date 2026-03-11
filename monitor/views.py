import threading
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.contrib import messages

from .models import Device, DeviceLog, Company, UserProfile
from .forms import DeviceForm
from .utils import check_device


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_profile(user):
    """Return UserProfile, creating a default one if missing."""
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": "company_manager"})
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
    profile = get_profile(request.user)
    return render(request, "monitor/device_detail.html", {
        "device": device, "logs": logs, "profile": profile
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
